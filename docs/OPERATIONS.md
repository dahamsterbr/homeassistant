# Operations — Local Home AI

## Updates

1. Pull / push new commits to the add-on repository.
2. Bump `version` in `local_home_ai/config.yaml` and add notes to `local_home_ai/CHANGELOG.md`.
3. In HA: Add-on → **Check for updates** → Update → Restart.

Rebuild is required when Python code or Dockerfile changes.

## Data & backups

| Path | Contents |
|------|----------|
| `/data/lhai.db` | Fusion weights + episodic memory (privacy-sensitive) |
| `/data/options.json` | Add-on options (includes tokens — protect backups) |
| `/share/local_home_ai/custom_components/` | Published Assist integration copy |

Include `/data` for this add-on in HA backups if you want to keep learned weights. Exclude or encrypt if sharing backups externally.

To reset learning only: stop add-on, delete `/data/lhai.db`, start again.

## Health checks

- Add-on logs: HA WebSocket auth, MQTT connect, LLM errors
- `GET /health` on port `8099`
- MQTT: entities under device **Local Home AI**

## Troubleshooting

| Symptom | Check |
|---------|--------|
| No MQTT entities | Mosquitto running; `mqtt_host=core-mosquitto`; discovery enabled in HA MQTT integration |
| LLM errors | LM Studio server up; `llm_base_url` uses host LAN IP (not add-on `localhost`); CORS/firewall allows HA host |
| HA auth failed | Fresh long-lived token; `ha_url` reachable from add-on network |
| Wrong person | Wait for cooldown; check persons home; inspect `sensor.lhai_*_reason`; review episodes after more learning |
| Assist missing | Custom component copied to `/config/custom_components` and HA restarted |

## Model routing

- Occupancy attribution **always** calls LM Studio when a room is occupied (also if only one person is home). Heuristic is only a fallback if the LLM request fails.
- Fast model first, escalates to **reason** when confidence &lt; `confidence_escalate`, multi-person conflict, or JSON parse fails.
- Assist uses the model configured in the Local OpenAI integration (recommend Gemma for tool use).
- Weather/forecast: HA entities + Assist tools only. No general web search.

## Future sensors

Adapters live in `local_home_ai/rootfs/app/plugins/base.py`.

Implemented: `mmwave`, `pir`, `radar`, `frigate`, `light`, `media`, `person`, `generic`.

Stub: `ble` (ESPresense / BLE room presence) — wire entity_ids with `"adapter": "ble"` when you add trackers; refine RSSI/distance features later without changing fusion core.

## Phase 2 — LM Studio Bionic via MCP

Desktop Bionic/LM Studio can control HA through the official **MCP Server** integration:

1. HA → add **MCP Server** integration; create a long-lived token for MCP.
2. On the LM Studio / Bionic host, bridge SSE → stdio with `mcp-proxy` (HA MCP is SSE; LM Studio expects stdio/streamable HTTP).
3. Example `mcp.json` fragment (fill token/URL locally, do not commit secrets):

```json
{
  "mcpServers": {
    "home-assistant": {
      "command": "mcp-proxy",
      "args": [
        "--transport=sse",
        "http://homeassistant.local:8123/mcp_server/sse"
      ],
      "env": {
        "API_ACCESS_TOKEN": "<HA_LONG_LIVED_TOKEN>"
      }
    }
  }
}
```

4. Keep occupancy fusion on the add-on path; use Bionic MCP for interactive desktop control/coding against HA.

Phase 1 does **not** require MCP — the add-on already calls LM Studio’s OpenAI API directly.
