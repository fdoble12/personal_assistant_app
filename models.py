"""
Pydantic models for data validation and type safety
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Literal, Union
from datetime import datetime


class QuestionData(BaseModel):
    """Model for conversational questions — NOT saved to the database"""
    type: Literal["question"] = "question"
    confidence: float = Field(ge=0.0, le=1.0)
    answer: str = Field(min_length=1, description="Claude's direct answer to the user")


class NoteData(BaseModel):
    """Model for note/brain dump entries"""
    type: Literal["note"] = "note"
    confidence: float = Field(ge=0.0, le=1.0)
    content: str = Field(min_length=1, description="Original user message")
    summary: str = Field(min_length=1, description="One-sentence summary")
    tags: List[str] = Field(default_factory=list, description="Extracted tags/topics")


class FoodData(BaseModel):
    """Model for food log entries"""
    type: Literal["food"] = "food"
    confidence: float = Field(ge=0.0, le=1.0)
    food_description: str = Field(min_length=1, description="Description of food")
    calories: int = Field(ge=0, description="Estimated calories")
    protein: float = Field(ge=0.0, description="Protein in grams")
    carbs: float = Field(ge=0.0, description="Carbohydrates in grams")
    fat: float = Field(ge=0.0, description="Fat in grams")

    @field_validator("calories", "protein", "carbs", "fat")
    @classmethod
    def round_values(cls, v):
        if isinstance(v, float):
            return round(v, 1)
        return v


class WorkoutData(BaseModel):
    """Model for workout entries"""
    type: Literal["workout"] = "workout"
    confidence: float = Field(ge=0.0, le=1.0)
    activity_type: str = Field(min_length=1, description="Type of exercise")
    duration_mins: int = Field(ge=1, description="Duration in minutes")
    distance_km: Optional[float] = Field(None, ge=0.0, description="Distance if applicable")
    notes: Optional[str] = Field(None, description="Additional notes about workout")


# Union type for all possible Claude responses
ClassifiedMessage = Union[QuestionData, NoteData, FoodData, WorkoutData]


class DailySummary(BaseModel):
    """Model for daily summary report"""
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
    """Model for user profile data"""
    telegram_id: int
    goal_weight: Optional[float] = None
    current_weight: Optional[float] = None
    daily_calorie_target: Optional[int] = None