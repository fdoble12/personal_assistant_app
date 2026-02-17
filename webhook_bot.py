"""
webhook_bot.py — PythonAnywhere WSGI entry point
=================================================

Architecture
------------
PythonAnywhere runs a synchronous WSGI server (uWSGI/gunicorn).
PTB's Application object owns an httpx async client that gets bound to
one specific event loop at initialization time.  When the WSGI server
calls our Flask route on a DIFFERENT thread/loop, PTB panics with:

    RuntimeError: <Event> is bound to a different event loop

Fix: don't use PTB's Application at all in the webhook path.
Instead we:
  1. Parse the incoming JSON into a plain dict.
  2. Detect the command/message type ourselves (trivial pattern match).
  3. Call our handler functions directly, passing them a lightweight
     context object.
  4. Use telegram.Bot with a brand-new httpx client created inside
     each request's own asyncio.run() call — no shared state, no loop
     conflicts.

bot.py (polling mode) is unchanged and still used for local dev.
"""

import asyncio
import logging
import os
from typing import Any

from flask import Flask, abort, request as flask_request
from telegram import Bot, Update
from telegram.request import HTTPXRequest

import config
from database import Database
from claude_client import get_claude_client
from models import QuestionData, NoteData, FoodData, WorkoutData

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Startup validation ───────────────────────────────────────────────────────
config.validate_config(require_telegram=True)

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change-me-to-something-random")
WEBHOOK_PATH   = f"/webhook/{WEBHOOK_SECRET}"

# ── Shared (stateless) clients — these hold NO async state ──────────────────
db     = Database()
claude = get_claude_client()

# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_bot() -> Bot:
    """
    Create a fresh Bot with its own httpx client.
    Called once per request so there is no shared async state between requests.
    Each asyncio.run() gets a brand-new client bound to its own loop.
    """
    return Bot(
        token=config.TELEGRAM_BOT_TOKEN,
        request=HTTPXRequest(connection_pool_size=1),
    )


def _fmt_ts(ts: str) -> str:
    from datetime import datetime
    try:
        return datetime.fromisoformat(ts).strftime("%b %d, %Y · %I:%M %p")
    except Exception:
        return ts


TG_MAX = 4096

def _split(text: str) -> list[str]:
    parts, buf = [], ""
    for line in text.splitlines(keepends=True):
        if len(buf) + len(line) > TG_MAX:
            parts.append(buf)
            buf = ""
        buf += line
    if buf:
        parts.append(buf)
    return parts or [""]


async def _send(bot: Bot, chat_id: int, text: str, md: bool = True) -> None:
    mode = "Markdown" if md else None
    for chunk in _split(text):
        await bot.send_message(chat_id=chat_id, text=chunk, parse_mode=mode)


# ── Command / message handlers ───────────────────────────────────────────────
# These mirror bot.py exactly but accept (bot, chat_id, ...) instead of
# (update, context) so they work without PTB's Application machinery.

async def _cmd_start(bot: Bot, chat_id: int, user_id: int) -> None:
    db.get_or_create_user(user_id)
    await _send(bot, chat_id,
        "👋 *Welcome to your Personal Life OS!*\n\n"
        "Just send me a message and I'll figure out what to do:\n"
        "📝 Save notes & brain dumps\n"
        "🍽️ Log meals with macro estimates\n"
        "💪 Track workouts\n"
        "💬 Answer health & fitness questions\n\n"
        "*Commands:*\n"
        "`/notes` — recent notes\n"
        "`/notes <keyword>` — search notes\n"
        "`/notes today` / `week` / `yesterday`\n"
        "`/summary` — today's stats\n"
        "`/profile` — your settings\n"
        "`/help` — this message"
    )


async def _cmd_help(bot: Bot, chat_id: int) -> None:
    await _send(bot, chat_id,
        "🤖 *Personal Life OS Help*\n\n"
        "*Saved automatically:*\n"
        "• Food → `had pizza for dinner`\n"
        "• Workouts → `45 min gym session`\n"
        "• Notes → `remember to call dentist`\n\n"
        "*Answered directly (not saved):*\n"
        "• `how many calories in X?`\n"
        "• `good protein goal for my weight?`\n\n"
        "*Commands:*\n"
        "`/notes` — last 10 notes\n"
        "`/notes dentist` — search\n"
        "`/notes today` / `yesterday` / `week` / `month`\n"
        "`/summary` — today's report\n"
        "`/setgoal 75` — goal weight (kg)\n"
        "`/settarget 2000` — daily calorie target"
    )


