"""Conversation agent backed by an OpenAI-compatible LM Studio server."""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

from homeassistant.components import conversation
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

        if api and getattr(api, "api_prompt", None):
            prompt = f"{prompt}\n\n{api.api_prompt}"

        messages: list[dict[str, Any]] = [{"role": "system", "content": prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_input.text})

        tools = _convert_tools(getattr(api, "tools", None)) if api else None

        try:
            content, tool_calls = await self.hass.async_add_executor_job(
                _chat_completion, base_url, api_key, model, messages, tools
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("LM Studio request failed")
            raise HomeAssistantError(f"LM Studio error: {err}") from err

        if tool_calls and api and hasattr(api, "async_call_tool"):
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
                    tool_result = {"error": str(err)}
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(tool_result, default=str),
                    }
                )
            try:
                content, _ = await self.hass.async_add_executor_job(
                    _chat_completion, base_url, api_key, model, messages, None
                )
            except Exception as err:  # noqa: BLE001
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

    async def _get_assist_api(
        self, user_input: conversation.ConversationInput
    ) -> llm.APIInstance | None:
        try:
            llm_context = llm.LLMContext(
                platform=DOMAIN,
                context=user_input.context,
                language=user_input.language,
                assistant=user_input.agent_id,
                device_id=user_input.device_id,
            )
        except TypeError:
            try:
                llm_context = llm.LLMContext(
                    platform=DOMAIN,
                    context=user_input.context,
                    user_prompt=user_input.text,
                    language=user_input.language,
                    assistant=user_input.agent_id,
                    device_id=user_input.device_id,
                )
            except TypeError:
                return None
        try:
            return await llm.async_get_api(self.hass, llm.LLM_API_ASSIST, llm_context)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Assist LLM API unavailable", exc_info=True)
            return None


def _convert_tools(tools: list[Any] | None) -> list[dict[str, Any]] | None:
    if not tools:
        return None
    converted: list[dict[str, Any]] = []
    for tool in tools:
        parameters = getattr(tool, "parameters", None)
        if hasattr(parameters, "model_json_schema"):
            schema = parameters.model_json_schema()
        elif isinstance(parameters, dict):
            schema = parameters
        else:
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
) -> tuple[str, list[dict[str, Any]]]:
    from openai import OpenAI

    client = OpenAI(base_url=base_url, api_key=api_key)
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.3,
    }
    if tools:
        kwargs["tools"] = tools
    response = client.chat.completions.create(**kwargs)
    message = response.choices[0].message
    content = message.content or ""
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
