"""
webhook_bot.py — PythonAnywhere WSGI entry point
=================================================
Each request gets its own asyncio.run() → its own Bot/httpx client.
Zero shared async state. See previous comments for full architecture rationale.

New commands in this version:
  /setweight <kg>              — update current weight
  /setmacros <p> <c> <f>       — set daily protein/carbs/fat targets (grams)
  /meals [today|yesterday|N]   — list logged meals with per-meal and daily macros
  /recommend                   — Claude suggests what to eat next based on today's data
  /insights                    — holistic 7-day wellness analysis (food+workouts+notes)
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta

from flask import Flask, abort, request as flask_request
from telegram import Bot
from telegram.request import HTTPXRequest

import config
from database import Database
from claude_client import get_claude_client
from models import QuestionData, NoteData, FoodData, WorkoutData

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

config.validate_config(require_telegram=True)

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change-me-to-something-random")
WEBHOOK_PATH   = f"/webhook/{WEBHOOK_SECRET}"

db     = Database()
claude = get_claude_client()


# ── Bot / helpers ─────────────────────────────────────────────────────────────

def _make_bot() -> Bot:
    return Bot(
        token=config.TELEGRAM_BOT_TOKEN,
        request=HTTPXRequest(connection_pool_size=1),
    )


def _fmt_ts(ts: str) -> str:
    try:
        return datetime.fromisoformat(ts).strftime("%b %d · %I:%M %p")
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


# ── Command handlers ──────────────────────────────────────────────────────────

async def _cmd_start(bot, chat_id, user_id):
    db.get_or_create_user(user_id)
    await _send(bot, chat_id,
        "👋 *Welcome to your Personal Life OS!*\n\n"
        "Just send me a message and I'll figure out what to do:\n"
        "📝 Save notes, mood & brain dumps\n"
        "🍽️ Log meals with auto macro estimates\n"
        "💪 Track workouts\n"
        "💬 Answer health & fitness questions\n\n"
        "*Commands:*\n"
        "`/meals` — today's meals & macros\n"
        "`/recommend` — what to eat next\n"
        "`/insights` — 7-day wellness analysis\n"
        "`/notes` — recent notes\n"
        "`/summary` — today's stats\n"
        "`/profile` — your settings\n"
        "`/setweight 80` — update current weight\n"
        "`/setmacros 150 200 60` — set P/C/F targets (g)\n"
        "`/setgoal 75` — goal weight\n"
        "`/settarget 2000` — daily calorie target\n"
        "`/help` — full command list"
    )


async def _cmd_help(bot, chat_id):
    await _send(bot, chat_id,
        "🤖 *Personal Life OS — Commands*\n\n"
        "*Logging (auto-detected from plain text):*\n"
        "• `had pizza for dinner` → food log\n"
        "• `45 min gym session` → workout\n"
        "• `feeling tired today` → wellness note\n"
        "• `productive morning` → productivity note\n\n"
        "*Food & Nutrition:*\n"
        "`/meals` — today's meals & macro breakdown\n"
        "`/meals yesterday` — yesterday's meals\n"
        "`/recommend` — meal suggestion based on remaining macros\n\n"
        "*Insights:*\n"
        "`/insights` — 7-day holistic wellness analysis\n"
        "`/summary` — today's calorie & workout report\n\n"
        "*Notes:*\n"
        "`/notes` — last 10 notes\n"
        "`/notes <keyword>` — search\n"
        "`/notes today` / `yesterday` / `week`\n\n"
        "*Profile:*\n"
        "`/profile` — view all settings\n"
        "`/setweight 80` — current weight (kg)\n"
        "`/setgoal 75` — goal weight (kg)\n"
        "`/settarget 2000` — daily calorie target\n"
        "`/setmacros 150 200 60` — protein/carbs/fat targets (g)"
    )


async def _cmd_profile(bot, chat_id, user_id):
    user = db.get_user_profile(user_id)
    text = "👤 *Your Profile*\n\n"
    text += f"⚖️ Current weight:  {user.current_weight} kg\n" if user.current_weight else "⚖️ Current weight:  _not set_ — use /setweight\n"
    text += f"🎯 Goal weight:     {user.goal_weight} kg\n"    if user.goal_weight    else "🎯 Goal weight:     _not set_ — use /setgoal\n"
    text += f"🔥 Calorie target:  {user.daily_calorie_target} kcal/day\n" if user.daily_calorie_target else "🔥 Calorie target:  _not set_ — use /settarget\n"
    if user.has_macro_targets():
        text += f"🥩 Protein target:  {user.protein_target}g\n"
        text += f"🍞 Carbs target:    {user.carbs_target}g\n"
        text += f"🥑 Fat target:      {user.fat_target}g\n"
    else:
        text += "📊 Macro targets:   _not set_ — use /setmacros P C F\n"
    await _send(bot, chat_id, text)


async def _cmd_setweight(bot, chat_id, user_id, args):
    if not args:
        await _send(bot, chat_id, "Usage: `/setweight 80.5`")
        return
    try:
        w = float(args[0])
        if not (20 < w < 300):
            raise ValueError
        db.update_user_profile(user_id, {"current_weight": w})
        user = db.get_user_profile(user_id)
        reply = f"✅ Current weight updated to *{w} kg*"
        if user.goal_weight:
            diff = round(w - user.goal_weight, 1)
            reply += f"\n{'📉 ' + str(diff) + ' kg to your goal' if diff > 0 else '🎉 You have reached your goal weight!'}"
        await _send(bot, chat_id, reply)
    except ValueError:
        await _send(bot, chat_id, "❌ Invalid weight. Example: `/setweight 80.5`")


async def _cmd_setgoal(bot, chat_id, user_id, args):
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


async def _cmd_settarget(bot, chat_id, user_id, args):
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


async def _cmd_setmacros(bot, chat_id, user_id, args):
    """
    /setmacros <protein_g> <carbs_g> <fat_g>
    Example: /setmacros 150 200 65
    """
    if len(args) != 3:
        await _send(bot, chat_id,
            "Usage: `/setmacros <protein> <carbs> <fat>` (all in grams)\n"
            "Example: `/setmacros 150 200 65`\n\n"
            "_Not sure what to set? A common starting point:_\n"
            "Protein: 0.8–1.2× your body weight in kg\n"
            "Fat: 20–35% of daily calories ÷ 9\n"
            "Carbs: fill the remaining calories ÷ 4"
        )
        return
    try:
        p, c, f = float(args[0]), float(args[1]), float(args[2])
        if any(x < 0 or x > 1000 for x in [p, c, f]):
            raise ValueError
        db.update_user_profile(user_id, {
            "protein_target": p,
            "carbs_target":   c,
            "fat_target":     f,
        })
        kcal = round(p * 4 + c * 4 + f * 9)
        await _send(bot, chat_id,
            f"✅ *Macro targets set*\n\n"
            f"🥩 Protein: {p}g\n"
            f"🍞 Carbs:   {c}g\n"
            f"🥑 Fat:     {f}g\n"
            f"🔥 Total:   ~{kcal} kcal/day\n\n"
            "_Use /recommend anytime to see what to eat next based on these targets._"
        )
    except ValueError:
        await _send(bot, chat_id, "❌ Invalid values. Example: `/setmacros 150 200 65`")


async def _cmd_meals(bot, chat_id, user_id, args):
    """
    /meals              — today's meals
    /meals yesterday    — yesterday
    /meals 3            — last 3 days
    """
    await bot.send_chat_action(chat_id=chat_id, action="typing")

    today = datetime.now().date()

    if not args:
        target_date = today
        label = "Today"
    elif args[0].lower() == "yesterday":
        target_date = today - timedelta(days=1)
        label = "Yesterday"
    else:
        try:
            n = int(args[0])
            # Multi-day: show a range
            start = today - timedelta(days=n - 1)
            logs = db.get_food_logs_by_date_range(user_id, start, today)
            await _send_meal_range(bot, chat_id, user_id, logs, f"Last {n} days", start, today)
            return
        except ValueError:
            target_date = today
            label = "Today"

    nutrition = db.get_daily_nutrition(user_id, target_date)
    logs = nutrition["entries"]

    if not logs:
        await _send(bot, chat_id, f"🍽️ *{label}'s meals*\n\n_Nothing logged yet._")
        return

    user = db.get_user_profile(user_id)
    lines = [f"🍽️ *{label}'s meals*\n"]

    for i, log in enumerate(sorted(logs, key=lambda x: x["created_at"]), 1):
        ts = _fmt_ts(log["created_at"])
        lines.append(
            f"*{i}. {log['food_description']}* — {ts}\n"
            f"   {log['calories']} kcal | P:{log['protein']}g C:{log['carbs']}g F:{log['fat']}g"
        )

    lines.append(f"\n*📊 Daily totals:*")
    lines.append(f"🔥 Calories: {nutrition['total_calories']}")
    if user and user.daily_calorie_target:
        rem = user.daily_calorie_target - nutrition['total_calories']
        icon = "✅" if rem >= 0 else "⚠️"
        lines.append(f"   {icon} Target: {user.daily_calorie_target} | Remaining: {abs(rem)} {'left' if rem >= 0 else 'over'}")
    lines.append(f"🥩 Protein: {nutrition['total_protein']}g", )
    if user and user.protein_target:
        rem_p = round(user.protein_target - nutrition['total_protein'], 1)
        lines.append(f"   Target: {user.protein_target}g | Remaining: {abs(rem_p)}g {'left' if rem_p >= 0 else 'over'}")
    lines.append(f"🍞 Carbs:   {nutrition['total_carbs']}g")
    if user and user.carbs_target:
        rem_c = round(user.carbs_target - nutrition['total_carbs'], 1)
        lines.append(f"   Target: {user.carbs_target}g | Remaining: {abs(rem_c)}g {'left' if rem_c >= 0 else 'over'}")
    lines.append(f"🥑 Fat:     {nutrition['total_fat']}g")
    if user and user.fat_target:
        rem_f = round(user.fat_target - nutrition['total_fat'], 1)
        lines.append(f"   Target: {user.fat_target}g | Remaining: {abs(rem_f)}g {'left' if rem_f >= 0 else 'over'}")

    await _send(bot, chat_id, "\n".join(lines))


async def _send_meal_range(bot, chat_id, user_id, logs, label, start, end):
    """Helper: show meal logs grouped by date for multi-day /meals N."""
    if not logs:
        await _send(bot, chat_id, f"🍽️ *{label}*\n\n_Nothing logged._")
        return

    by_day: dict = {}
    for log in logs:
        d = log["created_at"][:10]
        by_day.setdefault(d, []).append(log)

    lines = [f"🍽️ *{label}*\n"]
    for d in sorted(by_day.keys(), reverse=True):
        entries = by_day[d]
        day_cal = sum(e["calories"] or 0 for e in entries)
        day_p   = sum(float(e["protein"] or 0) for e in entries)
        day_c   = sum(float(e["carbs"] or 0) for e in entries)
        day_f   = sum(float(e["fat"] or 0) for e in entries)
        lines.append(f"*📅 {d}* — {day_cal} kcal | P:{day_p:.0f}g C:{day_c:.0f}g F:{day_f:.0f}g")
        for e in sorted(entries, key=lambda x: x["created_at"]):
            lines.append(f"  • {e['food_description']} ({e['calories']} kcal)")
        lines.append("")

    await _send(bot, chat_id, "\n".join(lines))


async def _cmd_recommend(bot, chat_id, user_id):
    """Ask Claude what to eat next based on today's remaining macros."""
    await bot.send_chat_action(chat_id=chat_id, action="typing")

    nutrition = db.get_daily_nutrition(user_id)
    user      = db.get_user_profile(user_id)

    context = {
        "eaten_today": nutrition["entries"],
        "totals": {
            "calories": nutrition["total_calories"],
            "protein":  nutrition["total_protein"],
            "carbs":    nutrition["total_carbs"],
            "fat":      nutrition["total_fat"],
        },
        "profile": {
            "daily_calorie_target": user.daily_calorie_target if user else None,
            "protein_target":       user.protein_target if user else None,
            "carbs_target":         user.carbs_target if user else None,
            "fat_target":           user.fat_target if user else None,
            "current_weight":       user.current_weight if user else None,
            "goal_weight":          user.goal_weight if user else None,
        }
    }

    recommendation = claude.generate_recommendation(context)
    await _send(bot, chat_id, f"🍽️ *Meal Recommendation*\n\n{recommendation}", md=False)