async def _cmd_notes(bot: Bot, chat_id: int, user_id: int, args: list[str]) -> None:
    from datetime import datetime, timedelta
    today = datetime.now().date()

    if not args:
        notes = db.get_recent_notes(user_id, limit=10)
        header = "📝 *Your last 10 notes*"
    else:
        kw = " ".join(args).lower().strip()
        if kw == "today":
            notes = db.get_notes_by_date_range(user_id, today, today)
            header = f"📝 *Notes from today* ({today.strftime('%B %d')})"
        elif kw == "yesterday":
            yd = today - timedelta(days=1)
            notes = db.get_notes_by_date_range(user_id, yd, yd)
            header = f"📝 *Notes from yesterday* ({yd.strftime('%B %d')})"
        elif kw in ("week", "this week"):
            notes = db.get_notes_by_date_range(user_id, today - timedelta(days=7), today)
            header = "📝 *Notes — last 7 days*"
        elif kw in ("month", "this month"):
            notes = db.get_notes_by_date_range(user_id, today - timedelta(days=30), today)
            header = "📝 *Notes — last 30 days*"
        else:
            notes = db.search_notes(user_id, kw, limit=8)
            header = f'🔍 *Notes matching "{kw}"*'

    if not notes:
        await _send(bot, chat_id, f"{header}\n\n_No notes found._")
        return

    lines = [header, ""]
    for i, note in enumerate(notes, 1):
        lines.append(f"*{i}. {note['summary']}*")
        lines.append(f"_{_fmt_ts(note['created_at'])}_")
        tags = note.get("tags") or []
        if tags:
            lines.append(f"🏷 {', '.join(tags)}")
        lines.append(note["content"])
        lines.append("")
    await _send(bot, chat_id, "\n".join(lines))


async def _cmd_summary(bot: Bot, chat_id: int, user_id: int) -> None:
    from datetime import datetime
    s    = db.get_daily_summary(user_id)
    user = db.get_user_profile(user_id)
    date_str = datetime.now().strftime("%A, %B %d, %Y")

    text = f"📊 *Daily Summary*\n_{date_str}_\n\n"

    text += "*🍽️ Nutrition*\n"
    if s.food_entries:
        text += f"Calories: {s.total_calories}"
        if s.calories_target:
            rem  = s.calories_remaining
            icon = "✅" if rem >= 0 else "⚠️"
            text += f" / {s.calories_target} {icon} ({abs(rem)} {'remaining' if rem >= 0 else 'over'})"
        text += f"\nProtein: {s.total_protein}g · Carbs: {s.total_carbs}g · Fat: {s.total_fat}g"
        text += f"\nMeals logged: {s.food_entries}\n"
    else:
        text += "_No meals logged yet_\n"

    text += "\n*💪 Activity*\n"
    if s.workout_count:
        text += f"Sessions: {s.workout_count} · Total: {s.workout_minutes} mins\n"
    else:
        text += "_No workouts logged yet_\n"

    text += "\n*📝 Notes*\n"
    text += (f"Entries today: {s.notes_count} — use /notes to read them\n"
             if s.notes_count else "_No notes today_\n")

    if user and user.current_weight and user.goal_weight:
        diff = round(user.current_weight - user.goal_weight, 1)
        text += f"\n*⚖️ Weight*\nCurrent: {user.current_weight}kg · Goal: {user.goal_weight}kg\n"
        text += f"{'To lose: ' + str(diff) + 'kg' if diff > 0 else '🎉 Goal reached!'}\n"

    await _send(bot, chat_id, text)


