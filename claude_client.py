"""
Claude API client for message classification and data extraction
"""
import json
from anthropic import Anthropic
import config
from models import QuestionData, NoteData, FoodData, WorkoutData, ClassifiedMessage
from prompts import SYSTEM_PROMPT, get_classification_prompt


class ClaudeClient:
    """Handles interactions with Claude API"""

    def __init__(self):
        self.client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self.model = "claude-sonnet-4-5-20250929"

    def classify_message(self, user_message: str) -> ClassifiedMessage:
        """
        Classify a user message. Returns one of:
          QuestionData  — answer directly, do NOT save to DB
          NoteData      — save to notes table
          FoodData      — save to food_logs table
          WorkoutData   — save to workouts table
        """
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": get_classification_prompt(user_message)}],
            )

            raw = response.content[0].text.strip()

            # Strip accidental markdown fences
            if raw.startswith("```"):
                raw = raw.replace("```json", "").replace("```", "").strip()

            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Claude returned invalid JSON: {raw[:300]}") from exc

            msg_type = data.get("type")
            if msg_type == "question":
                return QuestionData(**data)
            elif msg_type == "note":
                return NoteData(**data)
            elif msg_type == "food":
                return FoodData(**data)
            elif msg_type == "workout":
                return WorkoutData(**data)
            else:
                raise ValueError(f"Unknown type from Claude: {msg_type!r}")

        except Exception as exc:
            if config.DEBUG:
                print(f"ClaudeClient error: {exc}")
            raise

    def generate_summary_text(self, summary_data: dict) -> str:
        from prompts import SUMMARY_PROMPT_TEMPLATE
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