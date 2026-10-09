"""MQTT discovery publisher for Local Home AI entities."""

from __future__ import annotations

import json
import logging
import threading
from typing import Any

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


class MqttPublisher:
    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        discovery_prefix: str,
        state_prefix: str,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.discovery_prefix = discovery_prefix.rstrip("/")
        self.state_prefix = state_prefix.rstrip("/")
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id="local_home_ai",
        )
        if username:
            self.client.username_pw_set(username, password or None)
        self.client.on_connect = self._on_connect
        self._connected = threading.Event()
        self._discovered: set[str] = set()
        self._status_discovered = False

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: Any,
        reason_code: Any,
        properties: Any = None,
    ) -> None:
        if reason_code == 0 or str(reason_code) in {"Success", "0"}:
            self._connected.set()
            logger.info("MQTT connected to %s:%s", self.host, self.port)
        else:
            logger.warning("MQTT connect failed: %s", reason_code)

    def start(self) -> None:
        try:
            self.client.connect(self.host, self.port, keepalive=60)
            self.client.loop_start()
        except Exception as exc:  # noqa: BLE001
            logger.error("MQTT connect error: %s", exc)

    def stop(self) -> None:
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:  # noqa: BLE001
            pass

    def _publish(self, topic: str, payload: str | dict[str, Any], retain: bool = True) -> None:
        body = payload if isinstance(payload, str) else json.dumps(payload)
        self.client.publish(topic, body, qos=1, retain=retain)

    def _device(self) -> dict[str, Any]:
        return {
            "identifiers": ["local_home_ai"],
            "name": "Local Home AI",
            "manufacturer": "Local",
            "model": "Presence Fusion",
        }

    def ensure_room_discovery(self, room: str, friendly: str | None = None) -> None:
        if room in self._discovered:
            return
        name = friendly or room.replace("_", " ").title()
        object_id = f"lhai_{room}"
        base = f"{self.state_prefix}/{room}"
        device = self._device()

        occupied = {
            "name": f"LHAI {name} Occupied",
            "unique_id": f"{object_id}_occupied",
            "state_topic": f"{base}/occupied",
            "payload_on": "ON",
            "payload_off": "OFF",
            "device_class": "occupancy",
            "availability_topic": f"{self.state_prefix}/status",
            "payload_available": "online",
            "payload_not_available": "offline",
            "device": device,
        }
        confidence = {
            "name": f"LHAI {name} Confidence",
            "unique_id": f"{object_id}_confidence",
            "state_topic": f"{base}/confidence",
            "unit_of_measurement": "%",
            "state_class": "measurement",
            "availability_topic": f"{self.state_prefix}/status",
            "payload_available": "online",
            "payload_not_available": "offline",
            "device": device,
        }
        person = {
            "name": f"LHAI {name} Likely Person",
            "unique_id": f"{object_id}_likely_person",
            "state_topic": f"{base}/likely_person",
            "availability_topic": f"{self.state_prefix}/status",
            "payload_available": "online",
            "payload_not_available": "offline",
            "device": device,
        }
        reason = {
            "name": f"LHAI {name} Reason",
            "unique_id": f"{object_id}_reason",
            "state_topic": f"{base}/reason",
            "availability_topic": f"{self.state_prefix}/status",
            "payload_available": "online",
            "payload_not_available": "offline",
            "device": device,
        }
        model = {
            "name": f"LHAI {name} LLM Model",
            "unique_id": f"{object_id}_llm_model",
            "state_topic": f"{base}/llm_model",
            "availability_topic": f"{self.state_prefix}/status",
            "payload_available": "online",
            "payload_not_available": "offline",
            "device": device,
        }

        prefix = self.discovery_prefix
        self._publish(f"{prefix}/binary_sensor/{object_id}_occupied/config", occupied)
        self._publish(f"{prefix}/sensor/{object_id}_confidence/config", confidence)
        self._publish(f"{prefix}/sensor/{object_id}_likely_person/config", person)
        self._publish(f"{prefix}/sensor/{object_id}_reason/config", reason)
        self._publish(f"{prefix}/sensor/{object_id}_llm_model/config", model)
        self._publish(f"{self.state_prefix}/status", "online")
        self._discovered.add(room)

    def ensure_status_discovery(self) -> None:
        if self._status_discovered:
            return
        device = self._device()
        prefix = self.discovery_prefix
        base = f"{self.state_prefix}/system"
        for key, name, uid in (
            ("llm_ok", "LHAI LLM Online", "lhai_llm_ok"),
            ("llm_calls", "LHAI LLM Call Count", "lhai_llm_calls"),
            ("llm_last", "LHAI LLM Last Call", "lhai_llm_last"),
            ("llm_error", "LHAI LLM Error", "lhai_llm_error"),
        ):
            payload = {
                "name": name,
                "unique_id": uid,
                "state_topic": f"{base}/{key}",
                "availability_topic": f"{self.state_prefix}/status",
                "payload_available": "online",
                "payload_not_available": "offline",
                "device": device,
            }
            if key == "llm_calls":
                payload["state_class"] = "total_increasing"
            domain = "binary_sensor" if key == "llm_ok" else "sensor"
            if key == "llm_ok":
                payload.update(
                    {
                        "payload_on": "ON",
                        "payload_off": "OFF",
                        "device_class": "connectivity",
                    }
                )
            self._publish(f"{prefix}/{domain}/{uid}/config", payload)
        self._status_discovered = True

    def publish_room(
        self,
        room: str,
        *,
        occupied: bool,
        confidence: float,
        person: str,
        reason: str,
        model: str = "",
    ) -> None:
        self.ensure_room_discovery(room)
        base = f"{self.state_prefix}/{room}"
        self._publish(f"{base}/occupied", "ON" if occupied else "OFF")
        self._publish(f"{base}/confidence", f"{round(confidence * 100, 1)}")
        self._publish(f"{base}/likely_person", person or "unknown")
        self._publish(f"{base}/reason", (reason or "")[:255])
        self._publish(f"{base}/llm_model", model or "none")

    def publish_llm_status(
        self,
        *,
        ok: bool,
        call_count: int,
        last_call: dict[str, Any] | None,
        error: str | None,
    ) -> None:
        self.ensure_status_discovery()
        base = f"{self.state_prefix}/system"
        self._publish(f"{self.state_prefix}/status", "online")
        self._publish(f"{base}/llm_ok", "ON" if ok else "OFF")
        self._publish(f"{base}/llm_calls", str(call_count))
        if last_call:
            summary = (
                f"{last_call.get('purpose', '?')} "
                f"{last_call.get('model', '?')} "
                f"{last_call.get('seconds', last_call.get('error', ''))}"
            )
        else:
            summary = "none"
        self._publish(f"{base}/llm_last", summary[:255])
        self._publish(f"{base}/llm_error", (error or "")[:255])