async def _cmd_profile(bot: Bot, chat_id: int, user_id: int) -> None:
    user = db.get_user_profile(user_id)
    lines = ["👤 *Your Profile*\n"]
    lines.append(f"Current Weight: {user.current_weight}kg" if user.current_weight else "Current Weight: _Not set_")
    lines.append(f"Goal Weight: {user.goal_weight}kg"       if user.goal_weight     else "Goal Weight: _Not set_")
    lines.append(f"Daily Calorie Target: {user.daily_calorie_target} kcal"
                 if user.daily_calorie_target else "Daily Calorie Target: _Not set_")
    lines.append("\n*Update:* `/setgoal [weight]` · `/settarget [calories]`")
    await _send(bot, chat_id, "\n".join(lines))


async def _cmd_setgoal(bot: Bot, chat_id: int, user_id: int, args: list[str]) -> None:
    if not args:
        await _send(bot, chat_id, "Usage: `/setgoal 75`")
        return
    try:
        w = float(args[0])
        if not (20 < w < 300):
            raise ValueError
        db.update_user_profile(user_id, {"goal_weight": w})
        await _send(bot, chat_id, f"✅ Goal weight set to *{w} kg*")
    except ValueError:
        await _send(bot, chat_id, "❌ Invalid weight. Example: `/setgoal 75`")


async def _cmd_settarget(bot: Bot, chat_id: int, user_id: int, args: list[str]) -> None:
    if not args:
        await _send(bot, chat_id, "Usage: `/settarget 2000`")
        return
    try:
        cal = int(args[0])
        if not (500 <= cal <= 5000):
            raise ValueError
        db.update_user_profile(user_id, {"daily_calorie_target": cal})
        await _send(bot, chat_id, f"✅ Daily calorie target set to *{cal} kcal*")
    except ValueError:
        await _send(bot, chat_id, "❌ Must be 500–5000. Example: `/settarget 2000`")


async def _handle_text(bot: Bot, chat_id: int, user_id: int, text: str) -> None:
    """Route plain text through Claude — same logic as bot.py."""
    await bot.send_chat_action(chat_id=chat_id, action="typing")

    result = claude.classify_message(text)

    if isinstance(result, QuestionData):
        logger.info(f"[{user_id}] → question (not saved)")
        await _send(bot, chat_id, f"💬 {result.answer}", md=False)

    elif isinstance(result, NoteData):
        db.insert_note(user_id, result.content, result.summary, result.tags)
        tags_str = f"\n🏷 {', '.join(result.tags)}" if result.tags else ""
        await _send(bot, chat_id,
            f"📝 *Note saved*\n_{result.summary}_{tags_str}\n\nUse /notes to read your notes.")
        logger.info(f"[{user_id}] → note: {result.summary!r}")

    elif isinstance(result, FoodData):
        db.insert_food_log(user_id, result.food_description,
                           result.calories, result.protein, result.carbs, result.fat)
        nutrition = db.get_daily_nutrition(user_id)
        await _send(bot, chat_id,
            f"🍽️ *Logged:* {result.food_description}\n\n"
            f"• {result.calories} kcal\n"
            f"• Protein: {result.protein}g · Carbs: {result.carbs}g · Fat: {result.fat}g\n\n"
            f"*Today's total:* {nutrition['total_calories']} kcal "
            f"({nutrition['entry_count']} entries)")
        logger.info(f"[{user_id}] → food: {result.food_description} {result.calories} kcal")

    elif isinstance(result, WorkoutData):
        db.insert_workout(user_id, result.activity_type, result.duration_mins,
                          result.distance_km, result.notes)
        workouts = db.get_daily_workouts(user_id)
        total_mins = sum(w["duration_mins"] or 0 for w in workouts)
        reply = (f"💪 *Logged:* {result.activity_type}\n\n"
                 f"⏱ {result.duration_mins} mins")
        if result.distance_km:
            reply += f" · 📏 {result.distance_km} km"
        if result.notes:
            reply += f"\n_{result.notes}_"
        reply += f"\n\n*Today's activity:* {total_mins} mins total"
        await _send(bot, chat_id, reply)
        logger.info(f"[{user_id}] → workout: {result.activity_type} {result.duration_mins} min")


# ── Master dispatcher ─────────────────────────────────────────────────────────

