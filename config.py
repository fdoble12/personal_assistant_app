"""
Configuration module for Personal Life OS.

Priority order:
  1. st.secrets  — Streamlit Cloud injects these automatically
  2. os.environ  — Railway sets these as environment variables
  3. .env file   — loaded by python-dotenv for local development

Same config.py works on every platform with zero code changes.
"""
import os
from dotenv import load_dotenv

# Load .env for local dev — safe no-op if the file doesn't exist
load_dotenv()


def _get(key: str):
    """
    Read a config value from st.secrets (Streamlit Cloud) or env vars (Railway/local).
    """
    # Streamlit Cloud path
    try:
        import streamlit as st
        value = st.secrets.get(key)
        if value:
            return str(value)
    except Exception:
        pass

    # Railway / local .env path
    return os.getenv(key)


# ── Public config values ────────────────────────────────────────────────────
SUPABASE_URL        = _get("SUPABASE_URL")
SUPABASE_KEY        = _get("SUPABASE_KEY")
TELEGRAM_BOT_TOKEN  = _get("TELEGRAM_BOT_TOKEN")
ANTHROPIC_API_KEY   = _get("ANTHROPIC_API_KEY")

ENVIRONMENT = _get("ENVIRONMENT") or "development"
DEBUG       = ENVIRONMENT == "development"


def validate_config(require_telegram=False):
    """
    Validate required env vars are present.
    Pass require_telegram=True when running the bot on Railway.
    The Streamlit dashboard never needs the Telegram token.
    """
    required = {
        "SUPABASE_URL":      SUPABASE_URL,
        "SUPABASE_KEY":      SUPABASE_KEY,
        "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
    }
    if require_telegram:
        required["TELEGRAM_BOT_TOKEN"] = TELEGRAM_BOT_TOKEN

    missing = [k for k, v in required.items() if not v]
    if missing:
        raise ValueError(
            f"Missing environment variables: {', '.join(missing)}\n"
            "  Local: add to .env\n"
            "  Streamlit Cloud: App > Settings > Secrets\n"
            "  Railway: Service > Variables"
        )


if __name__ == "__main__":
    validate_config(require_telegram=True)
    print("All config OK.")
