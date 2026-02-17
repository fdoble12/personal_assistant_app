"""
Telegram Bot for Personal Life OS
Ingestion engine — routes messages to DB or answers them directly.
"""
import logging
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import config
from database import Database
from claude_client import get_claude_client
from models import QuestionData, NoteData, FoodData, WorkoutData

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO if not config.DEBUG else logging.DEBUG,
)
logger = logging.getLogger(__name__)

db = Database()
claude = get_claude_client()

TG_MAX = 4096   # Telegram message character limit


# ── Helpers ────────────────────────────────────────────────────────────────

def _fmt_ts(ts: str) -> str:
    """Turn a Supabase ISO timestamp into a readable string."""
    try:
        return datetime.fromisoformat(ts).strftime("%b %d, %Y · %I:%M %p")
    except Exception:
        return ts


def _chunks(text: str) -> list[str]:
    """Split text into ≤4096-char chunks on newline boundaries."""
    parts, buf = [], ""
    for line in text.splitlines(keepends=True):
        if len(buf) + len(line) > TG_MAX:
            parts.append(buf)
            buf = ""
        buf += line
    if buf:
        parts.append(buf)
    return parts or [""]


async def _send(update: Update, text: str, md: bool = True) -> None:
    """Send, splitting if over Telegram's limit."""
    mode = "Markdown" if md else None
    for chunk in _chunks(text):
        await update.message.reply_text(chunk, parse_mode=mode)


