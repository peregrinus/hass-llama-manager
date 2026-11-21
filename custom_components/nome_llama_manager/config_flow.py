"""Config flow for Nome-LLama-Manager."""

from __future__ import annotations

import logging
from datetime import timedelta

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.update_coordinator import UpdateFailed

from .api import LlamaAuthError, LlamaManagerClient
from .const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_UPDATE_INTERVAL,
    DEFAULT_BASE_URL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MAX_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_BASE_URL, default=DEFAULT_BASE_URL): str,
        vol.Required(CONF_API_KEY): str,
        vol.Required(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): vol.All(
            int, vol.Range(MIN_UPDATE_INTERVAL, MAX_UPDATE_INTERVAL)
        ),
    }
)


async def _validate(hass, base_url: str, api_key: str) -> None:
    """Check the llama-manager URL and API key actually work."""
    client = LlamaManagerClient(
        aiohttp_client.async_get_clientsession(hass), base_url, api_key
    )
    await client.get_health()
    await client.get_models()


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow for Nome-LLama-Manager."""

    async def async_step_user(self, user_input: dict | None = None):
        """Ask for the llama-manager URL, API key and update interval."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await _validate(
                    self.hass, user_input[CONF_BASE_URL], user_input[CONF_API_KEY]
                )
            except LlamaAuthError:
                errors["base"] = "llama-manager rejected the API key"
            except (UpdateFailed, aiohttp.ClientError) as err:
                errors["base"] = f"Unable to reach llama-manager: {err}"
            else:
                return self.async_create_entry(
                    title="Nome-LLama-Manager",
                    data={
                        CONF_BASE_URL: user_input[CONF_BASE_URL],
                        CONF_API_KEY: user_input[CONF_API_KEY],
                        CONF_UPDATE_INTERVAL: user_input[CONF_UPDATE_INTERVAL],
                    },
                )
        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )

    async def async_step_init(self, user_input: dict | None = None):
        """Options flow: edit URL, API key and update interval."""
        errors: dict[str, str] = {}
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if user_input is not None:
            try:
                await _validate(
                    self.hass, user_input[CONF_BASE_URL], user_input[CONF_API_KEY]
                )
            except LlamaAuthError:
                errors["base"] = "llama-manager rejected the API key"
            except (UpdateFailed, aiohttp.ClientError) as err:
                errors["base"] = f"Unable to reach llama-manager: {err}"
            else:
                self.hass.config_entries.async_update_entry(
                    entry,
                    data={
                        CONF_BASE_URL: user_input[CONF_BASE_URL],
                        CONF_API_KEY: user_input[CONF_API_KEY],
                        CONF_UPDATE_INTERVAL: user_input[CONF_UPDATE_INTERVAL],
                    },
                )
                coordinator = self.hass.data[DOMAIN][entry.entry_id]["coordinator"]
                coordinator.update_interval = timedelta(
                    seconds=user_input[CONF_UPDATE_INTERVAL]
                )
                return self.async_create_entry(title="", data={})
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(DATA_SCHEMA, entry.data),
            errors=errors,
        )
