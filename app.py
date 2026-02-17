"""
Streamlit Dashboard for Personal Life OS
Interactive analytics and data entry interface — with delete support.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, date

import config
from database import Database
from models import UserProfile

st.set_page_config(
    page_title="Personal Life OS",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── Database (cached so it's not re-created on every interaction) ───────────
@st.cache_resource
def get_db() -> Database:
    return Database()


db = get_db()


# ── Sidebar ─────────────────────────────────────────────────────────────────

def render_sidebar():
    st.sidebar.title("🧠 Personal Life OS")
    st.sidebar.markdown("---")

    telegram_id = st.sidebar.number_input(
        "Your Telegram ID",
        min_value=1,
        value=123456789,
        help="Find it by messaging @userinfobot on Telegram",
    )

    st.sidebar.subheader("Date Range")
    preset = st.sidebar.selectbox("Preset", ["Today", "Last 7 Days", "Last 30 Days", "Custom"])

    today = datetime.now().date()
    if preset == "Today":
        start, end = today, today
    elif preset == "Last 7 Days":
        start, end = today - timedelta(days=7), today
    elif preset == "Last 30 Days":
        start, end = today - timedelta(days=30), today
    else:
        c1, c2 = st.sidebar.columns(2)
        start = c1.date_input("From", today - timedelta(days=30))
        end = c2.date_input("To", today)

    return int(telegram_id), start, end


# ── Shared delete confirmation helper ───────────────────────────────────────

def _confirm_delete_key(prefix: str, row_id: str) -> str:
    """Session-state key for a pending delete confirmation."""
    return f"confirm_del_{prefix}_{row_id}"


def _delete_button(label: str, prefix: str, row_id: str,
                   telegram_id: int, delete_fn) -> None:
    """
    Render a 🗑 button. First click asks for confirmation;
    second click performs the delete and reruns.
    """
    confirm_key = _confirm_delete_key(prefix, row_id)

    if st.session_state.get(confirm_key):
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("✅ Confirm delete", key=f"yes_{prefix}_{row_id}"):
                ok = delete_fn(telegram_id, row_id)
                if ok:
                    st.toast("Deleted ✓", icon="🗑️")
                else:
                    st.warning("Could not delete — record not found.")
                del st.session_state[confirm_key]
                st.rerun()
        with col2:
            if st.button("❌ Cancel", key=f"no_{prefix}_{row_id}"):
                del st.session_state[confirm_key]
                st.rerun()
    else:
        if st.button(f"🗑 {label}", key=f"del_{prefix}_{row_id}"):
            st.session_state[confirm_key] = True
            st.rerun()


# ── DASHBOARD TAB ────────────────────────────────────────────────────────────

def render_dashboard(tid: int, start: date, end: date):
    st.header("📊 Dashboard")

    user = db.get_user_profile(tid)
    if not user:
        st.warning("User not found. Check your Telegram ID in the sidebar.")
        return

    _metrics(tid, start, end)
    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        _calorie_chart(tid, start, end, user)
        _macro_pie(tid, start, end)
    with col2:
        _workout_chart(tid, start, end)
        _weight_gauge(user)


def _metrics(tid: int, start: date, end: date):
    food = db.get_food_logs_by_date_range(tid, start, end)
    workouts = db.get_workouts_by_date_range(tid, start, end)
    notes = db.get_notes_by_date_range(tid, start, end)

    days = max(1, (end - start).days + 1)
    total_cal = sum(r["calories"] or 0 for r in food)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Avg Daily Calories", f"{total_cal // days:,} kcal")
    c2.metric("Workouts", len(workouts))
    c3.metric("Workout Time", f"{sum(w['duration_mins'] or 0 for w in workouts)} mins")
    c4.metric("Notes", len(notes))


def _calorie_chart(tid: int, start: date, end: date, user: UserProfile):
    st.subheader("📈 Daily Calorie Intake")
    food = db.get_food_logs_by_date_range(tid, start, end)
    if not food:
        st.info("No food logs in this range.")
        return

    df = pd.DataFrame(food)
    df["date"] = pd.to_datetime(df["created_at"]).dt.date
    daily = df.groupby("date")["calories"].sum().reset_index().sort_values("date")

    fig = go.Figure()
    fig.add_trace(go.Bar(x=daily["date"], y=daily["calories"],
                         name="Calories", marker_color="rgb(99,110,250)"))
    if user.daily_calorie_target:
        fig.add_hline(y=user.daily_calorie_target, line_dash="dash",
                      line_color="red",
                      annotation_text=f"Target: {user.daily_calorie_target} kcal")
    fig.update_layout(xaxis_title="Date", yaxis_title="Calories",
                      hovermode="x unified", height=300)
    st.plotly_chart(fig, use_container_width=True)


def _macro_pie(tid: int, start: date, end: date):
    st.subheader("🥗 Macro Distribution")
    food = db.get_food_logs_by_date_range(tid, start, end)
    if not food:
        st.info("No food logs in this range.")
        return

    df = pd.DataFrame(food)
    fig = go.Figure(data=[go.Pie(
        labels=["Protein", "Carbs", "Fat"],
        values=[df["protein"].sum(), df["carbs"].sum(), df["fat"].sum()],
        hole=0.35,
        marker_colors=["#FF6B6B", "#4ECDC4", "#FFE66D"],
    )])
    fig.update_layout(height=300)
    st.plotly_chart(fig, use_container_width=True)


def _workout_chart(tid: int, start: date, end: date):
    st.subheader("💪 Workout Frequency")
    workouts = db.get_workouts_by_date_range(tid, start, end)
    if not workouts:
        st.info("No workouts in this range.")
        return

    df = pd.DataFrame(workouts)
    counts = df["activity_type"].value_counts().reset_index()
    counts.columns = ["Activity", "Count"]
    fig = px.bar(counts, x="Activity", y="Count",
                 color="Count", color_continuous_scale="Viridis")
    fig.update_layout(height=300, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)


def _weight_gauge(user: UserProfile):
    st.subheader("⚖️ Weight Progress")
    if not (user.current_weight and user.goal_weight):
        st.info("Set current & goal weight via `/setgoal` in the bot.")
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


# ── JOURNAL TAB ──────────────────────────────────────────────────────────────

def render_journal(tid: int, start: date, end: date):
    st.header("📝 Journal")

    notes = db.get_notes_by_date_range(tid, start, end)

    if not notes:
        st.info("No notes in this date range. Start journaling through the Telegram bot!")
        return

    search = st.text_input("🔍 Search notes", placeholder="Search by content, summary or tags…")
    if search:
        q = search.lower()
        notes = [n for n in notes
                 if q in n["content"].lower()
                 or q in n["summary"].lower()
                 or any(q in t.lower() for t in (n.get("tags") or []))]

    st.caption(f"{len(notes)} note(s) shown")

    for note in notes:
        ts = datetime.fromisoformat(note["created_at"]).strftime("%B %d, %Y · %I:%M %p")
        with st.expander(f"📌 {note['summary']}  —  {ts}"):
            st.write(note["content"])

            tags = note.get("tags") or []
            if tags:
                tag_html = " ".join(
                    f'<span style="background:#e1e8ed;padding:2px 8px;'
                    f'border-radius:12px;margin-right:4px;font-size:12px">{t}</span>'
                    for t in tags
                )
                st.markdown(tag_html, unsafe_allow_html=True)

            st.markdown("---")
            _delete_button("Delete note", "note", note["id"], tid, db.delete_note)


# ── DATA ENTRY TAB ────────────────────────────────────────────────────────────

def render_data_entry(tid: int, start: date, end: date):
    st.header("✏️ Data Entry & History")

    tab_food, tab_workout, tab_note = st.tabs(["🍽️ Food", "💪 Workouts", "📝 Notes"])

    with tab_food:
        _food_entry_form(tid)
        st.markdown("---")
        _food_history(tid, start, end)

    with tab_workout:
        _workout_entry_form(tid)
        st.markdown("---")
        _workout_history(tid, start, end)

    with tab_note:
        _note_entry_form(tid)
        st.markdown("---")
        _note_history(tid, start, end)


# ── Food ─────────────────────────────────────────────────────────────────────

def _food_entry_form(tid: int):
    st.subheader("Log a Meal")
    with st.form("food_form", clear_on_submit=True):
        desc = st.text_input("Food Description *", placeholder="e.g. Grilled chicken with rice")
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


def _food_history(tid: int, start: date, end: date):
    st.subheader("Food Log History")
    rows = db.get_food_logs_by_date_range(tid, start, end)
    if not rows:
        st.info("No food logs in this date range.")
        return

    for row in rows:
        ts = datetime.fromisoformat(row["created_at"]).strftime("%b %d · %I:%M %p")
        with st.expander(f"🍽️ **{row['food_description']}** — {row['calories']} kcal  ·  {ts}"):
            c1, c2, c3 = st.columns(3)
            c1.metric("Protein", f"{row['protein']}g")
            c2.metric("Carbs", f"{row['carbs']}g")
            c3.metric("Fat", f"{row['fat']}g")
            st.markdown("---")
            _delete_button("Delete entry", "food", row["id"], tid, db.delete_food_log)


# ── Workouts ──────────────────────────────────────────────────────────────────

def _workout_entry_form(tid: int):
    st.subheader("Log a Workout")
    with st.form("workout_form", clear_on_submit=True):
        activity = st.selectbox("Activity *",
            ["Running", "Cycling", "Swimming", "Strength Training",
             "Yoga", "Walking", "HIIT", "Other"])
        custom = ""
        if activity == "Other":
            custom = st.text_input("Specify activity")

        c1, c2 = st.columns(2)
        duration = c1.number_input("Duration (mins) *", min_value=1, value=30)
        distance = c2.number_input("Distance (km)", min_value=0.0, step=0.1,
                                   help="Leave at 0 if not applicable")
        notes_txt = st.text_area("Notes", placeholder="How did it go?")

        if st.form_submit_button("➕ Log Workout"):
            act = custom.strip() if activity == "Other" else activity
            if not act:
                st.error("Please specify an activity.")
            else:
                db.insert_workout(tid, act, duration,
                                  distance if distance > 0 else None,
                                  notes_txt or None)
                st.success(f"✅ Logged: {act} — {duration} mins")
                st.rerun()


def _workout_history(tid: int, start: date, end: date):
    st.subheader("Workout History")
    rows = db.get_workouts_by_date_range(tid, start, end)
    if not rows:
        st.info("No workouts in this date range.")
        return

    for row in rows:
        ts = datetime.fromisoformat(row["created_at"]).strftime("%b %d · %I:%M %p")
        dist_str = f" · {row['distance_km']} km" if row.get("distance_km") else ""
        with st.expander(f"💪 **{row['activity_type']}** — {row['duration_mins']} mins{dist_str}  ·  {ts}"):
            if row.get("notes"):
                st.write(row["notes"])
            st.markdown("---")
            _delete_button("Delete entry", "workout", row["id"], tid, db.delete_workout)


# ── Notes ─────────────────────────────────────────────────────────────────────

def _note_entry_form(tid: int):
    st.subheader("Create a Note")
    with st.form("note_form", clear_on_submit=True):
        content = st.text_area("Note *", placeholder="Brain dump, idea, reminder…", height=120)
        summary = st.text_input("Summary *", placeholder="One-sentence title")
        tags_raw = st.text_input("Tags", placeholder="comma-separated, e.g. idea, work")

        if st.form_submit_button("➕ Save Note"):
            if not content or not summary:
                st.error("Content and summary are required.")
            else:
                tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []
                db.insert_note(tid, content, summary, tags)
                st.success("✅ Note saved!")
                st.rerun()


def _note_history(tid: int, start: date, end: date):
    st.subheader("Note History")
    rows = db.get_notes_by_date_range(tid, start, end)
    if not rows:
        st.info("No notes in this date range.")
        return

    for row in rows:
        ts = datetime.fromisoformat(row["created_at"]).strftime("%b %d · %I:%M %p")
        with st.expander(f"📌 **{row['summary']}**  ·  {ts}"):
            st.write(row["content"])
            tags = row.get("tags") or []
            if tags:
                tag_html = " ".join(
                    f'<span style="background:#e1e8ed;padding:2px 8px;'
                    f'border-radius:12px;margin-right:4px;font-size:12px">{t}</span>'
                    for t in tags
                )
                st.markdown(tag_html, unsafe_allow_html=True)
            st.markdown("---")
            _delete_button("Delete note", "note2", row["id"], tid, db.delete_note)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    try:
        config.validate_config()
    except ValueError as exc:
        st.error(f"⚠️ Configuration error: {exc}")
        st.info("Create a `.env` file based on `.env.example` and restart.")
        st.stop()

    tid, start, end = render_sidebar()

    tab_dash, tab_journal, tab_entry = st.tabs(["📊 Dashboard", "📝 Journal", "✏️ Data Entry"])

    with tab_dash:
        render_dashboard(tid, start, end)
    with tab_journal:
        render_journal(tid, start, end)
    with tab_entry:
        render_data_entry(tid, start, end)


if __name__ == "__main__":
    main()