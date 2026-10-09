"""Local Home AI FastAPI service."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from .config import data_dir, load_options
from .fusion import FusionEngine
from .ha_client import HomeAssistantClient
from .llm_client import LLMClient
from .memory import MemoryStore
from .mqtt_pub import MqttPublisher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("local_home_ai")

engine: FusionEngine | None = None
ha_client: HomeAssistantClient | None = None
llm_client: LLMClient | None = None
memory: MemoryStore | None = None
mqtt: MqttPublisher | None = None
worker_task: asyncio.Task[None] | None = None
status: dict[str, Any] = {"started": False}


async def _worker(options_poll: int) -> None:
    assert engine is not None
    assert ha_client is not None
    assert llm_client is not None
    while True:
        try:
            if not ha_client.states:
                await ha_client.fetch_states()
            await llm_client.health()
            results = await engine.evaluate_all()
            status.update(
                {
                    "started": True,
                    "rooms": len(results),
                    "llm_ok": llm_client.available,
                    "llm_error": llm_client.last_error,
                    "snapshot": engine.snapshot(),
                    "memory": memory.stats() if memory else {},
                }
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Worker loop error: %s", exc)
            status["last_error"] = str(exc)
        await asyncio.sleep(options_poll)


@asynccontextmanager
async def lifespan(_: FastAPI):
    global engine, ha_client, llm_client, memory, mqtt, worker_task

    options = load_options()
    logger.info(
        "Loaded options: rooms=%s llm=%s mqtt=%s",
        len(options.rooms),
        options.llm_base_url,
        options.mqtt_host,
    )
    if ":1234" not in options.llm_base_url and "localhost" not in options.llm_base_url:
        logger.info("Tip: LM Studio default API is http://<ip>:1234/v1")

    memory = MemoryStore(data_dir() / "lhai.db")
    ha_client = HomeAssistantClient(options.ha_url, options.ha_token)
    llm_client = LLMClient(
        options.llm_base_url,
        options.llm_api_key,
        options.model_fast,
        options.model_reason,
    )
    mqtt = MqttPublisher(
        options.mqtt_host,
        options.mqtt_port,
        options.mqtt_user,
        options.mqtt_password,
        options.mqtt_discovery_prefix,
        options.mqtt_state_prefix,
    )
    mqtt.start()

    engine = FusionEngine(options, ha_client, llm_client, memory, mqtt)

    async def on_state(_: dict[str, Any]) -> None:
        # Debounced evaluation happens in the worker; state cache is updated by HA client.
        return

    ha_client.on_state(on_state)

    try:
        if options.ha_token:
            await ha_client.fetch_states()
            await ha_client.start_websocket()
        else:
            logger.warning("ha_token is empty — set it in add-on options")
    except Exception as exc:  # noqa: BLE001
        logger.error("Initial HA fetch failed: %s", exc)
        status["last_error"] = str(exc)

    worker_task = asyncio.create_task(
        _worker(options.poll_seconds),
        name="lhai-worker",
    )
    status["started"] = True
    yield

    if worker_task:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
    if ha_client:
        await ha_client.stop()
    if mqtt:
        mqtt.stop()
    if memory:
        memory.close()


app = FastAPI(title="Local Home AI", version="1.0.1", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, Any]:
    llm_info = await llm_client.health() if llm_client else {"ok": False}
    return {
        "status": "ok" if status.get("started") else "starting",
        "llm": llm_info,
        "memory": memory.stats() if memory else {},
        "rooms": engine.snapshot() if engine else {},
    }


@app.get("/status")
async def get_status() -> dict[str, Any]:
    return status


@app.post("/evaluate")
async def evaluate_now() -> dict[str, Any]:
    if not engine or not ha_client:
        return {"ok": False, "error": "not ready"}
    await ha_client.fetch_states()
    results = await engine.evaluate_all()
    return {
        "ok": True,
        "rooms": [
            {
                "room": r.room,
                "occupied": r.occupied,
                "confidence": r.confidence,
                "person": r.person,
                "reason": r.reason,
            }
            for r in results
        ],
    }
