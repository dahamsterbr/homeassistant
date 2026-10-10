# Local Home AI (Home Assistant Add-on)

HAOS add-on repository that connects **LM Studio / Bionic** (OpenAI-compatible API) to Home Assistant, fuses existing room sensors into learned occupancy, and stores all learning data locally.

## Features

- Supervisor add-on with easy UI updates (bump version + rebuild)
- Dual-model routing: fast (`nvidia-nemotron-3-nano-4b`) and reason (`google/gemma-4-12b`)
- Room presence fusion from mmWave, PIR, radar, Frigate, lights, media
- Online weight learning + episodic memory in SQLite (`/data/lhai.db`)
- MQTT discovery entities: occupied / confidence / likely person / reason
- Bundled `custom_components/local_openai` for Assist → LM Studio
- Plugin adapters for future sensors (BLE / ESPresense stub included)

## Install (HAOS)

1. Keep **LM Studio** running with the OpenAI server on port `1234` and load your models.
2. In Home Assistant: **Settings → Add-ons → Add-on Store → ⋮ → Repositories**
3. Add this repository URL (Git remote of this project).
4. Install **Local Home AI**, set options (see [docs/SETUP.md](docs/SETUP.md)), start it.
5. Confirm Mosquitto is running so discovery entities appear.
6. Copy Assist integration from `/share/local_home_ai/custom_components/local_openai` into `/config/custom_components/local_openai`, restart HA, then add **Local OpenAI (LM Studio)** under Devices & Services.

## Security

Never commit long-lived access tokens. Put the HA token only in add-on options. If a token was shared in chat, revoke it and create a new one.

## Docs

- [docs/SETUP.md](docs/SETUP.md) — first-time setup and room map for thuis
- [docs/VOICE.md](docs/VOICE.md) — Home Assistant Voice pipeline, LLM on/off, prompt logging
- [docs/OPERATIONS.md](docs/OPERATIONS.md) — updates, backups, troubleshooting, Bionic MCP phase 2
- [local_home_ai/DOCS.md](local_home_ai/DOCS.md) — add-on panel documentation

## Development layout

```text
repository.yaml
local_home_ai/           # Supervisor add-on
custom_components/       # Assist integration (also bundled in add-on image)
docs/
```
