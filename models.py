"""
Pydantic models for data validation and type safety
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Literal, Union
from datetime import datetime


class QuestionData(BaseModel):
    """Conversational question — answered directly, NOT saved to DB"""
    type: Literal["question"] = "question"
    confidence: float = Field(ge=0.0, le=1.0)
    answer: str = Field(min_length=1)


class NoteData(BaseModel):
    """Note / brain dump entry"""
    type: Literal["note"] = "note"
    confidence: float = Field(ge=0.0, le=1.0)
    content: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    tags: List[str] = Field(default_factory=list)


class FoodData(BaseModel):
    """Food log entry"""
    type: Literal["food"] = "food"
    confidence: float = Field(ge=0.0, le=1.0)
    food_description: str = Field(min_length=1)
    calories: int = Field(ge=0)
    protein: float = Field(ge=0.0)
    carbs: float = Field(ge=0.0)
    fat: float = Field(ge=0.0)

    @field_validator("protein", "carbs", "fat")
    @classmethod
    def round_values(cls, v):
        return round(float(v), 1)


class WorkoutData(BaseModel):
    """Workout entry"""
    type: Literal["workout"] = "workout"
    confidence: float = Field(ge=0.0, le=1.0)
    activity_type: str = Field(min_length=1)
    duration_mins: int = Field(ge=1)
    distance_km: Optional[float] = Field(None, ge=0.0)
    notes: Optional[str] = None


# Union of all Claude response types
ClassifiedMessage = Union[QuestionData, NoteData, FoodData, WorkoutData]


class DailySummary(BaseModel):
    """Aggregated daily stats"""
    date: str
    total_calories: int = 0
    total_protein: float = 0.0
    total_carbs: float = 0.0
    total_fat: float = 0.0
    calories_target: Optional[int] = None
    calories_remaining: Optional[int] = None
    food_entries: int = 0
    workout_count: int = 0
    workout_minutes: int = 0
    notes_count: int = 0


class UserProfile(BaseModel):
    """Full user profile including macro targets"""
    telegram_id: int
    current_weight: Optional[float] = None
    goal_weight: Optional[float] = None
    daily_calorie_target: Optional[int] = None
    # Macro targets in grams
    protein_target: Optional[float] = None
    carbs_target: Optional[float] = None
    fat_target: Optional[float] = None

    def has_macro_targets(self) -> bool:
        return all([self.protein_target, self.carbs_target, self.fat_target])

    def macro_summary(self) -> str:
        """One-line display of macro targets."""
        if not self.has_macro_targets():
            return "No macro targets set — use /setmacros"
        return (f"P: {self.protein_target}g | "
                f"C: {self.carbs_target}g | "
                f"F: {self.fat_target}g")