"""Config flow for Local OpenAI / LM Studio."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_ENABLED,
    CONF_LOG_PROMPTS,
    CONF_MODEL,
    CONF_PROMPT,
    DEFAULT_API_KEY,
    DEFAULT_BASE_URL,
    DEFAULT_ENABLED,
    DEFAULT_LOG_PROMPTS,
    DEFAULT_MODEL,
    DEFAULT_NAME,
    DEFAULT_PROMPT,
    DOMAIN,
)


def _user_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_BASE_URL, default=d.get(CONF_BASE_URL, DEFAULT_BASE_URL)
            ): str,
            vol.Optional(
                CONF_API_KEY, default=d.get(CONF_API_KEY, DEFAULT_API_KEY)
            ): str,
            vol.Required(CONF_MODEL, default=d.get(CONF_MODEL, DEFAULT_MODEL)): str,
            vol.Optional(
                CONF_PROMPT, default=d.get(CONF_PROMPT, DEFAULT_PROMPT)
            ): selector.TemplateSelector(),
            vol.Optional(
                CONF_ENABLED, default=d.get(CONF_ENABLED, DEFAULT_ENABLED)
            ): bool,
            vol.Optional(
                CONF_LOG_PROMPTS, default=d.get(CONF_LOG_PROMPTS, DEFAULT_LOG_PROMPTS)
            ): bool,
        }
    )


async def _validate(hass: HomeAssistant, data: dict[str, Any]) -> None:
    if not data.get(CONF_BASE_URL):
        raise ValueError("base_url required")
    if not data.get(CONF_MODEL):
        raise ValueError("model required")


class LocalOpenAIConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await _validate(self.hass, user_input)
            except ValueError:
                errors["base"] = "invalid"
            else:
                await self.async_set_unique_id(
                    f"{user_input[CONF_BASE_URL]}|{user_input[CONF_MODEL]}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=DEFAULT_NAME, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return LocalOpenAIOptionsFlow(config_entry)


class LocalOpenAIOptionsFlow(config_entries.OptionsFlow):
    """Configure enable/disable and prompt logging without re-adding the integration."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            # Keep connection fields in data; store toggles in options + merge into data
            data = {**self.config_entry.data, **user_input}
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=data, options=user_input
            )
            return self.async_create_entry(title="", data=user_input)

        merged = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=_user_schema(merged),
        )
