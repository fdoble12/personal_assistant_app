"""
Database operations using Supabase client
All CRUD operations for the Personal Life OS
"""
from supabase import create_client, Client
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, date, time
import config
from models import UserProfile, DailySummary


def _start_of_day(d: date) -> str:
    return datetime.combine(d, time.min).isoformat()


def _end_of_day(d: date) -> str:
    return datetime.combine(d, time.max).isoformat()


class Database:
    def __init__(self):
        self.client: Client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)

    # ── USER ────────────────────────────────────────────────────────────────

    def get_or_create_user(self, telegram_id: int) -> Dict[str, Any]:
        response = (
            self.client.table("users")
            .select("*")
            .eq("telegram_id", telegram_id)
            .execute()
        )
        if response.data:
            return response.data[0]
        new_user = {"telegram_id": telegram_id, "daily_calorie_target": 2000}
        response = self.client.table("users").insert(new_user).execute()
        return response.data[0]

    def update_user_profile(self, telegram_id: int, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        response = (
            self.client.table("users")
            .update(updates)
            .eq("telegram_id", telegram_id)
            .execute()
        )
        return response.data[0] if response.data else None

    def get_user_profile(self, telegram_id: int) -> Optional[UserProfile]:
        user = self.get_or_create_user(telegram_id)
        return UserProfile(**user) if user else None

    # ── NOTES ───────────────────────────────────────────────────────────────

    def insert_note(self, telegram_id: int, content: str, summary: str, tags: List[str]) -> Dict[str, Any]:
        user = self.get_or_create_user(telegram_id)
        response = self.client.table("notes").insert({
            "user_id": user["id"], "content": content,
            "summary": summary, "tags": tags,
        }).execute()
        return response.data[0]

    def get_recent_notes(self, telegram_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        user = self.get_or_create_user(telegram_id)
        return (
            self.client.table("notes")
            .select("*").eq("user_id", user["id"])
            .order("created_at", desc=True).limit(limit)
            .execute()
        ).data

    def search_notes(self, telegram_id: int, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        user = self.get_or_create_user(telegram_id)
        content_hits = (
            self.client.table("notes").select("*")
            .eq("user_id", user["id"]).ilike("content", f"%{query}%")
            .order("created_at", desc=True).limit(limit).execute()
        ).data
        summary_hits = (
            self.client.table("notes").select("*")
            .eq("user_id", user["id"]).ilike("summary", f"%{query}%")
            .order("created_at", desc=True).limit(limit).execute()
        ).data
        seen, results = set(), []
        for note in content_hits + summary_hits:
            if note["id"] not in seen:
                seen.add(note["id"])
                results.append(note)
        results.sort(key=lambda n: n["created_at"], reverse=True)
        return results[:limit]

    def get_notes_by_date_range(self, telegram_id: int, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        user = self.get_or_create_user(telegram_id)
        return (
            self.client.table("notes").select("*")
            .eq("user_id", user["id"])
            .gte("created_at", _start_of_day(start_date))
            .lte("created_at", _end_of_day(end_date))
            .order("created_at", desc=True).execute()
        ).data

    # ── FOOD ────────────────────────────────────────────────────────────────

    def insert_food_log(self, telegram_id: int, food_description: str,
                        calories: int, protein: float, carbs: float, fat: float) -> Dict[str, Any]:
        user = self.get_or_create_user(telegram_id)
        response = self.client.table("food_logs").insert({
            "user_id": user["id"], "food_description": food_description,
            "calories": calories, "protein": protein, "carbs": carbs, "fat": fat,
        }).execute()
        return response.data[0]

    def get_daily_nutrition(self, telegram_id: int, target_date: Optional[date] = None) -> Dict[str, Any]:
        if target_date is None:
            target_date = datetime.now().date()
        user = self.get_or_create_user(telegram_id)
        logs = (
            self.client.table("food_logs").select("*")
            .eq("user_id", user["id"])
            .gte("created_at", _start_of_day(target_date))
            .lte("created_at", _end_of_day(target_date))
            .execute()
        ).data
        return {
            "total_calories": sum(r["calories"] or 0 for r in logs),
            "total_protein":  sum(float(r["protein"] or 0) for r in logs),
            "total_carbs":    sum(float(r["carbs"] or 0) for r in logs),
            "total_fat":      sum(float(r["fat"] or 0) for r in logs),
            "entry_count":    len(logs),
            "entries":        logs,
        }

    def get_food_logs_by_date_range(self, telegram_id: int, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        user = self.get_or_create_user(telegram_id)
        return (
            self.client.table("food_logs").select("*")
            .eq("user_id", user["id"])
            .gte("created_at", _start_of_day(start_date))
            .lte("created_at", _end_of_day(end_date))
            .order("created_at", desc=True).execute()
        ).data

    def get_recent_food_logs(self, telegram_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        """Get the most recent food entries regardless of date — for /meals command."""
        user = self.get_or_create_user(telegram_id)
        return (
            self.client.table("food_logs").select("*")
            .eq("user_id", user["id"])
            .order("created_at", desc=True).limit(limit)
            .execute()
        ).data

    # ── WORKOUTS ────────────────────────────────────────────────────────────

    def insert_workout(self, telegram_id: int, activity_type: str, duration_mins: int,
                       distance_km: Optional[float] = None, notes: Optional[str] = None) -> Dict[str, Any]:
        user = self.get_or_create_user(telegram_id)
        response = self.client.table("workouts").insert({
            "user_id": user["id"], "activity_type": activity_type,
            "duration_mins": duration_mins, "distance_km": distance_km, "notes": notes,
        }).execute()
        return response.data[0]

    def get_daily_workouts(self, telegram_id: int, target_date: Optional[date] = None) -> List[Dict[str, Any]]:
        if target_date is None:
            target_date = datetime.now().date()
        user = self.get_or_create_user(telegram_id)
        return (
            self.client.table("workouts").select("*")
            .eq("user_id", user["id"])
            .gte("created_at", _start_of_day(target_date))
            .lte("created_at", _end_of_day(target_date))
            .order("created_at", desc=True).execute()
        ).data

    def get_workouts_by_date_range(self, telegram_id: int, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        user = self.get_or_create_user(telegram_id)
        return (
            self.client.table("workouts").select("*")
            .eq("user_id", user["id"])
            .gte("created_at", _start_of_day(start_date))
            .lte("created_at", _end_of_day(end_date))
            .order("created_at", desc=True).execute()
        ).data

    # ── SUMMARY ─────────────────────────────────────────────────────────────

    def get_daily_summary(self, telegram_id: int, target_date: Optional[date] = None) -> DailySummary:
        if target_date is None:
            target_date = datetime.now().date()
        user = self.get_or_create_user(telegram_id)
        nutrition = self.get_daily_nutrition(telegram_id, target_date)
        workouts  = self.get_daily_workouts(telegram_id, target_date)

        notes_resp = (
            self.client.table("notes").select("id", count="exact")
            .eq("user_id", user["id"])
            .gte("created_at", _start_of_day(target_date))
            .lte("created_at", _end_of_day(target_date))
            .execute()
        )
        calories_target   = user.get("daily_calorie_target")
        calories_remaining = (calories_target - nutrition["total_calories"]) if calories_target else None

        return DailySummary(
            date=target_date.isoformat(),
            total_calories=nutrition["total_calories"],
            total_protein=round(nutrition["total_protein"], 1),
            total_carbs=round(nutrition["total_carbs"], 1),
            total_fat=round(nutrition["total_fat"], 1),
            calories_target=calories_target,
            calories_remaining=calories_remaining,
            food_entries=nutrition["entry_count"],
            workout_count=len(workouts),
            workout_minutes=sum(w["duration_mins"] or 0 for w in workouts),
            notes_count=notes_resp.count or 0,
        )

    # ── WELLNESS CONTEXT (for insights) ─────────────────────────────────────

    def get_wellness_context(self, telegram_id: int, days: int = 7) -> Dict[str, Any]:
        """
        Pull everything logged in the last N days and return a structured
        context dict for Claude to generate holistic insights from.
        Covers nutrition, workouts, and notes (which capture mood/energy/productivity).
        """
        today = datetime.now().date()
        start = today - timedelta(days=days - 1)

        user       = self.get_user_profile(telegram_id)
        food_logs  = self.get_food_logs_by_date_range(telegram_id, start, today)
        workouts   = self.get_workouts_by_date_range(telegram_id, start, today)
        notes      = self.get_notes_by_date_range(telegram_id, start, today)

        # Aggregate daily nutrition
        daily_nutrition: Dict[str, Dict] = {}
        for log in food_logs:
            d = log["created_at"][:10]
            if d not in daily_nutrition:
                daily_nutrition[d] = {"calories": 0, "protein": 0.0, "carbs": 0.0, "fat": 0.0, "meals": []}
            daily_nutrition[d]["calories"] += log["calories"] or 0
            daily_nutrition[d]["protein"]  += float(log["protein"] or 0)
            daily_nutrition[d]["carbs"]    += float(log["carbs"] or 0)
            daily_nutrition[d]["fat"]      += float(log["fat"] or 0)
            daily_nutrition[d]["meals"].append(log["food_description"])

        return {
            "period_days":    days,
            "start_date":     start.isoformat(),
            "end_date":       today.isoformat(),
            "user_profile":   {
                "current_weight":       user.current_weight if user else None,
                "goal_weight":          user.goal_weight if user else None,
                "daily_calorie_target": user.daily_calorie_target if user else None,
                "protein_target":       user.protein_target if user else None,
                "carbs_target":         user.carbs_target if user else None,
                "fat_target":           user.fat_target if user else None,
            },
            "daily_nutrition": daily_nutrition,
            "workouts": [
                {
                    "date":          w["created_at"][:10],
                    "activity":      w["activity_type"],
                    "duration_mins": w["duration_mins"],
                    "distance_km":   w.get("distance_km"),
                    "notes":         w.get("notes"),
                }
                for w in workouts
            ],
            "notes": [
                {
                    "date":    n["created_at"][:10],
                    "summary": n["summary"],
                    "content": n["content"],
                    "tags":    n.get("tags") or [],
                }
                for n in notes
            ],
            "totals": {
                "food_entries":    len(food_logs),
                "workouts":        len(workouts),
                "notes":           len(notes),
                "avg_daily_kcal":  round(
                    sum(d["calories"] for d in daily_nutrition.values()) / max(len(daily_nutrition), 1), 0
                ),
            },
        }

    # ── DELETE ──────────────────────────────────────────────────────────────

    def delete_note(self, telegram_id: int, note_id: str) -> bool:
        user = self.get_or_create_user(telegram_id)
        resp = (
            self.client.table("notes").delete()
            .eq("id", note_id).eq("user_id", user["id"]).execute()
        )
        return len(resp.data) > 0

    def delete_food_log(self, telegram_id: int, food_id: str) -> bool:
        user = self.get_or_create_user(telegram_id)
        resp = (
            self.client.table("food_logs").delete()
            .eq("id", food_id).eq("user_id", user["id"]).execute()
        )
        return len(resp.data) > 0

    def delete_workout(self, telegram_id: int, workout_id: str) -> bool:
        user = self.get_or_create_user(telegram_id)
        resp = (
            self.client.table("workouts").delete()
            .eq("id", workout_id).eq("user_id", user["id"]).execute()
        )
        return len(resp.data) > 0