# Setup — Local Home AI + LM Studio

## Prerequisites

- Home Assistant OS / Supervised with Mosquitto
- LM Studio (or Bionic using the same local runtime) on a GPU host
- Models loaded, for example:
  - `google/gemma-4-12b` (reason)
  - `nvidia-nemotron-3-nano-4b` (fast)
- OpenAI-compatible server listening on `0.0.0.0:1234` (not only localhost if HA runs on another machine)

## 1. LM Studio

1. Start LM Studio → Developer / Local Server → Start server on port `1234`.
2. Load both models (or keep the reason model loaded; fast model can be swapped as needed).
3. From another host, verify:

```bash
curl http://<LM_HOST>:1234/v1/models
```

## 2. Home Assistant token

1. HA → Profile → Security → Long-Lived Access Tokens → Create.
2. Paste into add-on option `ha_token` only (never commit it).
3. If a token was exposed earlier, revoke it and create a new one.

## 3. Install the add-on

1. Add this git repository in **Settings → Add-ons → Add-on Store → Repositories**.
2. Install **Local Home AI**.
3. Configure at minimum:

```yaml
ha_url: http://homeassistant:8123
ha_token: "<your token>"
llm_base_url: http://<LM_HOST>:1234/v1
llm_api_key: lmstudio
model_fast: nvidia-nemotron-3-nano-4b
model_reason: google/gemma-4-12b
mqtt_host: core-mosquitto
learn_enabled: true
```

4. Start the add-on. Check logs for MQTT connect and HA WebSocket auth.

## 4. Built-in room map (thuis)

Used automatically when `rooms` is empty:

| Room | Primary sensors |
|------|-----------------|
| keuken | `mmwave_keuken_presence`, `radar_keuken_presence`, `pir_keuken_*`, Frigate keuken person, `light.lampen_keuken` |
| gang | `mmwave_gang_presence`, `radar_gang_presence`, `pir_gang_*` |
| overloop | `mmwave_overloop_presence`, `pir_overloop*` |
| wc | `mmwave_wc_presence` |
| computers | `mmwave_computer_presence`, `wave_pc_occupancy`, `light.lampen_computer` |
| voordeur | Frigate/Reolink person + motion |
| achterhuis | Frigate person + motion |

Persons considered for attribution:

- `person.bjorn_reints`
- `person.eva_reints`
- `person.jannie`

## 5. Assist (Local OpenAI component)

1. With the add-on running, open Samba/SSH and copy:

```text
/share/local_home_ai/custom_components/local_openai
  → /config/custom_components/local_openai
```

Or copy from this repo’s `custom_components/local_openai`.

2. Restart Home Assistant.
3. **Settings → Devices & Services → Add Integration → Local OpenAI (LM Studio)**
4. Base URL: `http://<LM_HOST>:1234/v1`, model: `google/gemma-4-12b`
5. **Settings → Voice assistants → Assist** → create/edit a pipeline for **Home Assistant Voice**:
   - Conversation agent: **Local OpenAI** (LM Studio / Gemma)
   - STT: Whisper (or preferred)
   - TTS: Piper (or preferred)
6. Expose the lights/switches you want to control to Assist (entity settings → voice assistants).
7. Prefer model **`google/gemma-4-12b`** for voice control; enable tool calling in LM Studio.

Multi-command examples that should work with Local OpenAI:

- `lamp keuken uit en lamp woonkamer aan`
- `light A out and light B on`
- `zet de gang uit en de computer lamp aan`

Built-in Home Assistant Assist (non-LLM) usually only handles **one** intent per sentence — use Local OpenAI for multi-action.

## 6. Verify

1. Walk through keuken/gang — `binary_sensor.lhai_*_occupied` should flip.
2. When a room is occupied, check add-on logs for `Calling LLM for room=...` and `LLM OK purpose=attribute:...`.
3. Entities `sensor.lhai_*_reason` should look like `[google/gemma-4-12b] ...` (not only heuristic text).
4. System sensors: `binary_sensor.lhai_llm_ok`, `sensor.lhai_llm_calls`, `sensor.lhai_llm_last`.
5. Assist weather: expose your `weather.*` / Buienradar entities to Assist, then ask “wat is het weer?”. There is **no open internet search** — answers come from HA weather entities/tools only.
