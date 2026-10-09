# Changelog

## 1.0.3

- Assist: multi-command sentences (e.g. lamp A uit en lamp B aan) via parallel/sequential tool calls
- Treat spoken "out" as off; nudge model if only one of several actions ran

## 1.0.2

- Auto-fix `llm_base_url` missing port (default `:1234`) and ensure `/v1` suffix
- Clearer connection-error hints in health/status

## 1.0.1

- Always call LM Studio for who-is-in-room (no longer skip LLM when only one person is home)
- Resolve model ids against LM Studio `/models` list
- MQTT sensors for LLM online / call count / last call / error and per-room LLM model
- Assist: proper tool schemas, multi-round tool calls, weather entity injection (no open web search)

## 1.0.0

- Initial Local Home AI add-on
- LM Studio OpenAI-compatible dual-model routing
- Room presence fusion with online learning (SQLite)
- MQTT discovery entities for occupied / confidence / likely person
- Plugin adapters for mmWave, PIR, radar, Frigate, lights, media, person