# ── Commands ────────────────────────────────────────────────────────────────

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db.get_or_create_user(update.effective_user.id)
    await _send(update,
        "👋 *Welcome to your Personal Life OS!*\n\n"
        "Just send me a message and I'll figure out what to do:\n"
        "📝 Save notes & brain dumps\n"
        "🍽️ Log meals with macro estimates\n"
        "💪 Track workouts\n"
        "💬 Answer your health & fitness questions\n\n"
        "*Commands:*\n"
        "`/notes` — recent notes\n"
        "`/notes <keyword>` — search notes\n"
        "`/notes today` / `week` / `yesterday`\n"
        "`/summary` — today's stats\n"
        "`/profile` — your settings\n"
        "`/help` — this message\n\n"
        "*Examples:*\n"
        "• _Had eggs and toast for breakfast_\n"
        "• _30 min run this morning_\n"
        "• _Remember to call the dentist tomorrow_\n"
        "• _How many calories in a banana?_"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send(update,
        "🤖 *Personal Life OS Help*\n\n"
        "*What I save automatically:*\n"
        "• Food logs → `had pizza for dinner`\n"
        "• Workouts → `45 min gym session`\n"
        "• Notes / reminders → `remember to call dentist`\n\n"
        "*What I answer directly:*\n"
        "• Nutrition questions → `how many calories in X?`\n"
        "• Fitness advice → `good protein goal for my weight?`\n"
        "• General health questions\n\n"
        "*Commands:*\n"
        "`/notes` — last 10 notes\n"
        "`/notes dentist` — search by keyword\n"
        "`/notes today` / `yesterday` / `week` / `month`\n"
        "`/summary` — today's calorie & workout report\n"
        "`/profile` — view settings\n"
        "`/setgoal 75` — goal weight (kg)\n"
        "`/settarget 2000` — daily calorie target"
    )


async def notes_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /notes              → last 10 notes
    /notes today        → today's notes
    /notes yesterday    → yesterday's notes
    /notes week         → last 7 days
    /notes month        → last 30 days
    /notes <keyword>    → search
    """
    tid = update.effective_user.id
    await update.message.chat.send_action("typing")

    args = context.args
    today = datetime.now().date()

    try:
        if not args:
            notes = db.get_recent_notes(tid, limit=10)
            header = "📝 *Your last 10 notes*"
        else:
            kw = " ".join(args).lower().strip()
            if kw == "today":
                notes = db.get_notes_by_date_range(tid, today, today)
                header = f"📝 *Notes from today* ({today.strftime('%B %d')})"
            elif kw == "yesterday":
                yd = today - timedelta(days=1)
                notes = db.get_notes_by_date_range(tid, yd, yd)
                header = f"📝 *Notes from yesterday* ({yd.strftime('%B %d')})"
            elif kw in ("week", "this week"):
                notes = db.get_notes_by_date_range(tid, today - timedelta(days=7), today)
                header = "📝 *Notes — last 7 days*"
            elif kw in ("month", "this month"):
                notes = db.get_notes_by_date_range(tid, today - timedelta(days=30), today)
                header = "📝 *Notes — last 30 days*"
            else:
                notes = db.search_notes(tid, kw, limit=8)
                header = f'🔍 *Notes matching "{kw}"*'

        if not notes:
            await _send(update, f"{header}\n\n_No notes found._")
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

        await _send(update, "\n".join(lines))

    except Exception as exc:
        logger.error(f"[{tid}] /notes error: {exc}", exc_info=True)
        await update.message.reply_text("❌ Couldn't fetch notes. Please try again.")


async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tid = update.effective_user.id
    await update.message.chat.send_action("typing")

    try:
        s = db.get_daily_summary(tid)
        user = db.get_user_profile(tid)
        date_str = datetime.now().strftime("%A, %B %d, %Y")

        text = f"📊 *Daily Summary*\n_{date_str}_\n\n"

        text += "*🍽️ Nutrition*\n"
        if s.food_entries:
            text += f"Calories: {s.total_calories}"
            if s.calories_target:
                rem = s.calories_remaining
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
        if s.notes_count:
            text += f"Entries today: {s.notes_count} — use /notes to read them\n"
        else:
            text += "_No notes today_\n"

        if user and user.current_weight and user.goal_weight:
            diff = round(user.current_weight - user.goal_weight, 1)
            text += f"\n*⚖️ Weight*\nCurrent: {user.current_weight}kg · Goal: {user.goal_weight}kg\n"
            text += f"{'To lose: ' + str(diff) + 'kg' if diff > 0 else '🎉 Goal reached!'}\n"

        await _send(update, text)

    except Exception as exc:
        logger.error(f"[{tid}] /summary error: {exc}")
        await update.message.reply_text("❌ Couldn't generate summary. Please try again.")


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tid = update.effective_user.id
    user = db.get_user_profile(tid)

    lines = ["👤 *Your Profile*\n"]
    lines.append(f"Current Weight: {user.current_weight}kg" if user.current_weight else "Current Weight: _Not set_")
    lines.append(f"Goal Weight: {user.goal_weight}kg" if user.goal_weight else "Goal Weight: _Not set_")
    lines.append(f"Daily Calorie Target: {user.daily_calorie_target} kcal" if user.daily_calorie_target else "Daily Calorie Target: _Not set_")
    lines.append("\n*Update:* `/setgoal [weight]` · `/settarget [calories]`")
    await _send(update, "\n".join(lines))


async def setgoal_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tid = update.effective_user.id
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Usage: `/setgoal 75`", parse_mode="Markdown")
        return
    try:
        w = float(context.args[0])
        if not (20 < w < 300):
            raise ValueError
        db.update_user_profile(tid, {"goal_weight": w})
        await update.message.reply_text(f"✅ Goal weight set to *{w} kg*", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ Invalid weight. Example: `/setgoal 75`", parse_mode="Markdown")


async def settarget_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tid = update.effective_user.id
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Usage: `/settarget 2000`", parse_mode="Markdown")
        return
    try:
        cal = int(context.args[0])
        if not (500 <= cal <= 5000):
            raise ValueError
        db.update_user_profile(tid, {"daily_calorie_target": cal})
        await update.message.reply_text(f"✅ Daily calorie target set to *{cal} kcal*", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ Must be 500–5000. Example: `/settarget 2000`", parse_mode="Markdown")


# ── Main message handler ────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Route all non-command text through Claude.

    Claude decides:
      question → reply directly (nothing saved)
      note     → save to notes, confirm
      food     → save to food_logs, confirm with today's total
      workout  → save to workouts, confirm with today's total
    """
    tid = update.effective_user.id
    text = update.message.text

    await update.message.chat.send_action("typing")
    logger.info(f"[{tid}] Incoming: {text[:70]!r}")

    try:
        result = claude.classify_message(text)

        if isinstance(result, QuestionData):
            # ── Just answer — nothing written to DB ────────────────────
            logger.info(f"[{tid}] → question (not saved)")
            await _send(update, f"💬 {result.answer}", md=False)

        elif isinstance(result, NoteData):
            db.insert_note(tid, result.content, result.summary, result.tags)
            tags_str = f"\n🏷 {', '.join(result.tags)}" if result.tags else ""
            await _send(update,
                f"📝 *Note saved*\n_{result.summary}_{tags_str}\n\n"
                "Use /notes to read your notes."
            )
            logger.info(f"[{tid}] → note saved: {result.summary!r}")

        elif isinstance(result, FoodData):
            db.insert_food_log(tid, result.food_description,
                               result.calories, result.protein, result.carbs, result.fat)
            nutrition = db.get_daily_nutrition(tid)
            await _send(update,
                f"🍽️ *Logged:* {result.food_description}\n\n"
                f"• {result.calories} kcal\n"
                f"• Protein: {result.protein}g · Carbs: {result.carbs}g · Fat: {result.fat}g\n\n"
                f"*Today's total:* {nutrition['total_calories']} kcal "
                f"({nutrition['entry_count']} entries)"
            )
            logger.info(f"[{tid}] → food saved: {result.food_description} {result.calories} kcal")

        elif isinstance(result, WorkoutData):
            db.insert_workout(tid, result.activity_type, result.duration_mins,
                              result.distance_km, result.notes)
            workouts = db.get_daily_workouts(tid)
            total_mins = sum(w["duration_mins"] or 0 for w in workouts)
            reply = (
                f"💪 *Logged:* {result.activity_type}\n\n"
                f"⏱ {result.duration_mins} mins"
            )
            if result.distance_km:
                reply += f" · 📏 {result.distance_km} km"
            if result.notes:
                reply += f"\n_{result.notes}_"
            reply += f"\n\n*Today's activity:* {total_mins} mins total"
            await _send(update, reply)
            logger.info(f"[{tid}] → workout saved: {result.activity_type} {result.duration_mins} min")

    except Exception as exc:
        logger.error(f"[{tid}] handle_message error: {exc}", exc_info=True)
        await update.message.reply_text(
            "❌ Something went wrong. Try rephrasing, or use /help for examples."
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Unhandled error: {context.error}", exc_info=context.error)


# ── Entry point ─────────────────────────────────────────────────────────────

def main() -> None:
    config.validate_config()

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("notes", notes_command))
    app.add_handler(CommandHandler("summary", summary_command))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("setgoal", setgoal_command))
    app.add_handler(CommandHandler("settarget", settarget_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    logger.info("🚀 Personal Life OS bot running…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()