# Home Assistant Voice + Local OpenAI

Use this when you want spoken multi-command control via LM Studio and **no** presence LLM load.

## 1. Free LM Studio for Voice

Add-on **Local Home AI** → Configuration:

- `llm_attribution_enabled`: **off** (default in 1.0.5)

Fusion sensors still update; LM Studio is not called for who-is-in-room.

## 2. Local OpenAI toggles

**Settings → Devices & Services → Local OpenAI → Configure**

| Option | Meaning |
|--------|---------|
| Enable LLM for Assist / Voice | Master switch for the conversation agent |
| Log prompts | Writes every request to `/config/local_openai_last_prompt.md` and HA log |

Open the dump file after speaking (Samba / File Editor / VS Code).

Logger (optional, more detail):

```yaml
# configuration.yaml
logger:
  default: info
  logs:
    custom_components.local_openai: debug
```

## 3. Voice pipeline (required)

**Settings → Voice assistants → Assistants**

Create/edit the pipeline used by your **Home Assistant Voice** device:

| Stage | Suggested |
|-------|-----------|
| Wake word | OpenWakeWord (already common on HAOS) |
| Speech-to-text | **Whisper** (faster-whisper add-on / cloud STT you already use) |
| Conversation agent | **Local OpenAI** (not “Home Assistant”) |
| Text-to-speech | **Piper** |

On the Voice PE device settings: select that pipeline. Language: Dutch if you speak Dutch (STT model must support NL).

## 4. Expose devices

Each light/switch you want to control → entity settings → expose to **Assist**.

## 5. LM Studio

- One small model loaded (Granite Dutch / Nemotron nano / Qwen3 1.7B–4B)
- Server `http://<ip>:1234/v1`
- Tool calling enabled
- Same model id in Local OpenAI

## 6. Test order

1. Text chat in HA Assist UI with Local OpenAI (“keukenlamp uit”) — check `local_openai_last_prompt.md`
2. Then Voice wake word → same phrase
3. If Voice fails but chat works: STT/pipeline language, not the LLM
4. If chat fails: prompt dump + LM Studio server log

## What “does not work” usually means

| Symptom | Likely cause |
|---------|----------------|
| No reaction after wake | Wake word / pipeline not assigned to device |
| Hears you but wrong text | STT language/model |
| Correct text, no lights | Conversation agent still Home Assistant, or entities not exposed |
| Connection error | Slow/large model or wrong `:1234` URL |
