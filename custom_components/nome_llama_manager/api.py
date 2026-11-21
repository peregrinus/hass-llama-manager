"""Async client and data coordinator for the llama-manager API.

llama-manager exposes:
  GET /health          -> {"ok": true}                (public, no key needed)
  GET /api/gpu-stats   -> {"devices": [{device_name, temp, fan_speed,
                                        power_draw, gpu_util, mem_util}]}
  GET /api/vram        -> {"devices": [{backend, index, name, total, free,
                                        used_pct}]}
  GET /api/models      -> [{id, name, command, run_on_boot,
                            status: {running, pid}, perf: {tps, prompt_tps}}]

Authenticated endpoints require the ``X-API-Key`` header.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta

import aiohttp

from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=10)


class LlamaAuthError(Exception):
    """Raised when llama-manager rejects the API key (HTTP 401)."""


@dataclass
class LlamaData:
    """One poll of the llama-manager API."""

    healthy: bool
    gpu_devices: list[dict] = field(default_factory=list)
    vram_devices: list[dict] = field(default_factory=list)
    models: list[dict] = field(default_factory=list)
    system: dict = field(default_factory=dict)


class LlamaManagerClient:
    """Thin async client for the llama-manager Flask API."""

    def __init__(self, session: aiohttp.ClientSession, base_url: str, api_key: str):
        self._session = session
        self.base_url = base_url.rstrip("/")
        self._headers = {"X-API-Key": api_key} if api_key else {}

    async def _get(self, path: str, *, authenticated: bool) -> dict | list:
        url = f"{self.base_url}{path}"
        headers = self._headers if authenticated else {}
        try:
            async with self._session.get(
                url, headers=headers, timeout=REQUEST_TIMEOUT
            ) as resp:
                if resp.status == 401:
                    raise LlamaAuthError("llama-manager rejected the API key")
                resp.raise_for_status()
                return await resp.json()
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Cannot reach llama-manager at {url}: {err}") from err

    async def get_health(self) -> bool:
        """True when /health answers {"ok": true}."""
        data = await self._get("/health", authenticated=False)
        return bool(data.get("ok"))

    async def get_gpu_stats(self) -> list[dict]:
        data = await self._get("/api/gpu-stats", authenticated=True)
        return data.get("devices", [])

    async def get_vram(self) -> list[dict]:
        data = await self._get("/api/vram", authenticated=True)
        return data.get("devices", [])

    async def get_models(self) -> list[dict]:
        data = await self._get("/api/models", authenticated=True)
        return data if isinstance(data, list) else []

    async def get_system_stats(self) -> dict:
        data = await self._get("/api/system-stats", authenticated=True)
        return data if isinstance(data, dict) else {}


class LlamaManagerCoordinator(DataUpdateCoordinator[LlamaData]):
    """Poll llama-manager on a fixed interval and share the result."""

    def __init__(
        self,
        hass,
        *,
        base_url: str,
        api_key: str,
        update_interval: int,
    ):
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )
        from homeassistant.helpers import aiohttp_client

        self._client = LlamaManagerClient(
            aiohttp_client.async_get_clientsession(hass), base_url, api_key
        )

    async def _async_update_data(self) -> LlamaData:
        previous = self.data

        try:
            healthy = await self._client.get_health()
        except LlamaAuthError as err:
            raise UpdateFailed(str(err)) from err
        except UpdateFailed:
            # llama-manager is unreachable: report it via the status sensor
            # instead of failing the whole update.
            healthy = False

        if not healthy:
            # Keep the last known values so GPU/model sensors don't flap
            # to unknown while the app is down.
            if previous is not None:
                return LlamaData(
                    False,
                    previous.gpu_devices,
                    previous.vram_devices,
                    previous.models,
                    previous.system,
                )
            return LlamaData(False)

        try:
            gpu_devices = await self._client.get_gpu_stats()
            vram_devices = await self._client.get_vram()
            models = await self._client.get_models()
            system = await self._client.get_system_stats()
        except LlamaAuthError as err:
            raise UpdateFailed(str(err)) from err
        except UpdateFailed as err:
            if previous is not None:
                _LOGGER.warning("llama-manager API error, keeping last data: %s", err)
                return LlamaData(
                    True,
                    previous.gpu_devices,
                    previous.vram_devices,
                    previous.models,
                    previous.system,
                )
            raise

        return LlamaData(True, gpu_devices, vram_devices, models, system)
