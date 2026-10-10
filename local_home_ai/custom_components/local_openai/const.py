"""Constants for Local OpenAI / LM Studio integration."""

DOMAIN = "local_openai"
DEFAULT_NAME = "Local OpenAI"
CONF_BASE_URL = "base_url"
CONF_API_KEY = "api_key"
CONF_MODEL = "model"
CONF_PROMPT = "prompt"
CONF_ENABLED = "enabled"
CONF_LOG_PROMPTS = "log_prompts"
DEFAULT_BASE_URL = "http://192.168.1.10:1234/v1"
DEFAULT_API_KEY = "lmstudio"
# Prefer a small Instruct model for Voice (speed). Upgrade only if quality needs it.
DEFAULT_MODEL = "nvidia-nemotron-3-nano-4b"
DEFAULT_ENABLED = True
DEFAULT_LOG_PROMPTS = True
PROMPT_DUMP_FILENAME = "local_openai_last_prompt.md"
DEFAULT_PROMPT = (
    "You are a helpful Home Assistant voice assistant for the home 'thuis'. "
    "Be concise. Reply with a short confirmation after acting. "
    "Household language may be Dutch or mixed Dutch/English. "
    "Synonyms: uit/out/off = turn off; aan/on = turn on. "
    "When the user gives MULTIPLE actions in one sentence "
    "(e.g. 'lamp A uit en lamp B aan' or 'light A out and light B on'), "
    "call a tool for EACH action in the same turn (multiple tool calls). "
    "Do not only do the first action. "
    "For weather/forecast use weather entities/tools — never invent. "
    "You cannot browse the open internet."
)
