"""Constants for Local OpenAI / LM Studio integration."""

DOMAIN = "local_openai"
DEFAULT_NAME = "Local OpenAI"
CONF_BASE_URL = "base_url"
CONF_API_KEY = "api_key"
CONF_MODEL = "model"
CONF_PROMPT = "prompt"
DEFAULT_BASE_URL = "http://192.168.1.10:1234/v1"
DEFAULT_API_KEY = "lmstudio"
DEFAULT_MODEL = "google/gemma-4-12b"
DEFAULT_PROMPT = (
    "You are a helpful Home Assistant voice assistant. "
    "Be concise. Prefer controlling devices via tools when available. "
    "Household language may be Dutch."
)
