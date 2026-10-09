# Local Home AI

Fuses your existing occupancy sensors and asks a local LM Studio model who is likely in each room. Learning weights and episodes stay on the add-on data disk.

## Options

| Option | Meaning |
|--------|---------|
| `ha_url` | Usually `http://homeassistant:8123` |
| `ha_token` | Long-lived access token (Profile → Security) |
| `llm_base_url` | LM Studio OpenAI base URL, e.g. `http://192.168.x.x:1234/v1` |
| `model_fast` | Fast model id (default Nemotron nano) |
| `model_reason` | Reasoning model id (default Gemma) |
| `mqtt_host` | Default `core-mosquitto` |
| `learn_enabled` | Online weight updates |
| `rooms` | Optional override of the built-in thuis room map |

Leave `rooms` empty to use the built-in map (keuken, gang, overloop, wc, computers, voordeur, achterhuis).

## Entities

MQTT discovery creates per room:

- `binary_sensor.lhai_<room>_occupied`
- `sensor.lhai_<room>_confidence`
- `sensor.lhai_<room>_likely_person`
- `sensor.lhai_<room>_reason`

## Health

Add-on HTTP API on port **8099**:

- `GET /health`
- `GET /status`
- `POST /evaluate`

## Assist

After start, copy `/share/local_home_ai/custom_components/local_openai` into HA `/config/custom_components/`, restart, and add the **Local OpenAI** integration pointing at the same LM Studio URL.
