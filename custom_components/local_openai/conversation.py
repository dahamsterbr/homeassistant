"""Conversation agent backed by an OpenAI-compatible LM Studio server."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal

from homeassistant.components import conversation
from homeassistant.components.conversation import ConversationEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import intent, llm, template
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_MODEL,
    CONF_PROMPT,
    DEFAULT_PROMPT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

WEATHER_HINT = re.compile(
    r"\b(weer|weather|forecast|voorspelling|temperatuur|temperature|regen|rain|"
    r"buienradar|zonnig|wind)\b",
    re.I,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([LocalOpenAIAgent(config_entry)])


class LocalOpenAIAgent(conversation.ConversationEntity):
    """Assist agent that talks to LM Studio."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supports_streaming = False

    def __init__(self, entry: ConfigEntry) -> None:
        super().__init__()
        self.entry = entry
        self._attr_unique_id = entry.entry_id
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Local OpenAI",
            "manufacturer": "LM Studio",
            "model": entry.data.get(CONF_MODEL, "local"),
        }
        self._history: dict[str, list[dict[str, Any]]] = {}

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        return MATCH_ALL

    @property
    def supported_features(self) -> ConversationEntityFeature:
        return ConversationEntityFeature.CONTROL

    async def async_process(
        self, user_input: conversation.ConversationInput
    ) -> conversation.ConversationResult:
        options = self.entry.data
        base_url = str(options[CONF_BASE_URL]).rstrip("/")
        api_key = options.get(CONF_API_KEY) or "lmstudio"
        model = options[CONF_MODEL]
        raw_prompt = options.get(CONF_PROMPT) or DEFAULT_PROMPT

        conversation_id = user_input.conversation_id or (
            user_input.context.id if user_input.context else None
        )
        if not conversation_id:
            conversation_id = "default"
        history = list(self._history.get(conversation_id, []))

        api = await self._get_assist_api(user_input)

        try:
            prompt = template.Template(raw_prompt, self.hass).async_render(
                {"ha_name": self.hass.config.location_name},
                parse_result=False,
            )
        except Exception:  # noqa: BLE001
            prompt = str(raw_prompt)

        prompt = (
            f"{prompt}\n\n"
            "You have Home Assistant tools for live home data and device control. "
            "For weather, forecasts, temperatures, or sensor values: ALWAYS call tools "
            "(GetLiveContext / weather / entity tools) before answering. "
            "Never invent weather. You do NOT have open internet search; "
            "use Home Assistant entities and tools only. Prefer Dutch when the user does."
        )
        if api and getattr(api, "api_prompt", None):
            prompt = f"{prompt}\n\n{api.api_prompt}"

        # Inject weather entity snapshot so small local models can answer without tools
        live_bits = await self._live_context_snippet(user_input.text)
        if live_bits:
            prompt = f"{prompt}\n\nLive Home Assistant context:\n{live_bits}"

        messages: list[dict[str, Any]] = [{"role": "system", "content": prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_input.text})

        tools = _convert_tools(getattr(api, "tools", None), self.hass) if api else None
        if tools:
            _LOGGER.debug("Exposing %s Assist tools to LM Studio", len(tools))

        try:
            content = await self._tool_loop(
                base_url, api_key, model, messages, tools, api
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("LM Studio request failed")
            raise HomeAssistantError(f"LM Studio error: {err}") from err

        history.append({"role": "user", "content": user_input.text})
        history.append({"role": "assistant", "content": content or "OK"})
        self._history[conversation_id] = history[-20:]

        intent_response = intent.IntentResponse(language=user_input.language)
        intent_response.async_set_speech(content or "OK")
        return conversation.ConversationResult(
            response=intent_response,
            conversation_id=conversation_id,
        )

    async def _tool_loop(
        self,
        base_url: str,
        api_key: str,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        api: llm.APIInstance | None,
        max_rounds: int = 6,
    ) -> str:
        content = ""
        for round_i in range(max_rounds):
            force_tools = bool(tools) and round_i == 0 and WEATHER_HINT.search(
                messages[-1].get("content", "")
            )
            content, tool_calls = await self.hass.async_add_executor_job(
                _chat_completion,
                base_url,
                api_key,
                model,
                messages,
                tools if round_i < max_rounds - 1 else None,
                "required" if force_tools else ("auto" if tools else None),
            )
            if not tool_calls or not api or not hasattr(api, "async_call_tool"):
                return content or "OK"

            messages.append(
                {
                    "role": "assistant",
                    "content": content or "",
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc.get("arguments") or {}),
                            },
                        }
                        for tc in tool_calls
                    ],
                }
            )
            for tc in tool_calls:
                tool_input = llm.ToolInput(
                    tool_name=tc["name"],
                    tool_args=tc.get("arguments") or {},
                )
                try:
                    tool_result = await api.async_call_tool(tool_input)
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning("Tool %s failed: %s", tc["name"], err)
                    tool_result = {"error": str(err)}
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(tool_result, default=str),
                    }
                )
        return content or "OK"

    async def _live_context_snippet(self, text: str) -> str:
        """Pull weather / forecast states so answers work even without tool-calls."""
        if not WEATHER_HINT.search(text or ""):
            return ""
        lines: list[str] = []
        for state in self.hass.states.async_all("weather"):
            attrs = state.attributes or {}
            lines.append(
                f"- {state.entity_id}: {state.state}, "
                f"temp={attrs.get('temperature')}{attrs.get('temperature_unit', '')}, "
                f"humidity={attrs.get('humidity')}, "
                f"wind={attrs.get('wind_speed')}"
            )
            forecast = attrs.get("forecast")
            if isinstance(forecast, list) and forecast:
                first = forecast[0]
                lines.append(
                    f"  next: {first.get('datetime') or first.get('datetime')} "
                    f"cond={first.get('condition')} temp={first.get('temperature')}"
                )
        # Also common NL weather sensors
        for eid in list(self.hass.states.async_entity_ids("sensor")):
            if any(k in eid for k in ("buienradar", "weather", "temperature_outside", "neerslag")):
                st = self.hass.states.get(eid)
                if st:
                    lines.append(f"- {eid}: {st.state} {st.attributes.get('unit_of_measurement', '')}")
            if len(lines) > 40:
                break
        return "\n".join(lines[:40])

    async def _get_assist_api(
        self, user_input: conversation.ConversationInput
    ) -> llm.APIInstance | None:
        candidates: list[dict[str, Any]] = [
            {
                "platform": DOMAIN,
                "context": user_input.context,
                "language": user_input.language,
                "assistant": user_input.agent_id,
                "device_id": user_input.device_id,
            },
            {
                "platform": DOMAIN,
                "context": user_input.context,
                "user_prompt": user_input.text,
                "language": user_input.language,
                "assistant": user_input.agent_id,
                "device_id": user_input.device_id,
            },
        ]
        for kwargs in candidates:
            try:
                llm_context = llm.LLMContext(**kwargs)
            except TypeError:
                continue
            try:
                api = await llm.async_get_api(
                    self.hass, llm.LLM_API_ASSIST, llm_context
                )
                _LOGGER.debug(
                    "Assist API ready with %s tools",
                    len(getattr(api, "tools", []) or []),
                )
                return api
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Assist LLM API attempt failed", exc_info=True)
        return None


