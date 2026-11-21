"""The Nome-LLama-Manager integration.

Creates Home Assistant sensors from the llama-manager Flask API:
system status, per-GPU temperature / fan speed / memory utilisation,
per-GPU VRAM, the currently running model and its latest prompt speed.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .api import LlamaManagerCoordinator
from .const import CONF_API_KEY, CONF_BASE_URL, CONF_UPDATE_INTERVAL, DOMAIN, NAME

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Nome-LLama-Manager from a config entry."""
    coordinator = LlamaManagerCoordinator(
        hass,
        base_url=entry.data[CONF_BASE_URL],
        api_key=entry.data.get(CONF_API_KEY, ""),
        update_interval=entry.data.get(CONF_UPDATE_INTERVAL, 60),
    )
    await coordinator.async_refresh()

    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=NAME,
        manufacturer="Nome",
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"coordinator": coordinator}

    return await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Nome-LLama-Manager config entry."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    hass.data[DOMAIN].pop(entry.entry_id, None)
    return True
