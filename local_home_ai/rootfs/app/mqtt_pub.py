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

    def ensure_room_discovery(self, room: str, friendly: str | None = None) -> None:
        if room in self._discovered:
            return
        name = friendly or room.replace("_", " ").title()
        object_id = f"lhai_{room}"
        base = f"{self.state_prefix}/{room}"

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
            "device": {
                "identifiers": ["local_home_ai"],
                "name": "Local Home AI",
                "manufacturer": "Local",
                "model": "Presence Fusion",
            },
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
            "device": occupied["device"],
        }
        person = {
            "name": f"LHAI {name} Likely Person",
            "unique_id": f"{object_id}_likely_person",
            "state_topic": f"{base}/likely_person",
            "availability_topic": f"{self.state_prefix}/status",
            "payload_available": "online",
            "payload_not_available": "offline",
            "device": occupied["device"],
        }
        reason = {
            "name": f"LHAI {name} Reason",
            "unique_id": f"{object_id}_reason",
            "state_topic": f"{base}/reason",
            "availability_topic": f"{self.state_prefix}/status",
            "payload_available": "online",
            "payload_not_available": "offline",
            "device": occupied["device"],
        }

        prefix = self.discovery_prefix
        self._publish(f"{prefix}/binary_sensor/{object_id}_occupied/config", occupied)
        self._publish(f"{prefix}/sensor/{object_id}_confidence/config", confidence)
        self._publish(f"{prefix}/sensor/{object_id}_likely_person/config", person)
        self._publish(f"{prefix}/sensor/{object_id}_reason/config", reason)
        self._publish(f"{self.state_prefix}/status", "online")
        self._discovered.add(room)

    def publish_room(
        self,
        room: str,
        *,
        occupied: bool,
        confidence: float,
        person: str,
        reason: str,
    ) -> None:
        self.ensure_room_discovery(room)
        base = f"{self.state_prefix}/{room}"
        self._publish(f"{base}/occupied", "ON" if occupied else "OFF")
        self._publish(f"{base}/confidence", f"{round(confidence * 100, 1)}")
        self._publish(f"{base}/likely_person", person or "unknown")
        self._publish(f"{base}/reason", (reason or "")[:255])
