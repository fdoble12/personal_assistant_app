"""
Claude API client — classification, recommendations, and insights
"""
import json
from anthropic import Anthropic
import config
from models import QuestionData, NoteData, FoodData, WorkoutData, ClassifiedMessage
from prompts import (
    SYSTEM_PROMPT,
    get_classification_prompt,
    get_recommendation_prompt,
    get_insights_prompt,
    SUMMARY_PROMPT_TEMPLATE,
)


class ClaudeClient:
    def __init__(self):
        self.client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self.model  = "claude-sonnet-4-5-20250929"

    # ── Classification ───────────────────────────────────────────────────────

    def classify_message(self, user_message: str) -> ClassifiedMessage:
        """
        Route a user message to the right type.
        Returns QuestionData (answer directly) or NoteData/FoodData/WorkoutData (save to DB).
        """
        response = self.client.messages.create(
            model=self.model,
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": get_classification_prompt(user_message)}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.replace("```json", "").replace("```", "").strip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Claude returned invalid JSON: {raw[:300]}") from exc

        t = data.get("type")
        if t == "question": return QuestionData(**data)
        if t == "note":     return NoteData(**data)
        if t == "food":     return FoodData(**data)
        if t == "workout":  return WorkoutData(**data)
        raise ValueError(f"Unknown type: {t!r}")

    # ── Meal recommendations ─────────────────────────────────────────────────

    def generate_recommendation(self, context: dict) -> str:
        """
        Given today's food logs + user targets, suggest what to eat next.
        context keys: eaten_today, totals, profile
        """
        prompt = get_recommendation_prompt(context)
        response = self.client.messages.create(
            model=self.model,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()

    # ── Holistic wellness insights ────────────────────────────────────────────

    def generate_insights(self, context: dict) -> str:
        """
        Analyze 7 days of food, workouts, and notes (mood/energy/productivity)
        and return a holistic wellness insight report.
        context comes from db.get_wellness_context()
        """
        prompt = get_insights_prompt(context)
        response = self.client.messages.create(
            model=self.model,
            max_tokens=900,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()

    # ── Daily summary text ───────────────────────────────────────────────────

    def generate_summary_text(self, summary_data: dict) -> str:
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=300,
                messages=[{"role": "user", "content": SUMMARY_PROMPT_TEMPLATE.format(**summary_data)}],
            )
            return response.content[0].text.strip()
        except Exception:
            return (
                f"Summary for {summary_data['date']}: "
                f"{summary_data['total_calories']}/{summary_data['calorie_target']} kcal, "
                f"{summary_data['workout_count']} workout(s)."
            )


_client: ClaudeClient | None = None

def get_claude_client() -> ClaudeClient:
    global _client
    if _client is None:
        _client = ClaudeClient()
    return _client