async def _cmd_insights(bot, chat_id, user_id):
    """Generate a 7-day holistic wellness analysis from all logged data."""
    await bot.send_chat_action(chat_id=chat_id, action="typing")
    await _send(bot, chat_id,
        "🔍 _Analyzing your last 7 days — food, workouts, mood & notes..._",
        md=True
    )

    context  = db.get_wellness_context(user_id, days=7)
    insights = claude.generate_insights(context)
    await _send(bot, chat_id, f"🧠 *Your 7-Day Wellness Insights*\n\n{insights}", md=False)


async def _cmd_notes(bot, chat_id, user_id, args):
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


async def _cmd_summary(bot, chat_id, user_id):
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
        text += f"\nP:{s.total_protein}g | C:{s.total_carbs}g | F:{s.total_fat}g"
        if user and user.has_macro_targets():
            text += f"\nTargets → {user.macro_summary()}"
        text += f"\nMeals: {s.food_entries} — see /meals for details\n"
    else:
        text += "_No meals logged yet_\n"

    text += "\n*💪 Activity*\n"
    if s.workout_count:
        text += f"Sessions: {s.workout_count} · Total: {s.workout_minutes} mins\n"
    else:
        text += "_No workouts logged yet_\n"

    text += "\n*📝 Notes & Wellness*\n"
    text += (f"Entries today: {s.notes_count} — use /insights for patterns\n"
             if s.notes_count else "_No notes today_\n")

    if user and user.current_weight and user.goal_weight:
        diff = round(user.current_weight - user.goal_weight, 1)
        text += f"\n*⚖️ Weight*\nCurrent: {user.current_weight}kg · Goal: {user.goal_weight}kg\n"
        text += f"{'To lose: ' + str(diff) + 'kg' if diff > 0 else '🎉 Goal reached!'}\n"

    await _send(bot, chat_id, text)


