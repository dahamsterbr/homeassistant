# Changelog

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
