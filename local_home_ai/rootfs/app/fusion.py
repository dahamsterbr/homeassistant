"""Room occupancy fusion engine with online learning."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from .config import Options, RoomConfig
from .ha_client import HomeAssistantClient
from .llm_client import LLMClient
from .memory import MemoryStore
from .mqtt_pub import MqttPublisher
from .plugins import get_adapter

logger = logging.getLogger(__name__)


@dataclass
class RoomResult:
    room: str
    occupied: bool
    confidence: float
    person: str = "unknown"
    reason: str = ""
    features: dict[str, float] = field(default_factory=dict)
    score: float = 0.0


class FusionEngine:
    def __init__(
        self,
        options: Options,
        ha: HomeAssistantClient,
        llm: LLMClient,
        memory: MemoryStore,
        mqtt: MqttPublisher,
    ) -> None:
        self.options = options
        self.ha = ha
        self.llm = llm
        self.memory = memory
        self.mqtt = mqtt
        self._last: dict[str, RoomResult] = {}
        self._last_attr_ts: dict[str, float] = {}
        self._attr_cooldown = 45.0

    def evaluate_room(self, room: RoomConfig) -> RoomResult:
        features: dict[str, float] = {}
        weighted = 0.0
        total_weight = 0.0

        for sensor in room.sensors:
            adapter = get_adapter(sensor.adapter)
            state = self.ha.states.get(sensor.entity_id)
            feats = adapter.features(sensor.entity_id, state)
            features.update(feats)
            for feature_name, value in feats.items():
                default_w = adapter.default_weight
                weight = self.memory.get_weight(room.name, feature_name, default_w)
                weighted += weight * value
                total_weight += weight

        for entity_id in room.soft_entities:
            adapter = get_adapter("generic")
            state = self.ha.states.get(entity_id)
            feats = adapter.features(entity_id, state)
            features.update(feats)
            for feature_name, value in feats.items():
                weight = self.memory.get_weight(room.name, feature_name, 0.2)
                weighted += weight * value
                total_weight += weight

        score = (weighted / total_weight) if total_weight else 0.0
        occupied = score >= 0.35
        confidence = min(1.0, max(0.0, score if occupied else 1.0 - score))

        prev = self._last.get(room.name)
        person = prev.person if prev and occupied else "unknown"
        reason = prev.reason if prev and occupied else "fusion"

        result = RoomResult(
            room=room.name,
            occupied=occupied,
            confidence=confidence,
            person=person if occupied else "unknown",
            reason=reason if occupied else "empty",
            features=features,
            score=score,
        )
        return result

    async def evaluate_all(self) -> list[RoomResult]:
        results: list[RoomResult] = []
        for room in self.options.rooms:
            result = self.evaluate_room(room)
            await self._maybe_attribute(room, result)
            self._learn(room, result)
            self._publish(result)
            self._last[room.name] = result
            results.append(result)
        return results

    async def _maybe_attribute(self, room: RoomConfig, result: RoomResult) -> None:
        if not result.occupied:
            result.person = "unknown"
            result.reason = "empty"
            return

        now = time.time()
        last = self._last_attr_ts.get(room.name, 0.0)
        prev = self._last.get(room.name)
        became_occupied = not prev or not prev.occupied
        stale = (now - last) >= self._attr_cooldown
        if not (became_occupied or stale):
            if prev:
                result.person = prev.person
                result.reason = prev.reason
            return

        persons = self.ha.persons_home(self.options.persons)
        snippets = self.memory.recent_summaries(room.name)
        attribution = await self.llm.attribute_person(
            room=room.name,
            features=result.features,
            persons_home=persons,
            memory_snippets=snippets,
            escalate_below=self.options.confidence_escalate,
        )
        result.person = str(attribution.get("person") or "unknown")
        result.reason = str(attribution.get("reason") or "")
        # Blend LLM confidence lightly into published confidence
        llm_conf = float(attribution.get("confidence") or 0.0)
        if llm_conf > 0:
            result.confidence = min(1.0, (result.confidence * 0.7) + (llm_conf * 0.3))
        self._last_attr_ts[room.name] = now

        summary = (
            f"{room.name}: occupied={result.occupied} person={result.person} "
            f"conf={result.confidence:.2f} reason={result.reason}"
        )
        self.memory.add_episode(
            room=room.name,
            occupied=result.occupied,
            confidence=result.confidence,
            person=result.person,
            features=result.features,
            summary=summary,
        )

    def _learn(self, room: RoomConfig, result: RoomResult) -> None:
        if not self.options.learn_enabled:
            return
        for sensor in room.sensors:
            adapter = get_adapter(sensor.adapter)
            state = self.ha.states.get(sensor.entity_id)
            active = adapter.is_active(state)
            for feature_name in adapter.features(sensor.entity_id, state):
                self.memory.nudge_weight(
                    room.name,
                    feature_name,
                    adapter.default_weight,
                    active=active,
                    occupied=result.occupied,
                )

    def _publish(self, result: RoomResult) -> None:
        self.mqtt.publish_room(
            result.room,
            occupied=result.occupied,
            confidence=result.confidence,
            person=result.person,
            reason=result.reason,
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            room: {
                "occupied": res.occupied,
                "confidence": res.confidence,
                "person": res.person,
                "reason": res.reason,
                "score": res.score,
            }
            for room, res in self._last.items()
        }
