"""Load Supervisor options and default room map."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


DEFAULT_ROOMS: list[dict[str, Any]] = [
    {
        "name": "keuken",
        "area_id": "keuken",
        "sensors": [
            {"entity_id": "binary_sensor.mmwave_keuken_presence", "adapter": "mmwave"},
            {"entity_id": "binary_sensor.radar_keuken_presence", "adapter": "radar"},
            {"entity_id": "binary_sensor.pir_keuken_occupancy", "adapter": "pir"},
            {"entity_id": "binary_sensor.pir_keuken_aanrecht_occupancy", "adapter": "pir"},
            {"entity_id": "binary_sensor.keuken_person_detected", "adapter": "frigate"},
            {"entity_id": "light.lampen_keuken", "adapter": "light"},
        ],
    },
    {
        "name": "gang",
        "area_id": "gang",
        "sensors": [
            {"entity_id": "binary_sensor.mmwave_gang_presence", "adapter": "mmwave"},
            {"entity_id": "binary_sensor.radar_gang_presence", "adapter": "radar"},
            {"entity_id": "binary_sensor.pir_gang_occupancy", "adapter": "pir"},
            {"entity_id": "binary_sensor.pir_gang_2_occupancy", "adapter": "pir"},
        ],
    },
    {
        "name": "overloop",
        "area_id": "overloop",
        "sensors": [
            {"entity_id": "binary_sensor.mmwave_overloop_presence", "adapter": "mmwave"},
            {"entity_id": "binary_sensor.pir_overloop_occupancy", "adapter": "pir"},
            {"entity_id": "binary_sensor.pir_overloop2_occupancy", "adapter": "pir"},
        ],
    },
    {
        "name": "wc",
        "area_id": "wc",
        "sensors": [
            {"entity_id": "binary_sensor.mmwave_wc_presence", "adapter": "mmwave"},
        ],
    },
    {
        "name": "computers",
        "area_id": "computers",
        "sensors": [
            {"entity_id": "binary_sensor.mmwave_computer_presence", "adapter": "mmwave"},
            {"entity_id": "binary_sensor.wave_pc_occupancy", "adapter": "mmwave"},
            {"entity_id": "light.lampen_computer", "adapter": "light"},
        ],
    },
    {
        "name": "voordeur",
        "area_id": "voor",
        "sensors": [
            {"entity_id": "binary_sensor.voordeur_person_occupancy", "adapter": "frigate"},
            {"entity_id": "binary_sensor.voordeur_motion", "adapter": "pir"},
            {"entity_id": "binary_sensor.voordeur_person", "adapter": "frigate"},
        ],
    },
    {
        "name": "achterhuis",
        "area_id": "achter",
        "sensors": [
            {"entity_id": "binary_sensor.achterhuis_person_occupancy", "adapter": "frigate"},
            {"entity_id": "binary_sensor.achterhuis_motion", "adapter": "pir"},
        ],
    },
]


class SensorRef(BaseModel):
    entity_id: str
    adapter: str = "generic"


class RoomConfig(BaseModel):
    name: str
    area_id: str | None = None
    sensors: list[SensorRef] = Field(default_factory=list)
    soft_entities: list[str] = Field(default_factory=list)


class Options(BaseModel):
    ha_url: str = "http://homeassistant:8123"
    ha_token: str = ""
    llm_base_url: str = "http://192.168.1.10:1234/v1"
    llm_api_key: str = "lmstudio"
    model_fast: str = "nvidia-nemotron-3-nano-4b"
    model_reason: str = "google/gemma-4-12b"
    mqtt_host: str = "core-mosquitto"
    mqtt_port: int = 1883
    mqtt_user: str = ""
    mqtt_password: str = ""
    mqtt_discovery_prefix: str = "homeassistant"
    mqtt_state_prefix: str = "lhai"
    poll_seconds: int = 15
    learn_enabled: bool = True
    confidence_escalate: float = 0.55
    rooms: list[RoomConfig] = Field(default_factory=list)
    persons: list[str] = Field(
        default_factory=lambda: [
            "person.bjorn_reints",
            "person.eva_reints",
            "person.jannie",
        ]
    )


def normalize_llm_base_url(url: str) -> str:
    """Ensure LM Studio URL has a port (default 1234) and ends with /v1."""
    raw = (url or "").strip().rstrip("/")
    if not raw:
        return "http://192.168.1.10:1234/v1"
    if "://" not in raw:
        raw = "http://" + raw
    parsed = urlparse(raw)
    host = parsed.hostname or ""
    port = parsed.port
    scheme = parsed.scheme or "http"
    path = parsed.path or ""

    # Common misconfig: http://10.x.x.x/v1 without :1234
    if port is None and host and scheme in {"http", "https"}:
        # Keep explicit 80/443 only if user wrote them; missing port → LM Studio 1234
        port = 1234
        logger.warning(
            "llm_base_url had no port; assuming LM Studio default :1234 → %s://%s:1234...",
            scheme,
            host,
        )

    if not path or path == "/":
        path = "/v1"
    elif not path.rstrip("/").endswith("/v1"):
        path = path.rstrip("/") + "/v1"

    netloc = host
    if port:
        netloc = f"{host}:{port}"
    fixed = urlunparse((scheme, netloc, path, "", "", ""))
    return fixed.rstrip("/")


def load_options() -> Options:
    path = Path(os.environ.get("LHAI_OPTIONS_PATH", "/data/options.json"))
    raw: dict[str, Any] = {}
    if path.is_file():
        raw = json.loads(path.read_text(encoding="utf-8"))
    opts = Options.model_validate(raw)
    original = opts.llm_base_url
    opts.llm_base_url = normalize_llm_base_url(opts.llm_base_url)
    if opts.llm_base_url != original.rstrip("/"):
        logger.warning("Normalized llm_base_url: %s -> %s", original, opts.llm_base_url)
    if not opts.rooms:
        opts.rooms = [RoomConfig.model_validate(r) for r in DEFAULT_ROOMS]
    return opts


def data_dir() -> Path:
    path = Path(os.environ.get("LHAI_DATA_DIR", "/data"))
    path.mkdir(parents=True, exist_ok=True)
    return path
