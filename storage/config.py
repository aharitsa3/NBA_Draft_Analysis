"""Environment/config loading (currently just the Anthropic API key for Phase 9)."""

import os

from dotenv import load_dotenv

from storage.paths import PROJECT_ROOT

load_dotenv(PROJECT_ROOT / ".env")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")


def require_anthropic_api_key() -> str:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Add it to a .env file at the project root "
            "(see .env.example)."
        )
    return ANTHROPIC_API_KEY
