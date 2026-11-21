# AGENTS.md

Home Assistant custom integration (HACS), domain `nome_llama_manager`. It polls the
`llama-manager` Flask API (sibling project at `../llama-manager`, runs on an Ubuntu
server, port 6522, API key sent as `X-API-Key`) and exposes the results as sensors.

## Build / test / lint

There is **no tooling in this repo**: no `pyproject.toml`, no tests, no CI, no build
step. The integration is deployed as-is to HA via HACS (or by copying
`custom_components/nome_llama_manager/` into HA's `custom_components/`).

- Syntax check: `python -m py_compile custom_components/nome_llama_manager/*.py`
- Real verification is loading it in a running Home Assistant instance
  (the only real environment; `homeassistant` must be importable to even import
  the module).
- Releasing = bump `version` in `manifest.json` and push. There are no tags or
  release scripts.

## Architecture (not obvious from the tree)

- `api.py`: `LlamaManagerCoordinator` (a `DataUpdateCoordinator`) polls
  `/health`, `/api/gpu-stats`, `/api/vram`, `/api/models`, `/api/system-stats`
  every `update_interval` seconds and bundles them into one `LlamaData` snapshot.
- `sensor.py` holds all sensor entities. GPU/VRAM sensors are **created and removed
  dynamically**: after every coordinator update, `update_entities` reconciles the
  entities present against what the API reports (new devices → add, vanished
  devices → remove from the entity registry). Unique IDs are deterministic
  (`gpu_<slug>_<metric>`, `vram_<backend><index>`, fixed names for the rest).
- Failure policy matters: if llama-manager is unreachable or errors, the
  coordinator **keeps the last good data** (only `healthy` flips to False) so GPU
  and model sensors don't flap to `unknown`. A bad API key (HTTP 401) is the
  exception — that raises `UpdateFailed` and fails setup/config validation.
- The API key is optional in the client (header only sent when set; `/health` is
  public) but **required** in the config flow.

## Conventions

- No third-party deps beyond what ships with Home Assistant (aiohttp, voluptuous).
- API values can arrive as strings with unit suffixes (nvtop reports e.g. `"34C"`);
  always funnel numeric sensor states through `_to_float()`.
- Model `perf` keys differ by backend: llama-server → `tps`/`prompt_tps`,
  sd-server → `image_s`. Speed sensors key off these to stay model-type-agnostic.
- UI strings use British spelling ("Utilisation").
- `strings.json` and `translations/en.json` must stay **byte-identical** (HA loads
  the `translations/` copy for custom components). Edit both together.
