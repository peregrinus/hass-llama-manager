"""Sensor platform for the Nome-LLama-Manager integration."""

from __future__ import annotations

import logging
import re

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

from .api import LlamaData
from .const import DOMAIN, NAME

_LOGGER = logging.getLogger(__name__)

# metric key in /api/gpu-stats -> sensor definition
GPU_METRICS: dict[str, dict] = {
    "temp": {
        "name": "Temperature",
        "unit": "°C",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "icon": "mdi:thermometer",
    },
    "fan_speed": {
        "name": "Fan Speed",
        "unit": "%",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "icon": "mdi:fan",
    },
    "mem_util": {
        "name": "Memory Utilisation",
        "unit": "%",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "icon": "mdi:memory",
    },
}


def _to_float(value) -> float | None:
    """Best-effort conversion of an API value to a float.

    nvtop occasionally reports values with unit suffixes (e.g. "34C");
    pull the number out of whatever the API sends, else return None.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.search(r"-?\d+(?:\.\d+)?", value)
        if match:
            return float(match.group(0))
    return None


def _running_models(data: LlamaData) -> list[str]:
    """Names of the models whose status.running is true."""
    return [
        m["name"]
        for m in data.models
        if isinstance(m.get("status"), dict) and m["status"].get("running")
    ]


def _running_perf(data: LlamaData, keys: tuple[str, ...]) -> dict | None:
    """Latest perf dict of the first running model that reports any of `keys`.

    llama-server models report tps/prompt_tps; sd-server models report
    image_s. Filtering by key keeps the two kinds of model separate when
    both are running at the same time.
    """
    for m in data.models:
        if isinstance(m.get("status"), dict) and m["status"].get("running"):
            perf = m.get("perf") or {}
            if any(perf.get(k) is not None for k in keys):
                return perf
    return None


class LlamaManagerEntity(CoordinatorEntity):
    """Base entity bound to the llama-manager coordinator."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry_id: str):
        super().__init__(coordinator)
        self._entry_id = entry_id

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name=NAME,
            manufacturer="Nome",
        )


class LlamaStatusSensor(LlamaManagerEntity):
    """Is the llama-manager application up?"""

    _attr_name = "Status"
    _attr_unique_id = "status"
    _attr_icon = "mdi:server"

    @property
    def state(self) -> str:
        return "online" if self.coordinator.data.healthy else "offline"


class LlamaGpuSensor(LlamaManagerEntity):
    """One metric for one GPU, from /api/gpu-stats."""

    def __init__(self, coordinator, entry_id: str, device_slug: str, device_name: str, metric: str):
        super().__init__(coordinator, entry_id)
        self._device_slug = device_slug
        self._metric = metric
        spec = GPU_METRICS[metric]
        self._attr_name = f"{device_name} {spec['name']}"
        self._attr_unique_id = f"gpu_{device_slug}_{metric}"
        self._attr_native_unit_of_measurement = spec["unit"]
        self._attr_device_class = spec["device_class"]
        self._attr_state_class = spec["state_class"]
        self._attr_icon = spec["icon"]

    @property
    def state(self):
        for dev in self.coordinator.data.gpu_devices:
            if slugify(dev.get("device_name") or "unknown") == self._device_slug:
                # Always report a number (or None) so the state can be
                # used in charts, gauges and automations.
                return _to_float(dev.get(self._metric))
        return None


class LlamaVramSensor(LlamaManagerEntity):
    """VRAM utilisation for one device, from /api/vram."""

    def __init__(self, coordinator, entry_id: str, backend: str, index: int):
        super().__init__(coordinator, entry_id)
        self._key = f"{backend}{index}"
        self._attr_name = f"{backend} {index} VRAM"
        self._attr_unique_id = f"vram_{backend.lower()}{index}"
        self._attr_native_unit_of_measurement = "%"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:memory"

    def _device(self) -> dict | None:
        for dev in self.coordinator.data.vram_devices:
            if f"{dev.get('backend', '')}{dev.get('index', '')}" == self._key:
                return dev
        return None

    @property
    def state(self):
        dev = self._device()
        if not dev:
            return None
        return _to_float(dev.get("used_pct"))

    @property
    def extra_state_attributes(self) -> dict:
        dev = self._device()
        if not dev:
            return {}
        return {
            "device_name": dev.get("name"),
            "free_mib": dev.get("free"),
            "total_mib": dev.get("total"),
        }


class LlamaModelRunningSensor(LlamaManagerEntity):
    """Which model(s) are currently running."""

    _attr_name = "Model Running"
    _attr_unique_id = "model_running"
    _attr_icon = "mdi:cpu-64-bit"

    @property
    def state(self) -> str:
        running = _running_models(self.coordinator.data)
        return ", ".join(running) if running else "none"


class LlamaPromptSpeedSensor(LlamaManagerEntity):
    """Latest prompt speed of the running llama-server model, UI format:
    "out 18.7 t/s · prompt 36.5 t/s". Ignores sd-server models."""

    _attr_name = "Prompt Speed"
    _attr_unique_id = "prompt_speed"
    _attr_icon = "mdi:speedometer"

    @property
    def state(self) -> str | None:
        perf = _running_perf(self.coordinator.data, ("tps", "prompt_tps"))
        if not perf:
            return None
        parts = []
        if perf.get("tps") is not None:
            parts.append(f"out {perf['tps']} t/s")
        if perf.get("prompt_tps") is not None:
            parts.append(f"prompt {perf['prompt_tps']} t/s")
        return " \u00b7 ".join(parts) if parts else None


