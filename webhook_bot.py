"""
webhook_bot.py — PythonAnywhere deployment entry point
======================================================
Wraps the exact same bot handlers from bot.py inside a Flask app
so Telegram can POST updates to us (webhook mode).

Polling (bot.py)  →  bot pulls updates from Telegram every few seconds
Webhook (this)    →  Telegram pushes updates to our Flask URL instantly

PythonAnywhere free tier gives you a persistent HTTPS URL at:
  https://<your-username>.pythonanywhere.com

This file is the WSGI app PythonAnywhere runs.  bot.py is unchanged
and still works for local development.
"""

import logging
import os
from flask import Flask, request, abort
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
import asyncio

import config

# ── Import all handlers from bot.py (no duplication) ───────────────────────
from bot import (
    start_command,
    help_command,
    notes_command,
    summary_command,
    profile_command,
    setgoal_command,
    settarget_command,
    handle_message,
    error_handler,
)

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────────────────────────
config.validate_config(require_telegram=True)

# The secret path Telegram will POST to — obscure it so random bots can't hit it
# Set WEBHOOK_SECRET in PythonAnywhere environment variables (any random string)
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "lifeos-webhook-secret-change-me")
WEBHOOK_PATH   = f"/webhook/{WEBHOOK_SECRET}"

# ── Build the PTB Application (no polling — we drive it manually) ────────────
ptb_app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

ptb_app.add_handler(CommandHandler("start",      start_command))
ptb_app.add_handler(CommandHandler("help",       help_command))
ptb_app.add_handler(CommandHandler("notes",      notes_command))
ptb_app.add_handler(CommandHandler("summary",    summary_command))
ptb_app.add_handler(CommandHandler("profile",    profile_command))
ptb_app.add_handler(CommandHandler("setgoal",    setgoal_command))
ptb_app.add_handler(CommandHandler("settarget",  settarget_command))
ptb_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
ptb_app.add_error_handler(error_handler)

# ── Flask app ─────────────────────────────────────────────────────────────────
flask_app = Flask(__name__)


@flask_app.route(WEBHOOK_PATH, methods=["POST"])
def telegram_webhook():
    """Receive an update from Telegram and process it."""
    if request.content_type != "application/json":
        abort(415)

    update = Update.de_json(request.get_json(force=True), ptb_app.bot)

    # Run the async PTB handler inside the current event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(ptb_app.process_update(update))
    finally:
        loop.close()

    return "ok", 200


@flask_app.route("/health")
def health():
    """PythonAnywhere pings this to keep the app alive."""
    return "ok", 200


@flask_app.route("/")
def index():
    return "Personal Life OS Bot is running.", 200


# ── Register the webhook with Telegram (run once after deploy) ───────────────
def register_webhook(pythonanywhere_username: str):
    """
    Call this ONCE from a PythonAnywhere console to point Telegram at your URL.

    Usage:
        from webhook_bot import register_webhook
        register_webhook("your_pythonanywhere_username")
    """
    import asyncio as _asyncio

    webhook_url = (
        f"https://{pythonanywhere_username}.pythonanywhere.com{WEBHOOK_PATH}"
    )

    async def _set():
        await ptb_app.bot.set_webhook(
            url=webhook_url,
            allowed_updates=["message", "callback_query"],
        )
        info = await ptb_app.bot.get_webhook_info()
        logger.info(f"Webhook set: {info.url}")
        print(f"✅ Webhook registered: {webhook_url}")
        print(f"   Pending updates:    {info.pending_update_count}")

    _asyncio.run(_set())


# ── Local testing shim ────────────────────────────────────────────────────────
if __name__ == "__main__":
    # For quick local testing only — use bot.py (polling) for normal local dev
    print(f"Flask dev server starting — webhook path: {WEBHOOK_PATH}")
    flask_app.run(port=5000, debug=True)