# ── Main message handler ──────────────────────────────────────────────────────

async def _handle_text(bot, chat_id, user_id, text):
    await bot.send_chat_action(chat_id=chat_id, action="typing")
    result = claude.classify_message(text)

    if isinstance(result, QuestionData):
        logger.info(f"[{user_id}] → question")
        await _send(bot, chat_id, f"💬 {result.answer}", md=False)

    elif isinstance(result, NoteData):
        db.insert_note(user_id, result.content, result.summary, result.tags)
        tags_str = f"\n🏷 {', '.join(result.tags)}" if result.tags else ""
        # Surface wellness-relevant tags back to the user
        wellness_tags = {"mood", "energy", "sleep", "stress", "productivity", "focus"}
        matched = [t for t in result.tags if t in wellness_tags]
        tip = f"\n\n_Tip: /insights shows patterns across your {', '.join(matched)} entries_" if matched else ""
        await _send(bot, chat_id,
            f"📝 *Note saved*\n_{result.summary}_{tags_str}{tip}")
        logger.info(f"[{user_id}] → note: {result.summary!r}")

    elif isinstance(result, FoodData):
        db.insert_food_log(user_id, result.food_description,
                           result.calories, result.protein, result.carbs, result.fat)
        nutrition = db.get_daily_nutrition(user_id)
        user      = db.get_user_profile(user_id)

        reply  = (f"🍽️ *Logged:* {result.food_description}\n\n"
                  f"• {result.calories} kcal | P:{result.protein}g C:{result.carbs}g F:{result.fat}g\n\n"
                  f"*Today so far:* {nutrition['total_calories']} kcal")

        if user and user.daily_calorie_target:
            rem = user.daily_calorie_target - nutrition["total_calories"]
            reply += f" / {user.daily_calorie_target} ({abs(rem)} {'left' if rem >= 0 else 'over ⚠️'})"

        if user and user.has_macro_targets():
            rem_p = round(user.protein_target - nutrition["total_protein"], 1)
            rem_c = round(user.carbs_target   - nutrition["total_carbs"],   1)
            rem_f = round(user.fat_target      - nutrition["total_fat"],     1)
            reply += (f"\nP: {nutrition['total_protein']}g / {user.protein_target}g "
                      f"({'✅' if rem_p <= 0 else str(abs(rem_p))+'g left'})\n"
                      f"C: {nutrition['total_carbs']}g / {user.carbs_target}g "
                      f"({'✅' if rem_c <= 0 else str(abs(rem_c))+'g left'})\n"
                      f"F: {nutrition['total_fat']}g / {user.fat_target}g "
                      f"({'✅' if rem_f <= 0 else str(abs(rem_f))+'g left'})")
            reply += "\n\n_Use /recommend for what to eat next_"

        await _send(bot, chat_id, reply)
        logger.info(f"[{user_id}] → food: {result.food_description} {result.calories} kcal")

    elif isinstance(result, WorkoutData):
        db.insert_workout(user_id, result.activity_type, result.duration_mins,
                          result.distance_km, result.notes)
        workouts   = db.get_daily_workouts(user_id)
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
    msg = payload.get("message") or payload.get("edited_message")
    if not msg:
        return

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

            dispatch_map = {
                "start":      lambda: _cmd_start(bot, chat_id, user_id),
                "help":       lambda: _cmd_help(bot, chat_id),
                "profile":    lambda: _cmd_profile(bot, chat_id, user_id),
                "setweight":  lambda: _cmd_setweight(bot, chat_id, user_id, args),
                "setgoal":    lambda: _cmd_setgoal(bot, chat_id, user_id, args),
                "settarget":  lambda: _cmd_settarget(bot, chat_id, user_id, args),
                "setmacros":  lambda: _cmd_setmacros(bot, chat_id, user_id, args),
                "meals":      lambda: _cmd_meals(bot, chat_id, user_id, args),
                "recommend":  lambda: _cmd_recommend(bot, chat_id, user_id),
                "insights":   lambda: _cmd_insights(bot, chat_id, user_id),
                "notes":      lambda: _cmd_notes(bot, chat_id, user_id, args),
                "summary":    lambda: _cmd_summary(bot, chat_id, user_id),
            }

            handler = dispatch_map.get(command)
            if handler:
                await handler()
            else:
                await _send(bot, chat_id, "Unknown command. Try /help")
        else:
            await _handle_text(bot, chat_id, user_id, text)

    except Exception as exc:
        logger.error(f"[{user_id}] Dispatch error: {exc}", exc_info=True)
        try:
            await _send(bot, chat_id, "❌ Something went wrong. Try again or use /help", md=False)
        except Exception:
            pass
    finally:
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
    asyncio.run(_dispatch(payload))
    return "ok", 200


@flask_app.route("/health")
def health():
    return "ok", 200


@flask_app.route("/")
def index():
    return "Personal Life OS — running.", 200


# ── Webhook management ────────────────────────────────────────────────────────

def register_webhook(pythonanywhere_username: str) -> None:
    url = f"https://{pythonanywhere_username}.pythonanywhere.com{WEBHOOK_PATH}"
    async def _go():
        bot = _make_bot()
        try:
            await bot.initialize()
            await bot.set_webhook(url=url, allowed_updates=["message", "callback_query"],
                                  drop_pending_updates=True)
            info = await bot.get_webhook_info()
            print(f"✅ Webhook set: {info.url}")
            if info.last_error_message:
                print(f"   ⚠️  Last error: {info.last_error_message}")
        finally:
            await bot.shutdown()
    asyncio.run(_go())


def check_webhook() -> None:
    async def _go():
        bot = _make_bot()
        try:
            await bot.initialize()
            info = await bot.get_webhook_info()
            print(f"URL:        {info.url or '(not set)'}")
            print(f"Last error: {info.last_error_message or 'none'}")
            print(f"Pending:    {info.pending_update_count}")
        finally:
            await bot.shutdown()
    asyncio.run(_go())


def unregister_webhook() -> None:
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