class LlamaGenerationTpsSensor(LlamaManagerEntity):
    """Generation (output) speed of the running model in tokens/s."""

    _attr_name = "Generation Speed"
    _attr_unique_id = "generation_tps"
    _attr_native_unit_of_measurement = "t/s"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:download-network"

    @property
    def state(self):
        perf = _running_perf(self.coordinator.data, ("tps", "prompt_tps"))
        if not perf:
            return None
        return _to_float(perf.get("tps"))


class LlamaPromptTpsSensor(LlamaManagerEntity):
    """Prompt processing speed of the running model in tokens/s."""

    _attr_name = "Prompt Processing Speed"
    _attr_unique_id = "prompt_tps"
    _attr_native_unit_of_measurement = "t/s"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:arrow-up-bold"

    @property
    def state(self):
        perf = _running_perf(self.coordinator.data, ("tps", "prompt_tps"))
        if not perf:
            return None
        return _to_float(perf.get("prompt_tps"))


class LlamaImageGenSensor(LlamaManagerEntity):
    """Image generation time (s) of a running sd-server model."""

    _attr_name = "Image Generation Time"
    _attr_unique_id = "image_gen_time"
    _attr_native_unit_of_measurement = "s"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:image"

    @property
    def state(self):
        perf = _running_perf(self.coordinator.data, ("image_s",))
        if not perf:
            return None
        return _to_float(perf.get("image_s"))


# key in /api/system-stats -> sensor definition
SYSTEM_METRICS: dict[str, dict] = {
    "cpu_util": {"name": "CPU Utilisation", "unit": "%", "icon": "mdi:cpu"},
    "ram": {"name": "RAM In Use", "unit": "GB", "icon": "mdi:memory"},
    "disk": {"name": "Disk In Use", "unit": "GB", "icon": "mdi:harddisk"},
}


class LlamaSystemSensor(LlamaManagerEntity):
    """Host CPU / RAM / disk usage, from /api/system-stats. Plain numbers, no attributes."""

    def __init__(self, coordinator, entry_id: str, metric: str):
        super().__init__(coordinator, entry_id)
        self._metric = metric
        spec = SYSTEM_METRICS[metric]
        self._attr_name = spec["name"]
        self._attr_unique_id = f"system_{metric}"
        self._attr_native_unit_of_measurement = spec["unit"]
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = spec["icon"]

    @property
    def state(self):
        val = self.coordinator.data.system.get(self._metric)
        if val is None:
            return None
        if self._metric == "cpu_util":
            return _to_float(val)
        if not isinstance(val, dict):
            return None
        if self._metric == "ram":
            used_mb = val.get("used_mb")
            return round(used_mb / 1024, 1) if used_mb is not None else None
        return _to_float(val.get("used_gb"))


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up the sensors, adding/removing GPU entities as they appear."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entry_id = entry.entry_id
    entities: dict[str, LlamaManagerEntity] = {}

    def desired_entities() -> dict[str, LlamaManagerEntity]:
        data = coordinator.data
        wanted: dict[str, LlamaManagerEntity] = {}
        if data is None:
            return wanted

        for dev in data.gpu_devices:
            name = dev.get("device_name") or "Unknown"
            slug = slugify(name)
            for metric in GPU_METRICS:
                entity = LlamaGpuSensor(coordinator, entry_id, slug, name, metric)
                wanted[entity.unique_id] = entity

        for dev in data.vram_devices:
            entity = LlamaVramSensor(
                coordinator,
                entry_id,
                dev.get("backend", "Unknown"),
                dev.get("index", 0),
            )
            wanted[entity.unique_id] = entity

        for cls in (
            LlamaStatusSensor,
            LlamaModelRunningSensor,
            LlamaPromptSpeedSensor,
            LlamaGenerationTpsSensor,
            LlamaPromptTpsSensor,
            LlamaImageGenSensor,
        ):
            entity = cls(coordinator, entry_id)
            wanted[entity.unique_id] = entity

        for metric in SYSTEM_METRICS:
            entity = LlamaSystemSensor(coordinator, entry_id, metric)
            wanted[entity.unique_id] = entity

        return wanted

    def remove_stale(wanted: dict[str, LlamaManagerEntity]) -> None:
        registry = dr.async_get(hass)
        for entity in [e for uid, e in entities.items() if uid not in wanted]:
            if entity.registry_entry is not None:
                registry.async_remove(entity.registry_entry.id)
            entities.pop(entity.unique_id, None)

    async def add_new(new: list[LlamaManagerEntity]) -> None:
        entities.update({e.unique_id: e for e in new})
        await async_add_entities(new)

    @callback
    def update_entities() -> None:
        """Sync listener: reconcile entities after each coordinator update."""
        wanted = desired_entities()
        remove_stale(wanted)
        new = [e for uid, e in wanted.items() if uid not in entities]
        if new:
            hass.async_create_task(
                add_new(new), name="nome_llama_manager add entities"
            )

    # Initial add (awaited), then listen for updates.
    wanted = desired_entities()
    new = [e for uid, e in wanted.items() if uid not in entities]
    if new:
        await add_new(new)
    entry.async_on_unload(coordinator.async_add_listener(update_entities))
