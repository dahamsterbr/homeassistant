"""LM Studio OpenAI-compatible client with dual-model routing."""

from __future__ import annotations

import logging
import re
import time
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
        self.call_count = 0
        self.last_call: dict[str, Any] | None = None
        self.models_available: list[str] = []

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _resolve_model(self, requested: str) -> str:
        """Pick the best matching loaded model id from LM Studio."""
        if not self.models_available:
            return requested
        if requested in self.models_available:
            return requested
        req_l = requested.lower()
        for mid in self.models_available:
            if req_l in mid.lower() or mid.lower() in req_l:
                logger.info("Resolved model %s -> %s", requested, mid)
                return mid
        # Prefer any loaded model rather than failing hard
        logger.warning(
            "Model %s not in LM Studio list %s; using %s",
            requested,
            self.models_available,
            self.models_available[0],
        )
        return self.models_available[0]

    async def health(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self.base_url}/models", headers=self._headers())
                resp.raise_for_status()
                payload = resp.json()
            models = [m.get("id") for m in payload.get("data", []) if isinstance(m, dict)]
            self.models_available = [m for m in models if m]
            self.available = True
            self.last_error = None
            return {
                "ok": True,
                "models": self.models_available,
                "call_count": self.call_count,
                "last_call": self.last_call,
            }
        except Exception as exc:  # noqa: BLE001
            self.available = False
            self.last_error = str(exc)
            hint = ""
            if "All connection attempts failed" in str(exc) or "ConnectError" in type(exc).__name__:
                hint = (
                    f" Cannot reach {self.base_url}. "
                    "Use http://<LM-Studio-PC-IP>:1234/v1, enable server on 0.0.0.0, "
                    "and allow the HA host through the firewall."
                )
            return {
                "ok": False,
                "error": str(exc) + hint,
                "models": [],
                "call_count": self.call_count,
                "last_call": self.last_call,
            }

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        kind: ModelKind = "fast",
        temperature: float = 0.2,
        max_tokens: int = 400,
        purpose: str = "chat",
    ) -> str | None:
        requested = self.model_fast if kind == "fast" else self.model_reason
        model = self._resolve_model(requested)
        body = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        started = time.time()
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
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
            self.call_count += 1
            self.last_call = {
                "purpose": purpose,
                "kind": kind,
                "model": model,
                "seconds": round(time.time() - started, 2),
                "ts": time.time(),
            }
            logger.info(
                "LLM OK purpose=%s kind=%s model=%s took=%.2fs",
                purpose,
                kind,
                model,
                self.last_call["seconds"],
            )
            return str(content)
        except Exception as exc:  # noqa: BLE001
            self.available = False
            self.last_error = str(exc)
            self.last_call = {
                "purpose": purpose,
                "kind": kind,
                "model": model,
                "error": str(exc),
                "ts": time.time(),
            }
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
        force_llm: bool = True,
    ) -> dict[str, Any]:
        """Ask the LLM who is likely in a room. Always uses LM Studio when possible."""
        if not persons_home:
            # Still ask the model for a short empty-home judgement when forced
            if not force_llm:
                return {
                    "person": "unknown",
                    "confidence": 0.0,
                    "reason": "nobody home",
                    "model": "heuristic",
                }

        system = (
            "You attribute room occupancy in a Dutch smart home. "
            "Reply with ONLY compact JSON (no markdown): "
            '{"person":"<entity_id or unknown>","confidence":0.0-1.0,"reason":"short"} '
            "Pick person only from the provided home list, or unknown. "
            "Use sensor features and memory. Dutch reason text is fine."
        )
        memory = "\n".join(f"- {s}" for s in memory_snippets[:8]) or "- none"
        active = [k for k, v in features.items() if v and v > 0]
        user = (
            f"Room: {room}\n"
            f"Persons home: {', '.join(persons_home) if persons_home else 'none'}\n"
            f"Active sensors: {', '.join(active) if active else 'none'}\n"
            f"All features: {orjson.dumps(features).decode()}\n"
            f"Recent memory:\n{memory}\n"
        )

        text = await self.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            kind="fast",
            purpose=f"attribute:{room}",
        )
        parsed = self._parse_json(text) if text else None
        model_used: str | None = self.model_fast

        confidence = float((parsed or {}).get("confidence") or 0.0)
        need_reason = parsed is None or confidence < escalate_below or len(persons_home) > 1
        if need_reason:
            text = await self.chat(
                [
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": user + "\nThink carefully, then output JSON only.",
                    },
                ],
                kind="reason",
                max_tokens=500,
                purpose=f"attribute_reason:{room}",
            )
            parsed = self._parse_json(text) if text else parsed
            model_used = self.model_reason

        if not parsed:
            # Heuristic fallback only when LLM failed
            if len(persons_home) == 1:
                return {
                    "person": persons_home[0],
                    "confidence": 0.55,
                    "reason": f"llm failed ({self.last_error}); only one person home",
                    "model": "heuristic_fallback",
                }
            return {
                "person": "unknown",
                "confidence": 0.0,
                "reason": self.last_error or "llm unavailable",
                "model": model_used,
            }

        person = str(parsed.get("person") or "unknown")
        # Accept friendly names mapped to entity ids
        if person not in persons_home and person != "unknown":
            pl = person.lower()
            matched = next(
                (
                    p
                    for p in persons_home
                    if pl in p.lower() or p.split(".", 1)[-1].replace("_", " ") in pl
                ),
                None,
            )
            person = matched or "unknown"

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
        # Strip common thinking tags from reasoning models
        cleaned = re.sub(r"<think>[\s\S]*?</think>", "", cleaned, flags=re.I).strip()
        try:
            data = orjson.loads(cleaned)
            if isinstance(data, dict):
                return data
        except orjson.JSONDecodeError:
            match = re.search(r"\{[^{}]*\}", cleaned, re.DOTALL)
            if match:
                try:
                    data = orjson.loads(match.group(0))
                    if isinstance(data, dict):
                        return data
                except orjson.JSONDecodeError:
                    return None
        return None
