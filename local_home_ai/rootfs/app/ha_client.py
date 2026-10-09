"""Home Assistant REST + WebSocket client."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import orjson
import websockets
from websockets.asyncio.client import ClientConnection

logger = logging.getLogger(__name__)

StateHandler = Callable[[dict[str, Any]], Awaitable[None]]


class HomeAssistantClient:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._states: dict[str, dict[str, Any]] = {}
        self._handlers: list[StateHandler] = []
        self._ws_task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._msg_id = 1

    @property
    def states(self) -> dict[str, dict[str, Any]]:
        return self._states

    def on_state(self, handler: StateHandler) -> None:
        self._handlers.append(handler)

    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    async def fetch_states(self) -> dict[str, dict[str, Any]]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{self.base_url}/api/states", headers=self.headers())
            resp.raise_for_status()
            items = resp.json()
        self._states = {item["entity_id"]: item for item in items}
        return self._states

    async def get_config(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{self.base_url}/api/config", headers=self.headers())
            resp.raise_for_status()
            return resp.json()

    def is_on(self, entity_id: str) -> bool:
        state = self._states.get(entity_id, {}).get("state")
        if state is None:
            return False
        return str(state).lower() in {
            "on",
            "home",
            "occupied",
            "detected",
            "open",
            "playing",
        }

    def state_value(self, entity_id: str) -> str | None:
        item = self._states.get(entity_id)
        if not item:
            return None
        return str(item.get("state"))

    def persons_home(self, person_entities: list[str]) -> list[str]:
        return [
            entity_id
            for entity_id in person_entities
            if self.state_value(entity_id) == "home"
        ]

    async def start_websocket(self) -> None:
        if not self.token:
            logger.warning("HA token empty; WebSocket disabled")
            return
        self._stop.clear()
        self._ws_task = asyncio.create_task(self._ws_loop(), name="ha-websocket")

    async def stop(self) -> None:
        self._stop.set()
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
            self._ws_task = None

    def _ws_url(self) -> str:
        if self.base_url.startswith("https://"):
            return "wss://" + self.base_url[len("https://") :] + "/api/websocket"
        if self.base_url.startswith("http://"):
            return "ws://" + self.base_url[len("http://") :] + "/api/websocket"
        return self.base_url.rstrip("/") + "/api/websocket"

    async def _ws_loop(self) -> None:
        url = self._ws_url()
        while not self._stop.is_set():
            try:
                async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                    await self._authenticate(ws)
                    await self._subscribe_states(ws)
                    logger.info("Connected to Home Assistant WebSocket")
                    async for raw in ws:
                        if self._stop.is_set():
                            break
                        await self._handle_message(raw)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("HA WebSocket error: %s; reconnecting in 5s", exc)
                await asyncio.sleep(5)

    async def _authenticate(self, ws: ClientConnection) -> None:
        await ws.recv()
        await ws.send(orjson.dumps({"type": "auth", "access_token": self.token}).decode())
        auth_ok = await ws.recv()
        data = orjson.loads(auth_ok)
        if data.get("type") != "auth_ok":
            raise RuntimeError(f"HA auth failed: {data}")

    async def _subscribe_states(self, ws: ClientConnection) -> None:
        msg_id = self._next_id()
        await ws.send(
            orjson.dumps(
                {
                    "id": msg_id,
                    "type": "subscribe_events",
                    "event_type": "state_changed",
                }
            ).decode()
        )

    def _next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    async def _handle_message(self, raw: str | bytes) -> None:
        data = orjson.loads(raw)
        if data.get("type") != "event":
            return
        event = data.get("event") or {}
        if event.get("event_type") != "state_changed":
            return
        new_state = (event.get("data") or {}).get("new_state")
        if not new_state or "entity_id" not in new_state:
            return
        entity_id = new_state["entity_id"]
        self._states[entity_id] = new_state
        for handler in self._handlers:
            try:
                await handler(new_state)
            except Exception as exc:  # noqa: BLE001
                logger.exception("State handler failed for %s: %s", entity_id, exc)