async def _dispatch(payload: dict) -> None:
    """
    Parse a raw Telegram update dict and call the right handler.
    A fresh Bot (and fresh httpx client) is created here — bound to
    THIS call's event loop — so there is never any cross-loop state.
    """
    msg = payload.get("message") or payload.get("edited_message")
    if not msg:
        return   # ignore non-message updates (inline queries, etc.)

    chat_id = msg["chat"]["id"]
    user_id = msg["from"]["id"]
    text    = msg.get("text", "").strip()

    if not text:
        return

    bot = _make_bot()

    try:
        if text.startswith("/"):
            parts   = text.split()
            command = parts[0].lstrip("/").split("@")[0].lower()
            args    = parts[1:]

            if command == "start":
                await _cmd_start(bot, chat_id, user_id)
            elif command == "help":
                await _cmd_help(bot, chat_id)
            elif command == "notes":
                await _cmd_notes(bot, chat_id, user_id, args)
            elif command == "summary":
                await _cmd_summary(bot, chat_id, user_id)
            elif command == "profile":
                await _cmd_profile(bot, chat_id, user_id)
            elif command == "setgoal":
                await _cmd_setgoal(bot, chat_id, user_id, args)
            elif command == "settarget":
                await _cmd_settarget(bot, chat_id, user_id, args)
            else:
                await _send(bot, chat_id, "Unknown command. Try /help")
        else:
            await _handle_text(bot, chat_id, user_id, text)

    except Exception as exc:
        logger.error(f"[{user_id}] Dispatch error: {exc}", exc_info=True)
        try:
            await _send(bot, chat_id,
                "❌ Something went wrong. Try again or use /help", md=False)
        except Exception:
            pass
    finally:
        # Always shut down the bot's httpx client cleanly
        await bot.shutdown()


# ── Flask app ─────────────────────────────────────────────────────────────────

flask_app = Flask(__name__)


@flask_app.route(WEBHOOK_PATH, methods=["POST"])
def telegram_webhook():
    if flask_request.content_type != "application/json":
        abort(415)
    payload = flask_request.get_json(force=True)
    if not payload:
        abort(400)

    # Each request gets its own asyncio.run() → its own event loop →
    # its own Bot/httpx client. Zero shared async state.
    asyncio.run(_dispatch(payload))
    return "ok", 200


@flask_app.route("/health")
def health():
    return "ok", 200


@flask_app.route("/")
def index():
    return "Personal Life OS — bot is running.", 200


# ── One-time webhook registration (run from Bash console) ────────────────────

def register_webhook(pythonanywhere_username: str) -> None:
    """
    Run once after deploying to register your URL with Telegram:

        cd ~/your-project
        python3.10 -c "
        from webhook_bot import register_webhook
        register_webhook('YOUR_PYTHONANYWHERE_USERNAME')
        "
    """
    url = f"https://{pythonanywhere_username}.pythonanywhere.com{WEBHOOK_PATH}"

    async def _go():
        bot = _make_bot()
        try:
            await bot.initialize()
            await bot.set_webhook(
                url=url,
                allowed_updates=["message", "callback_query"],
                drop_pending_updates=True,
            )
            info = await bot.get_webhook_info()
            print(f"✅ Webhook set:       {info.url}")
            print(f"   Pending updates:   {info.pending_update_count}")
            if info.last_error_message:
                print(f"   ⚠️  Last error:    {info.last_error_message}")
        finally:
            await bot.shutdown()

    asyncio.run(_go())


def check_webhook() -> None:
    """Print current webhook status — useful for debugging."""
    async def _go():
        bot = _make_bot()
        try:
            await bot.initialize()
            info = await bot.get_webhook_info()
            print(f"URL:         {info.url or '(not set)'}")
            print(f"Last error:  {info.last_error_message or 'none'}")
            print(f"Pending:     {info.pending_update_count}")
        finally:
            await bot.shutdown()
    asyncio.run(_go())


def unregister_webhook() -> None:
    """Switch back to polling (for local dev)."""
    async def _go():
        bot = _make_bot()
        try:
            await bot.initialize()
            await bot.delete_webhook(drop_pending_updates=True)
            print("✅ Webhook removed.")
        finally:
            await bot.shutdown()
    asyncio.run(_go())


if __name__ == "__main__":
    print(f"Dev server — webhook path: {WEBHOOK_PATH}")
    flask_app.run(port=5000, debug=False)