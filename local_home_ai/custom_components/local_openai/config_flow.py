"""Config flow for Local OpenAI / LM Studio."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_MODEL,
    CONF_PROMPT,
    DEFAULT_API_KEY,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    DEFAULT_NAME,
    DEFAULT_PROMPT,
    DOMAIN,
)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_BASE_URL, default=DEFAULT_BASE_URL): str,
        vol.Optional(CONF_API_KEY, default=DEFAULT_API_KEY): str,
        vol.Required(CONF_MODEL, default=DEFAULT_MODEL): str,
        vol.Optional(CONF_PROMPT, default=DEFAULT_PROMPT): selector.TemplateSelector(),
    }
)


async def _validate(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Best-effort validation; connection errors surface at conversation time."""
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
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
