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
    """Return ISO timestamp for the very start of a date (00:00:00).

    Supabase stores TIMESTAMPTZ values. Comparing with a bare date string
    like '2025-02-17' only matches midnight exactly. We must always pass
    full datetime boundaries so the gte/lte filters cover the whole day.
    """
    return datetime.combine(d, time.min).isoformat()


def _end_of_day(d: date) -> str:
    """Return ISO timestamp for the very end of a date (23:59:59.999999)."""
    return datetime.combine(d, time.max).isoformat()


class Database:
    """Handles all database operations with Supabase"""

    def __init__(self):
        """Initialize Supabase client"""
        self.client: Client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)

    # ==================== USER OPERATIONS ====================

    def get_or_create_user(self, telegram_id: int) -> Dict[str, Any]:
        """Get user by telegram_id or create if doesn't exist"""
        response = (
            self.client.table("users")
            .select("*")
            .eq("telegram_id", telegram_id)
            .execute()
        )

        if response.data:
            return response.data[0]

        new_user = {
            "telegram_id": telegram_id,
            "daily_calorie_target": 2000,
        }
        response = self.client.table("users").insert(new_user).execute()
        return response.data[0]

    def update_user_profile(self, telegram_id: int, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update user profile fields"""
        response = (
            self.client.table("users")
            .update(updates)
            .eq("telegram_id", telegram_id)
            .execute()
        )
        return response.data[0] if response.data else None

    def get_user_profile(self, telegram_id: int) -> Optional[UserProfile]:
        """Get user profile as Pydantic model"""
        user = self.get_or_create_user(telegram_id)
        if user:
            return UserProfile(**user)
        return None

    # ==================== NOTE OPERATIONS ====================

    def insert_note(self, telegram_id: int, content: str, summary: str, tags: List[str]) -> Dict[str, Any]:
        """Insert a new note"""
        user = self.get_or_create_user(telegram_id)
        note = {
            "user_id": user["id"],
            "content": content,
            "summary": summary,
            "tags": tags,
        }
        response = self.client.table("notes").insert(note).execute()
        return response.data[0]

    def get_recent_notes(self, telegram_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get the most recent notes for a user, regardless of date"""
        user = self.get_or_create_user(telegram_id)
        response = (
            self.client.table("notes")
            .select("*")
            .eq("user_id", user["id"])
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data

    def search_notes(self, telegram_id: int, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search notes by keyword in content or summary (case-insensitive).
        Returns deduplicated results sorted by newest first.
        """
        user = self.get_or_create_user(telegram_id)

        content_matches = (
            self.client.table("notes")
            .select("*")
            .eq("user_id", user["id"])
            .ilike("content", f"%{query}%")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

        summary_matches = (
            self.client.table("notes")
            .select("*")
            .eq("user_id", user["id"])
            .ilike("summary", f"%{query}%")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

        # Merge and deduplicate by id
        seen = set()
        results = []
        for note in (content_matches.data or []) + (summary_matches.data or []):
            if note["id"] not in seen:
                seen.add(note["id"])
                results.append(note)

        results.sort(key=lambda n: n["created_at"], reverse=True)
        return results[:limit]

    def get_notes_by_date_range(self, telegram_id: int, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """Get notes within a date range (inclusive of full end day)"""
        user = self.get_or_create_user(telegram_id)
        response = (
            self.client.table("notes")
            .select("*")
            .eq("user_id", user["id"])
            .gte("created_at", _start_of_day(start_date))
            .lte("created_at", _end_of_day(end_date))
            .order("created_at", desc=True)
            .execute()
        )
        return response.data

    # ==================== FOOD LOG OPERATIONS ====================

    def insert_food_log(self, telegram_id: int, food_description: str,
                        calories: int, protein: float, carbs: float, fat: float) -> Dict[str, Any]:
        """Insert a food log entry"""
        user = self.get_or_create_user(telegram_id)
        food_log = {
            "user_id": user["id"],
            "food_description": food_description,
            "calories": calories,
            "protein": protein,
            "carbs": carbs,
            "fat": fat,
        }
        response = self.client.table("food_logs").insert(food_log).execute()
        return response.data[0]

    def get_daily_nutrition(self, telegram_id: int, target_date: Optional[date] = None) -> Dict[str, Any]:
        """Get total nutrition for a specific day"""
        if target_date is None:
            target_date = datetime.now().date()

        user = self.get_or_create_user(telegram_id)
        response = (
            self.client.table("food_logs")
            .select("*")
            .eq("user_id", user["id"])
            .gte("created_at", _start_of_day(target_date))
            .lte("created_at", _end_of_day(target_date))
            .execute()
        )

        logs = response.data
        return {
            "total_calories": sum(log["calories"] or 0 for log in logs),
            "total_protein": sum(float(log["protein"] or 0) for log in logs),
            "total_carbs": sum(float(log["carbs"] or 0) for log in logs),
            "total_fat": sum(float(log["fat"] or 0) for log in logs),
            "entry_count": len(logs),
            "entries": logs,
        }

    def get_food_logs_by_date_range(self, telegram_id: int, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """Get food logs within a date range (inclusive of full end day)"""
        user = self.get_or_create_user(telegram_id)
        response = (
            self.client.table("food_logs")
            .select("*")
            .eq("user_id", user["id"])
            .gte("created_at", _start_of_day(start_date))
            .lte("created_at", _end_of_day(end_date))
            .order("created_at", desc=True)
            .execute()
        )
        return response.data

    # ==================== WORKOUT OPERATIONS ====================

    def insert_workout(self, telegram_id: int, activity_type: str, duration_mins: int,
                       distance_km: Optional[float] = None, notes: Optional[str] = None) -> Dict[str, Any]:
        """Insert a workout entry"""
        user = self.get_or_create_user(telegram_id)
        workout = {
            "user_id": user["id"],
            "activity_type": activity_type,
            "duration_mins": duration_mins,
            "distance_km": distance_km,
            "notes": notes,
        }
        response = self.client.table("workouts").insert(workout).execute()
        return response.data[0]

    def get_daily_workouts(self, telegram_id: int, target_date: Optional[date] = None) -> List[Dict[str, Any]]:
        """Get all workouts for a specific day"""
        if target_date is None:
            target_date = datetime.now().date()

        user = self.get_or_create_user(telegram_id)
        response = (
            self.client.table("workouts")
            .select("*")
            .eq("user_id", user["id"])
            .gte("created_at", _start_of_day(target_date))
            .lte("created_at", _end_of_day(target_date))
            .order("created_at", desc=True)
            .execute()
        )
        return response.data

    def get_workouts_by_date_range(self, telegram_id: int, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """Get workouts within a date range (inclusive of full end day)"""
        user = self.get_or_create_user(telegram_id)
        response = (
            self.client.table("workouts")
            .select("*")
            .eq("user_id", user["id"])
            .gte("created_at", _start_of_day(start_date))
            .lte("created_at", _end_of_day(end_date))
            .order("created_at", desc=True)
            .execute()
        )
        return response.data

    # ==================== SUMMARY & ANALYTICS ====================

    def get_daily_summary(self, telegram_id: int, target_date: Optional[date] = None) -> DailySummary:
        """Get complete daily summary"""
        if target_date is None:
            target_date = datetime.now().date()

        user = self.get_or_create_user(telegram_id)
        nutrition = self.get_daily_nutrition(telegram_id, target_date)
        workouts = self.get_daily_workouts(telegram_id, target_date)
        total_workout_mins = sum(w["duration_mins"] or 0 for w in workouts)

        notes_response = (
            self.client.table("notes")
            .select("id", count="exact")
            .eq("user_id", user["id"])
            .gte("created_at", _start_of_day(target_date))
            .lte("created_at", _end_of_day(target_date))
            .execute()
        )
        notes_count = notes_response.count or 0

        calories_target = user.get("daily_calorie_target")
        calories_remaining = None
        if calories_target:
            calories_remaining = calories_target - nutrition["total_calories"]

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
            workout_minutes=total_workout_mins,
            notes_count=notes_count,
        )

    # ==================== DELETE OPERATIONS ====================

    def delete_note(self, telegram_id: int, note_id: str) -> bool:
        """Delete a note — verifies ownership before deleting"""
        user = self.get_or_create_user(telegram_id)
        response = (
            self.client.table("notes")
            .delete()
            .eq("id", note_id)
            .eq("user_id", user["id"])   # ownership guard
            .execute()
        )
        return len(response.data) > 0

    def delete_food_log(self, telegram_id: int, food_id: str) -> bool:
        """Delete a food log entry — verifies ownership before deleting"""
        user = self.get_or_create_user(telegram_id)
        response = (
            self.client.table("food_logs")
            .delete()
            .eq("id", food_id)
            .eq("user_id", user["id"])
            .execute()
        )
        return len(response.data) > 0

    def delete_workout(self, telegram_id: int, workout_id: str) -> bool:
        """Delete a workout entry — verifies ownership before deleting"""
        user = self.get_or_create_user(telegram_id)
        response = (
            self.client.table("workouts")
            .delete()
            .eq("id", workout_id)
            .eq("user_id", user["id"])
            .execute()
        )
        return len(response.data) > 0