def _convert_tools(
    tools: list[Any] | None, hass: HomeAssistant | None = None
) -> list[dict[str, Any]] | None:
    if not tools:
        return None
    converted: list[dict[str, Any]] = []
    custom_serializer = None
    if hass is not None:
        try:
            custom_serializer = llm.async_get_custom_serializer(hass)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            custom_serializer = None

    for tool in tools:
        parameters = getattr(tool, "parameters", None)
        schema: dict[str, Any]
        if hasattr(parameters, "model_json_schema"):
            schema = parameters.model_json_schema()
        elif isinstance(parameters, dict):
            schema = parameters
        else:
            try:
                from voluptuous_openapi import convert

                schema = convert(parameters, custom_serializer=custom_serializer)
            except Exception:  # noqa: BLE001
                schema = {"type": "object", "properties": {}}
        converted.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": getattr(tool, "description", None) or "",
                    "parameters": schema,
                },
            }
        )
    return converted


def _chat_completion(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    tool_choice: str | None = "auto",
) -> tuple[str, list[dict[str, Any]]]:
    from openai import OpenAI

    client = OpenAI(base_url=base_url, api_key=api_key)
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
    }
    if tools:
        kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
    try:
        response = client.chat.completions.create(**kwargs)
    except Exception:
        # Some local servers reject tool_choice=required
        if "tool_choice" in kwargs:
            kwargs.pop("tool_choice", None)
            response = client.chat.completions.create(**kwargs)
        else:
            raise
    message = response.choices[0].message
    content = message.content or ""
    # Strip thinking tags from reasoning models
    content = re.sub(r"<think>[\s\S]*?</think>", "", content, flags=re.I).strip()
    parsed_tools: list[dict[str, Any]] = []
    if message.tool_calls:
        for tc in message.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            parsed_tools.append(
                {"id": tc.id, "name": tc.function.name, "arguments": args}
            )
    return content, parsed_tools
