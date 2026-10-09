"""LM Studio OpenAI-compatible client with dual-model routing."""

from __future__ import annotations

import logging
import re
from typing import Any, Literal

import httpx
import orjson

logger = logging.getLogger(__name__)

ModelKind = Literal["fast", "reason"]


class LLMClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model_fast: str,
        model_reason: str,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or "lmstudio"
        self.model_fast = model_fast
        self.model_reason = model_reason
        self.last_error: str | None = None
        self.available = False

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def health(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self.base_url}/models", headers=self._headers())
                resp.raise_for_status()
                payload = resp.json()
            models = [m.get("id") for m in payload.get("data", []) if isinstance(m, dict)]
            self.available = True
            self.last_error = None
            return {"ok": True, "models": models}
        except Exception as exc:  # noqa: BLE001
            self.available = False
            self.last_error = str(exc)
            return {"ok": False, "error": str(exc), "models": []}

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        kind: ModelKind = "fast",
        temperature: float = 0.2,
        max_tokens: int = 400,
    ) -> str | None:
        model = self.model_fast if kind == "fast" else self.model_reason
        body = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    content=orjson.dumps(body),
                )
                resp.raise_for_status()
                data = resp.json()
            content = data["choices"][0]["message"]["content"]
            self.available = True
            self.last_error = None
            return str(content)
        except Exception as exc:  # noqa: BLE001
            self.available = False
            self.last_error = str(exc)
            logger.warning("LLM chat failed (%s / %s): %s", kind, model, exc)
            return None

    async def attribute_person(
        self,
        *,
        room: str,
        features: dict[str, float],
        persons_home: list[str],
        memory_snippets: list[str],
        escalate_below: float,
    ) -> dict[str, Any]:
        """Ask the LLM who is likely in a room. Returns person/confidence/reason."""
        if not persons_home:
            return {
                "person": "unknown",
                "confidence": 0.0,
                "reason": "nobody home",
                "model": None,
            }

        if len(persons_home) == 1:
            return {
                "person": persons_home[0],
                "confidence": 0.7,
                "reason": "only one person home",
                "model": "heuristic",
            }

        system = (
            "You attribute room occupancy in a Dutch home. "
            "Reply with ONLY compact JSON: "
            '{"person":"<entity_id or unknown>","confidence":0.0-1.0,"reason":"..."} '
            "Pick person only from the provided home list."
        )
        memory = "\n".join(f"- {s}" for s in memory_snippets[:8]) or "- none"
        user = (
            f"Room: {room}\n"
            f"Persons home: {', '.join(persons_home)}\n"
            f"Sensor features: {orjson.dumps(features).decode()}\n"
            f"Recent memory:\n{memory}\n"
        )
        text = await self.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            kind="fast",
        )
        parsed = self._parse_json(text) if text else None
        model_used: str | None = self.model_fast

        confidence = float((parsed or {}).get("confidence") or 0.0)
        if parsed is None or confidence < escalate_below:
            text = await self.chat(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user + "\nUse careful reasoning."},
                ],
                kind="reason",
                max_tokens=500,
            )
            parsed = self._parse_json(text) if text else parsed
            model_used = self.model_reason

        if not parsed:
            return {
                "person": "unknown",
                "confidence": 0.0,
                "reason": self.last_error or "llm unavailable",
                "model": model_used,
            }

        person = str(parsed.get("person") or "unknown")
        if person not in persons_home and person != "unknown":
            person = "unknown"
        return {
            "person": person,
            "confidence": float(parsed.get("confidence") or 0.0),
            "reason": str(parsed.get("reason") or ""),
            "model": model_used,
        }

    @staticmethod
    def _parse_json(text: str | None) -> dict[str, Any] | None:
        if not text:
            return None
        cleaned = text.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            data = orjson.loads(cleaned)
            if isinstance(data, dict):
                return data
        except orjson.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    data = orjson.loads(match.group(0))
                    if isinstance(data, dict):
                        return data
                except orjson.JSONDecodeError:
                    return None
        return None
