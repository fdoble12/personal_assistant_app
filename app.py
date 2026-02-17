"""
Streamlit Dashboard for Personal Life OS
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, date

import config
from database import Database
from claude_client import get_claude_client
from models import UserProfile

st.set_page_config(
    page_title="Personal Life OS",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def get_db() -> Database:
    return Database()

@st.cache_resource
def get_claude():
    return get_claude_client()

db     = get_db()
claude = get_claude()


# ── Sidebar ──────────────────────────────────────────────────────────────────

def render_sidebar():
    st.sidebar.title("🧠 Personal Life OS")
    st.sidebar.markdown("---")

    telegram_id = st.sidebar.number_input(
        "Your Telegram ID",
        min_value=1, value=123456789,
        help="Get it from @userinfobot on Telegram",
    )

    st.sidebar.subheader("Date Range")
    preset = st.sidebar.selectbox("Preset", ["Today", "Last 7 Days", "Last 30 Days", "Custom"])
    today  = datetime.now().date()

    if preset == "Today":
        start, end = today, today
    elif preset == "Last 7 Days":
        start, end = today - timedelta(days=7), today
    elif preset == "Last 30 Days":
        start, end = today - timedelta(days=30), today
    else:
        c1, c2 = st.sidebar.columns(2)
        start  = c1.date_input("From", today - timedelta(days=30))
        end    = c2.date_input("To", today)

    return int(telegram_id), start, end


# ── Delete helper ─────────────────────────────────────────────────────────────

def _delete_button(label, prefix, row_id, tid, delete_fn):
    key = f"confirm_del_{prefix}_{row_id}"
    if st.session_state.get(key):
        c1, c2 = st.columns([1, 1])
        with c1:
            if st.button("✅ Confirm", key=f"yes_{prefix}_{row_id}"):
                ok = delete_fn(tid, row_id)
                st.toast("Deleted ✓" if ok else "Not found", icon="🗑️")
                del st.session_state[key]
                st.rerun()
        with c2:
            if st.button("❌ Cancel", key=f"no_{prefix}_{row_id}"):
                del st.session_state[key]
                st.rerun()
    else:
        if st.button(f"🗑 {label}", key=f"del_{prefix}_{row_id}"):
            st.session_state[key] = True
            st.rerun()


# ── DASHBOARD ─────────────────────────────────────────────────────────────────

def render_dashboard(tid, start, end):
    st.header("📊 Dashboard")
    user = db.get_user_profile(tid)
    if not user:
        st.warning("User not found. Check Telegram ID in sidebar.")
        return

    _metrics(tid, start, end)
    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        _calorie_chart(tid, start, end, user)
        _macro_pie(tid, start, end)
    with c2:
        _workout_chart(tid, start, end)
        _weight_gauge(user)


def _metrics(tid, start, end):
    food     = db.get_food_logs_by_date_range(tid, start, end)
    workouts = db.get_workouts_by_date_range(tid, start, end)
    notes    = db.get_notes_by_date_range(tid, start, end)
    days     = max(1, (end - start).days + 1)
    total_cal = sum(r["calories"] or 0 for r in food)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Avg Daily Calories", f"{total_cal // days:,} kcal")
    c2.metric("Workouts", len(workouts))
    c3.metric("Workout Time", f"{sum(w['duration_mins'] or 0 for w in workouts)} mins")
    c4.metric("Notes / Journal", len(notes))


def _calorie_chart(tid, start, end, user):
    st.subheader("📈 Daily Calorie Intake")
    food = db.get_food_logs_by_date_range(tid, start, end)
    if not food:
        st.info("No food logs in this range.")
        return
    df    = pd.DataFrame(food)
    df["date"] = pd.to_datetime(df["created_at"]).dt.date
    daily = df.groupby("date")["calories"].sum().reset_index().sort_values("date")
    fig   = go.Figure()
    fig.add_trace(go.Bar(x=daily["date"], y=daily["calories"],
                         name="Calories", marker_color="rgb(99,110,250)"))
    if user.daily_calorie_target:
        fig.add_hline(y=user.daily_calorie_target, line_dash="dash",
                      line_color="red",
                      annotation_text=f"Target: {user.daily_calorie_target} kcal")
    fig.update_layout(xaxis_title="Date", yaxis_title="Calories",
                      hovermode="x unified", height=300)
    st.plotly_chart(fig, use_container_width=True)


def _macro_pie(tid, start, end):
    st.subheader("🥗 Macro Distribution")
    food = db.get_food_logs_by_date_range(tid, start, end)
    if not food:
        st.info("No food logs in this range.")
        return
    df  = pd.DataFrame(food)
    fig = go.Figure(data=[go.Pie(
        labels=["Protein", "Carbs", "Fat"],
        values=[df["protein"].sum(), df["carbs"].sum(), df["fat"].sum()],
        hole=0.35, marker_colors=["#FF6B6B", "#4ECDC4", "#FFE66D"],
    )])
    fig.update_layout(height=300)
    st.plotly_chart(fig, use_container_width=True)


def _workout_chart(tid, start, end):
    st.subheader("💪 Workout Frequency")
    workouts = db.get_workouts_by_date_range(tid, start, end)
    if not workouts:
        st.info("No workouts in this range.")
        return
    df     = pd.DataFrame(workouts)
    counts = df["activity_type"].value_counts().reset_index()
    counts.columns = ["Activity", "Count"]
    fig = px.bar(counts, x="Activity", y="Count",
                 color="Count", color_continuous_scale="Viridis")
    fig.update_layout(height=300, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)


def _weight_gauge(user):
    st.subheader("⚖️ Weight Progress")
    if not (user.current_weight and user.goal_weight):
        st.info("Set current & goal weight in your Profile tab.")
        return
    diff = user.current_weight - user.goal_weight
    if diff <= 0:
        st.success("🎉 Goal weight reached!")
        return
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=user.current_weight,
        delta={"reference": user.goal_weight, "suffix": " kg"},
        gauge={
            "axis": {"range": [None, user.current_weight + 10]},
            "bar": {"color": "darkblue"},
            "steps": [
                {"range": [0, user.goal_weight], "color": "lightgreen"},
                {"range": [user.goal_weight, user.current_weight], "color": "lightyellow"},
            ],
            "threshold": {"line": {"color": "red", "width": 4},
                          "thickness": 0.75, "value": user.goal_weight},
        },
        title={"text": "Current Weight (kg)"},
    ))
    fig.update_layout(height=300)
    st.plotly_chart(fig, use_container_width=True)
    st.metric("Still to lose", f"{diff:.1f} kg")


# ── MEALS TAB ────────────────────────────────────────────────────────────────

def render_meals(tid, start, end):
    st.header("🍽️ Meals & Macros")
    user = db.get_user_profile(tid)

    logs = db.get_food_logs_by_date_range(tid, start, end)
    if not logs:
        st.info("No meals logged in this date range.")
        return

    df = pd.DataFrame(logs)
    df["date"]    = pd.to_datetime(df["created_at"]).dt.date
    df["protein"] = df["protein"].astype(float)
    df["carbs"]   = df["carbs"].astype(float)
    df["fat"]     = df["fat"].astype(float)

    # ── Summary metrics
    total_cal = int(df["calories"].sum())
    total_p   = round(df["protein"].sum(), 1)
    total_c   = round(df["carbs"].sum(), 1)
    total_f   = round(df["fat"].sum(), 1)
    days      = max(1, (end - start).days + 1)

    st.subheader("Range Totals")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Calories", f"{total_cal:,} kcal", f"~{total_cal//days}/day")
    c2.metric("Protein",  f"{total_p}g",  f"~{round(total_p/days,1)}/day")
    c3.metric("Carbs",    f"{total_c}g",  f"~{round(total_c/days,1)}/day")
    c4.metric("Fat",      f"{total_f}g",  f"~{round(total_f/days,1)}/day")

    # ── Macro progress vs targets
    if user and user.has_macro_targets() and (end - start).days == 0:
        st.subheader("Today vs Targets")
        cc1, cc2, cc3 = st.columns(3)
        for col, macro, target, label in [
            (cc1, total_p, user.protein_target, "🥩 Protein"),
            (cc2, total_c, user.carbs_target,   "🍞 Carbs"),
            (cc3, total_f, user.fat_target,      "🥑 Fat"),
        ]:
            pct = min(int(macro / target * 100), 100) if target else 0
            col.metric(label, f"{macro}g / {target}g")
            col.progress(pct / 100)

    # ── Daily macro stacked bar
    st.subheader("📊 Daily Macro Breakdown")
    daily = df.groupby("date").agg(
        calories=("calories", "sum"),
        protein=("protein",  "sum"),
        carbs=("carbs",    "sum"),
        fat=("fat",      "sum"),
    ).reset_index().sort_values("date")

    fig = go.Figure()
    fig.add_trace(go.Bar(name="Protein", x=daily["date"], y=daily["protein"],
                         marker_color="#FF6B6B"))
    fig.add_trace(go.Bar(name="Carbs",   x=daily["date"], y=daily["carbs"],
                         marker_color="#4ECDC4"))
    fig.add_trace(go.Bar(name="Fat",     x=daily["date"], y=daily["fat"],
                         marker_color="#FFE66D"))
    fig.update_layout(barmode="stack", height=320,
                      xaxis_title="Date", yaxis_title="Grams")
    if user and user.protein_target:
        total_macro_target = user.protein_target + user.carbs_target + user.fat_target
        fig.add_hline(y=total_macro_target, line_dash="dot", line_color="white",
                      annotation_text="Macro target total")
    st.plotly_chart(fig, use_container_width=True)

    # ── Per-day meal detail
    st.subheader("📋 Meal Log")
    for d in sorted(daily["date"].tolist(), reverse=True):
        day_logs = [r for r in logs if r["created_at"][:10] == str(d)]
        day_cal  = sum(r["calories"] or 0 for r in day_logs)
        day_p    = sum(float(r["protein"] or 0) for r in day_logs)
        day_c    = sum(float(r["carbs"] or 0) for r in day_logs)
        day_f    = sum(float(r["fat"] or 0) for r in day_logs)

        with st.expander(
            f"📅 {d}  —  {day_cal} kcal | P:{day_p:.0f}g C:{day_c:.0f}g F:{day_f:.0f}g"
        ):
            for row in sorted(day_logs, key=lambda x: x["created_at"]):
                ts = datetime.fromisoformat(row["created_at"]).strftime("%I:%M %p")
                st.markdown(
                    f"**{row['food_description']}** — {ts}  \n"
                    f"{row['calories']} kcal | P:{row['protein']}g  C:{row['carbs']}g  F:{row['fat']}g"
                )
                _delete_button("Delete", "food_m", row["id"], tid, db.delete_food_log)
                st.divider()


# ── INSIGHTS TAB ──────────────────────────────────────────────────────────────

def render_insights(tid):
    st.header("🧠 Wellness Insights")
    st.caption("Claude analyzes your last 7 days of food, workouts, notes, mood & productivity entries.")

    user = db.get_user_profile(tid)
    context = db.get_wellness_context(tid, days=7)
    totals  = context.get("totals", {})

    # ── Quick data summary so user knows what's being analyzed
    c1, c2, c3 = st.columns(3)
    c1.metric("Meals logged", totals.get("food_entries", 0), "last 7 days")
    c2.metric("Workouts",     totals.get("workouts", 0),      "last 7 days")
    c3.metric("Notes/Journal", totals.get("notes", 0),        "last 7 days")

    if totals.get("food_entries", 0) + totals.get("workouts", 0) + totals.get("notes", 0) == 0:
        st.info("Not enough data yet. Log some meals, workouts, and daily notes first!")
        st.markdown(
            "**Tips for better insights:**\n"
            "- Log meals via the bot: `had oatmeal for breakfast`\n"
            "- Log mood: `feeling energized and focused today`\n"
            "- Log sleep: `slept poorly last night, only 5 hours`\n"
            "- Log workouts: `30 min run`\n"
            "The more you log, the richer the insights."
        )
        return

    st.markdown("---")

    # ── Note tags cloud (show what wellness signals we're picking up)
    all_notes = context.get("notes", [])
    all_tags  = [t for n in all_notes for t in (n.get("tags") or [])]
    wellness_tags = {"mood", "energy", "sleep", "stress", "productivity", "focus", "motivation", "social", "health"}
    found_tags = [t for t in all_tags if t in wellness_tags]
    if found_tags:
        from collections import Counter
        tag_counts = Counter(found_tags)
        st.subheader("📌 Wellness signals detected in your notes")
        cols = st.columns(min(len(tag_counts), 5))
        for i, (tag, count) in enumerate(tag_counts.most_common(5)):
            cols[i % 5].metric(tag.capitalize(), f"×{count}")

    # ── Generate insights button
    st.markdown("---")
    if st.button("✨ Generate Insights", type="primary", use_container_width=True):
        with st.spinner("Claude is analyzing your last 7 days..."):
            try:
                insights = claude.generate_insights(context)
                st.session_state["last_insights"] = insights
                st.session_state["insights_ts"] = datetime.now().strftime("%B %d, %Y at %I:%M %p")
            except Exception as e:
                st.error(f"Error generating insights: {e}")

    if "last_insights" in st.session_state:
        st.markdown(f"*Generated {st.session_state.get('insights_ts', '')}*")
        st.markdown(st.session_state["last_insights"])

    # ── Nutrition trends chart
    daily_nutrition = context.get("daily_nutrition", {})
    if daily_nutrition:
        st.markdown("---")
        st.subheader("📈 7-Day Nutrition Trend")
        rows = [
            {"date": d, **data}
            for d, data in sorted(daily_nutrition.items())
        ]
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df["date"], y=df["calories"],
                                 mode="lines+markers", name="Calories",
                                 line=dict(color="rgb(99,110,250)", width=2)))
        if user and user.daily_calorie_target:
            fig.add_hline(y=user.daily_calorie_target, line_dash="dash",
                          line_color="red", annotation_text="Calorie target")
        fig.update_layout(height=250, xaxis_title="Date", yaxis_title="Calories")
        st.plotly_chart(fig, use_container_width=True)


# ── JOURNAL TAB ──────────────────────────────────────────────────────────────

def render_journal(tid, start, end):
    st.header("📝 Journal")
    notes  = db.get_notes_by_date_range(tid, start, end)
    if not notes:
        st.info("No notes in this range. Send thoughts via the Telegram bot!")
        return

    search = st.text_input("🔍 Search", placeholder="Search content, tags…")
    if search:
        q     = search.lower()
        notes = [n for n in notes
                 if q in n["content"].lower()
                 or q in n["summary"].lower()
                 or any(q in t.lower() for t in (n.get("tags") or []))]

    st.caption(f"{len(notes)} note(s)")

    for note in notes:
        ts   = datetime.fromisoformat(note["created_at"]).strftime("%B %d, %Y · %I:%M %p")
        tags = note.get("tags") or []
        tag_str = f"  🏷 {', '.join(tags)}" if tags else ""
        with st.expander(f"📌 {note['summary']} — {ts}{tag_str}"):
            st.write(note["content"])
            st.markdown("---")
            _delete_button("Delete note", "note", note["id"], tid, db.delete_note)


# ── DATA ENTRY TAB ────────────────────────────────────────────────────────────

def render_data_entry(tid, start, end):
    st.header("✏️ Data Entry & History")
    t1, t2, t3, t4 = st.tabs(["👤 Profile", "🍽️ Food", "💪 Workouts", "📝 Notes"])

    with t1:
        _profile_form(tid)
    with t2:
        _food_entry_form(tid)
        st.markdown("---")
        _food_history(tid, start, end)
    with t3:
        _workout_entry_form(tid)
        st.markdown("---")
        _workout_history(tid, start, end)
    with t4:
        _note_entry_form(tid)
        st.markdown("---")
        _note_history(tid, start, end)


def _profile_form(tid):
    st.subheader("👤 Your Profile")
    user = db.get_user_profile(tid)

    with st.form("profile_form"):
        st.markdown("**Weight**")
        c1, c2 = st.columns(2)
        current_w = c1.number_input("Current Weight (kg)",
                                    min_value=0.0, step=0.1,
                                    value=float(user.current_weight or 0))
        goal_w    = c2.number_input("Goal Weight (kg)",
                                    min_value=0.0, step=0.1,
                                    value=float(user.goal_weight or 0))

        st.markdown("**Calorie Target**")
        cal_target = st.number_input("Daily Calories (kcal)",
                                     min_value=0, step=50,
                                     value=int(user.daily_calorie_target or 2000))

        st.markdown("**Macro Targets (grams/day)**")
        st.caption("Tip: Protein ≈ 0.8–1.2× your weight in kg. Fat ≈ 20–35% of calories ÷ 9. Carbs fill the rest.")
        m1, m2, m3 = st.columns(3)
        prot = m1.number_input("Protein (g)", min_value=0.0, step=5.0,
                               value=float(user.protein_target or 0))
        carb = m2.number_input("Carbs (g)",   min_value=0.0, step=5.0,
                               value=float(user.carbs_target or 0))
        fat  = m3.number_input("Fat (g)",     min_value=0.0, step=5.0,
                               value=float(user.fat_target or 0))

        macro_kcal = round(prot * 4 + carb * 4 + fat * 9)
        if macro_kcal > 0:
            st.caption(f"Macro total: ~{macro_kcal} kcal/day")

        if st.form_submit_button("💾 Save Profile", type="primary"):
            updates = {
                "current_weight":       current_w if current_w > 0 else None,
                "goal_weight":          goal_w    if goal_w    > 0 else None,
                "daily_calorie_target": cal_target if cal_target > 0 else None,
                "protein_target":       prot if prot > 0 else None,
                "carbs_target":         carb if carb > 0 else None,
                "fat_target":           fat  if fat  > 0 else None,
            }
            db.update_user_profile(tid, updates)
            st.success("✅ Profile saved!")
            st.rerun()

    # Show current state
    if user.current_weight and user.goal_weight:
        diff = round(user.current_weight - user.goal_weight, 1)
        if diff > 0:
            st.info(f"📉 {diff} kg to your goal weight")
        else:
            st.success("🎉 You've reached your goal weight!")


def _food_entry_form(tid):
    st.subheader("Log a Meal")
    with st.form("food_form", clear_on_submit=True):
        desc = st.text_input("Food *", placeholder="e.g. Grilled chicken with rice")
        c1, c2 = st.columns(2)
        calories = c1.number_input("Calories *", min_value=0, step=10)
        protein  = c1.number_input("Protein (g)", min_value=0.0, step=0.5)
        carbs    = c2.number_input("Carbs (g)", min_value=0.0, step=0.5)
        fat      = c2.number_input("Fat (g)", min_value=0.0, step=0.5)
        if st.form_submit_button("➕ Log Food"):
            if not desc or calories == 0:
                st.error("Description and calories are required.")
            else:
                db.insert_food_log(tid, desc, calories, protein, carbs, fat)
                st.success(f"✅ Logged: {desc} — {calories} kcal")
                st.rerun()


def _food_history(tid, start, end):
    st.subheader("Food Log History")
    rows = db.get_food_logs_by_date_range(tid, start, end)
    if not rows:
        st.info("No food logs in this range.")
        return
    for row in rows:
        ts = datetime.fromisoformat(row["created_at"]).strftime("%b %d · %I:%M %p")
        with st.expander(f"🍽️ **{row['food_description']}** — {row['calories']} kcal  ·  {ts}"):
            c1, c2, c3 = st.columns(3)
            c1.metric("Protein", f"{row['protein']}g")
            c2.metric("Carbs",   f"{row['carbs']}g")
            c3.metric("Fat",     f"{row['fat']}g")
            st.markdown("---")
            _delete_button("Delete", "food", row["id"], tid, db.delete_food_log)


def _workout_entry_form(tid):
    st.subheader("Log a Workout")
    with st.form("workout_form", clear_on_submit=True):
        activity = st.selectbox("Activity *",
            ["Running", "Cycling", "Swimming", "Strength Training",
             "Yoga", "Walking", "HIIT", "Other"])
        custom = ""
        if activity == "Other":
            custom = st.text_input("Specify activity")
        c1, c2  = st.columns(2)
        duration = c1.number_input("Duration (mins) *", min_value=1, value=30)
        distance = c2.number_input("Distance (km)", min_value=0.0, step=0.1)
        notes_txt = st.text_area("Notes", placeholder="How did it go?")
        if st.form_submit_button("➕ Log Workout"):
            act = custom.strip() if activity == "Other" else activity
            if not act:
                st.error("Please specify an activity.")
            else:
                db.insert_workout(tid, act, duration,
                                  distance if distance > 0 else None, notes_txt or None)
                st.success(f"✅ Logged: {act} — {duration} mins")
                st.rerun()


def _workout_history(tid, start, end):
    st.subheader("Workout History")
    rows = db.get_workouts_by_date_range(tid, start, end)
    if not rows:
        st.info("No workouts in this range.")
        return
    for row in rows:
        ts       = datetime.fromisoformat(row["created_at"]).strftime("%b %d · %I:%M %p")
        dist_str = f" · {row['distance_km']} km" if row.get("distance_km") else ""
        with st.expander(f"💪 **{row['activity_type']}** — {row['duration_mins']} mins{dist_str}  ·  {ts}"):
            if row.get("notes"):
                st.write(row["notes"])
            st.markdown("---")
            _delete_button("Delete", "workout", row["id"], tid, db.delete_workout)


def _note_entry_form(tid):
    st.subheader("Create a Note")
    with st.form("note_form", clear_on_submit=True):
        content  = st.text_area("Note *", height=120, placeholder="Brain dump, mood, idea…")
        summary  = st.text_input("Summary *", placeholder="One-sentence title")
        tags_raw = st.text_input("Tags", placeholder="mood, energy, work, stress…")
        if st.form_submit_button("➕ Save Note"):
            if not content or not summary:
                st.error("Content and summary are required.")
            else:
                tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []
                db.insert_note(tid, content, summary, tags)
                st.success("✅ Note saved!")
                st.rerun()


def _note_history(tid, start, end):
    st.subheader("Note History")
    rows = db.get_notes_by_date_range(tid, start, end)
    if not rows:
        st.info("No notes in this range.")
        return
    for row in rows:
        ts   = datetime.fromisoformat(row["created_at"]).strftime("%b %d · %I:%M %p")
        tags = row.get("tags") or []
        with st.expander(f"📌 **{row['summary']}**  ·  {ts}"):
            st.write(row["content"])
            if tags:
                st.markdown(" ".join(
                    f'<span style="background:#e1e8ed;padding:2px 8px;border-radius:12px;'
                    f'margin-right:4px;font-size:12px">{t}</span>' for t in tags
                ), unsafe_allow_html=True)
            st.markdown("---")
            _delete_button("Delete", "note", row["id"], tid, db.delete_note)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    try:
        config.validate_config()
    except ValueError as exc:
        st.error(f"⚠️ Configuration error: {exc}")
        st.stop()

    tid, start, end = render_sidebar()

    tab_dash, tab_meals, tab_insights, tab_journal, tab_entry = st.tabs([
        "📊 Dashboard", "🍽️ Meals", "🧠 Insights", "📝 Journal", "✏️ Data Entry"
    ])

    with tab_dash:
        render_dashboard(tid, start, end)
    with tab_meals:
        render_meals(tid, start, end)
    with tab_insights:
        render_insights(tid)
    with tab_journal:
        render_journal(tid, start, end)
    with tab_entry:
        render_data_entry(tid, start, end)


if __name__ == "__main__":
    main()