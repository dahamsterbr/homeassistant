"""SensorAdapter interface and registry."""

from __future__ import annotations

from typing import Any, Protocol


class SensorAdapter(Protocol):
    name: str
    default_weight: float

    def is_active(self, state: dict[str, Any] | None) -> bool:
        """Return True when this sensor indicates presence/activity."""

    def features(self, entity_id: str, state: dict[str, Any] | None) -> dict[str, float]:
        """Return feature_name -> 0/1 contribution for fusion."""


class BaseAdapter:
    name = "generic"
    default_weight = 0.4
    on_states = {
        "on",
        "home",
        "occupied",
        "detected",
        "open",
        "playing",
        "true",
    }

    def is_active(self, state: dict[str, Any] | None) -> bool:
        if not state:
            return False
        value = str(state.get("state", "")).lower()
        return value in self.on_states

    def features(self, entity_id: str, state: dict[str, Any] | None) -> dict[str, float]:
        active = 1.0 if self.is_active(state) else 0.0
        return {f"{self.name}:{entity_id}": active}


class MmwaveAdapter(BaseAdapter):
    name = "mmwave"
    default_weight = 1.0


class PirAdapter(BaseAdapter):
    name = "pir"
    default_weight = 0.65


class RadarAdapter(BaseAdapter):
    name = "radar"
    default_weight = 0.95


class FrigateAdapter(BaseAdapter):
    name = "frigate"
    default_weight = 0.75


class LightAdapter(BaseAdapter):
    name = "light"
    default_weight = 0.25


class MediaAdapter(BaseAdapter):
    name = "media"
    default_weight = 0.3
    on_states = {"playing", "on", "paused"}


class PersonAdapter(BaseAdapter):
    name = "person"
    default_weight = 0.5
    on_states = {"home"}


class FutureBleAdapter(BaseAdapter):
    """Stub for future ESPresense / BLE room-level tracking."""

    name = "ble"
    default_weight = 0.85

    def features(self, entity_id: str, state: dict[str, Any] | None) -> dict[str, float]:
        # Future: map distance/rssi attributes into graded presence.
        return super().features(entity_id, state)


ADAPTERS: dict[str, BaseAdapter] = {
    "mmwave": MmwaveAdapter(),
    "pir": PirAdapter(),
    "radar": RadarAdapter(),
    "frigate": FrigateAdapter(),
    "light": LightAdapter(),
    "media": MediaAdapter(),
    "person": PersonAdapter(),
    "generic": BaseAdapter(),
    "ble": FutureBleAdapter(),
}


def get_adapter(name: str) -> BaseAdapter:
    return ADAPTERS.get(name, ADAPTERS["generic"])
