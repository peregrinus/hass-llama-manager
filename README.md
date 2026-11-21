# Nome-LLama-Manager

A Home Assistant **custom integration** (HACS, lives in `custom_components/`) that
creates sensors from the [llama-manager](../llama-manager) Flask API, so you can put
a stats card on your dashboard. Sensors update once a minute by default.

## Sensors created

| Sensor | Source | State |
| --- | --- | --- |
| Status | `GET /health` | `online` / `offline` |
| `<GPU> Temperature` (one per GPU) | `GET /api/gpu-stats` | °C |
| `<GPU> Fan Speed` (one per GPU) | `GET /api/gpu-stats` | % |
| `<GPU> Memory Utilisation` (one per GPU) | `GET /api/gpu-stats` | % |
| `<Backend> <n> VRAM` (one per device) | `GET /api/vram` | % used (free/total MiB in attributes) |
| Model Running | `GET /api/models` | model name(s), or `none` |
| Prompt Speed | `GET /api/models` | e.g. `out 18.7 t/s · prompt 36.5 t/s` |
| Generation Speed | `GET /api/models` | numeric, t/s |
| Prompt Processing Speed | `GET /api/models` | numeric, t/s |

GPU and VRAM sensors are created dynamically — one per device that
llama-manager reports, so they appear/disappear automatically.

## Configuration

When you add the integration, Home Assistant asks for:

- **llama-manager URL** — e.g. `http://192.168.1.222:6522/`
- **API key** — the key configured on llama-manager's `/edit` page
  (it is sent as the `X-API-Key` header). The key must be set there;
  llama-manager's `/api/*` endpoints reject requests without a valid key.
- **Update interval (seconds)** — default 60, minimum 10.

All three can be changed later via *Settings → Devices & Services →
Nome-LLama-Manager → Options*.

## Installation

### Via HACS

1. HACS → **Integrations** → ⋮ → **Custom Repositories** → add this
   repository's URL.
2. HACS → **Integrations** → search for **Nome-LLama-Manager** → **Download**.
3. Restart Home Assistant.
4. *Settings → Devices & Services → Add Integration → Nome-LLama-Manager*.

### Manual

Copy the `custom_components/nome_llama_manager` folder into your
Home Assistant config's `custom_components/` directory, restart Home
Assistant, then add the integration as above.

## Notes

- No extra Python dependencies — uses only what ships with Home Assistant.
- If llama-manager is unreachable, the Status sensor shows `offline` and the
  other sensors keep their last known values.
- If the API key is wrong, the integration refuses to set up (and reports the
  error in the config flow) rather than silently failing.
