from __future__ import annotations

import json

from pydantic import BaseModel, Field

from app.agents.tools.rag_tool import get_destination_guide_context
from app.config import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MAX_RETRIES,
    LLM_MODEL,
    LLM_TIMEOUT_SECONDS,
)
from app.models.schemas import DayPlan, TripEditRequest, TripRequest


class PlannerDayDraft(BaseModel):
    """The minimal single-day itinerary draft returned by the LLM."""

    day_index: int = Field(..., ge=1)
    theme: str = Field(..., description="Short theme for the day")
    spot_name: str = Field(..., description="Name of the main attraction for the day")
    spot_description: str = Field(..., description="Short reason for recommending this attraction")
    meal_name: str = Field(..., description="Meal or restaurant suggestion for the day")
    meal_notes: str = Field(..., description="Short dining notes")
    daily_note: str = Field(..., description="A short planning note for the day")


class PlannerDraft(BaseModel):
    """Structured itinerary draft provided for use by trip_service.py."""

    summary: str = Field(..., description="Short overview of the entire trip")
    tips: list[str] = Field(default_factory=list, description="Travel tips")
    days: list[PlannerDayDraft] = Field(default_factory=list)


class DayEditDraft(BaseModel):
    """The single-day edit draft returned by the LLM."""

    theme: str = Field(..., description="Edited theme for the day")
    spot_name: str = Field(..., description="Edited main attraction name")
    spot_description: str = Field(..., description="Edited attraction description")
    meal_name: str = Field(..., description="Edited meal name")
    meal_notes: str = Field(..., description="Edited meal notes")
    daily_note: str = Field(..., description="Edited note for the day")


def _normalize_day_edit_payload(payload: dict) -> dict:
    """Support both single-day edit formats that the model may return."""
    if "spot_name" in payload and "meal_name" in payload and "daily_note" in payload:
        return payload

    normalized = dict(payload)

    spots = payload.get("spots")
    if isinstance(spots, list) and spots:
        first_spot = spots[0] or {}
        normalized.setdefault("spot_name", first_spot.get("name", ""))
        normalized.setdefault("spot_description", first_spot.get("description", ""))

    meals = payload.get("meals")
    if isinstance(meals, list) and meals:
        first_meal = meals[0] or {}
        normalized.setdefault("meal_name", first_meal.get("name", ""))
        normalized.setdefault("meal_notes", first_meal.get("notes", ""))

    notes = payload.get("notes")
    if isinstance(notes, list) and notes:
        normalized.setdefault("daily_note", notes[-1] or "")

    return normalized


def _extract_json_object(raw_text: str) -> str | None:
    """Best-effort extraction of a JSON object string from the model's raw text."""
    text = raw_text.strip()

    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()

    start_index = text.find("{")
    end_index = text.rfind("}")
    if start_index == -1 or end_index == -1 or end_index <= start_index:
        return None

    return text[start_index : end_index + 1]


def collect_trip_context(
    destination: str,
    preferences: list[str] | None = None,
    pace: str | None = None,
    special_notes: str | None = None,
    top_k: int = 5,
) -> tuple[list[str], dict[str, int], dict[str, int], dict[str, int]]:
    """Collect local guide snippets. Returns (contexts, rewrite_usage, rerank_usage, embedding_usage)."""
    return get_destination_guide_context(
        destination=destination,
        preferences=preferences,
        pace=pace,
        special_notes=special_notes,
        top_k=top_k,
    )


def _build_chat_llm():
    """Create a generic ChatOpenAI instance."""
    if not LLM_API_KEY:
        return None

    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        return None

    return ChatOpenAI(
        model=LLM_MODEL,
        temperature=0.3,
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL or None,
        timeout=LLM_TIMEOUT_SECONDS,
        max_retries=LLM_MAX_RETRIES,
    )


def _extract_token_usage(response) -> dict[str, int]:
    """Extract token usage from a LangChain AIMessage."""
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    metadata = getattr(response, "response_metadata", None) or {}
    token_usage = metadata.get("token_usage", {})
    if token_usage:
        usage["prompt_tokens"] = token_usage.get("prompt_tokens", 0)
        usage["completion_tokens"] = token_usage.get("completion_tokens", 0)
    return usage


def generate_planner_draft(
    request: TripRequest,
    rag_contexts: list[str],
    day_count: int,
) -> tuple[PlannerDraft | None, dict[str, int]]:
    """
    Generate a structured itinerary draft using LangChain. Returns (draft, token_usage).

    If the current environment is not yet ready for a model call, return None
    so the service layer can fall back to the rule-based implementation.
    """
    empty_usage = {"prompt_tokens": 0, "completion_tokens": 0}
    llm = _build_chat_llm()
    if llm is None:
        return None, empty_usage

    guide_context = "\n\n".join(rag_contexts) if rag_contexts else "No local guide context available."

    system_prompt = (
        "You are a travel planning assistant."
        "Generate a concise, structured travel draft in English."
        "You must always respond in English, regardless of the language of the local guide context or user notes."
        "You must follow the destination, budget, pace, and local guide context given by the user."
        "You must output only a single JSON object — no Markdown, no explanatory text, no code blocks."
        "The output must strictly conform to the required structured fields."
        "If the user raises explicit requests in the additional notes, such as watching a sunset, not wanting to wake up early, avoiding spicy food, or taking photos, prioritize actually incorporating these requests into a specific day's main attraction or that day's plan, rather than just writing a vague tip."
        "If the user explicitly mentions wanting to watch a sunset, prioritize arranging a location suitable for watching the sunset as the main attraction for a given day, or at least ensure the day's main attraction is strongly related to the sunset plan."
    )

    human_prompt = f"""
Destination: {request.destination}
Start date: {request.start_date.isoformat()}
End date: {request.end_date.isoformat()}
Number of days: {day_count}
Travelers: {request.travelers}
Budget: {request.budget}
Preferences: {', '.join(request.preferences) if request.preferences else 'No particular preference'}
Pace: {request.pace or 'Moderate'}
Dietary preferences: {', '.join(request.dietary_preferences) if request.dietary_preferences else 'None'}
Hotel tier: {request.hotel_level or 'Comfort'}
Additional notes: {request.special_notes or 'None'}

Local guide context:
{guide_context}

Requirements:
1. Output an overall summary.
2. Output a daily draft for {day_count} days.
3. Each day should have only one main attraction, one meal suggestion, and one note for the day.
4. Keep tips concise.
5. day_index must range from 1 to {day_count}.
6. If the additional notes contain explicit requests such as "want to watch the sunset" or "don't want to wake up early", these must be reflected in the days, not just placed in tips.
7. If a sunset viewing is arranged, that day's spot_name should, as much as possible, be a location suitable for watching the sunset, or stay consistent with the sunset arrangement in daily_note — avoid a complete disconnect between the "main attraction" and the "sunset location".
8. Each day's schedule should match a "relaxed" pace — avoid overpacking the day or too-early departures.
9. For meal suggestions, prioritize using specialty dishes/restaurants that already appear in the local guide context.
10. Return only the JSON object — no additional explanation, and do not use ```json code blocks.

Example JSON structure:
{{
  "summary": "Overall summary",
  "tips": ["Tip 1", "Tip 2"],
  "days": [
    {{
      "day_index": 1,
      "theme": "Theme for the day",
      "spot_name": "Main attraction",
      "spot_description": "Reason for recommending the attraction",
      "meal_name": "Meal name",
      "meal_notes": "Meal notes",
      "daily_note": "Note for the day"
    }}
  ]
}}
"""

    print("[trip_planner_agent] Preparing to call the LLM...")
    print(f"[trip_planner_agent] model = {LLM_MODEL}")
    print(f"[trip_planner_agent] base_url = {LLM_BASE_URL or '<DEFAULT>'}")
    print(f"[trip_planner_agent] timeout = {LLM_TIMEOUT_SECONDS}s")
    print(f"[trip_planner_agent] max_retries = {LLM_MAX_RETRIES}")

    try:
        response = llm.invoke(
            [
                ("system", system_prompt),
                ("human", human_prompt),
            ]
        )
    except Exception as exc:
        print(f"[trip_planner_agent] LLM call failed: {type(exc).__name__}: {exc}")
        return None, empty_usage

    token_usage = _extract_token_usage(response)
    print(f"[trip_planner_agent] LLM call completed. tokens: prompt={token_usage['prompt_tokens']}, completion={token_usage['completion_tokens']}")

    raw_text = getattr(response, "content", "")
    if isinstance(raw_text, list):
        raw_text = "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in raw_text
        )

    json_text = _extract_json_object(str(raw_text))
    if json_text is None:
        print("[trip_planner_agent] Failed to extract JSON from the model response.")
        print(f"[trip_planner_agent] Raw response preview: {str(raw_text)[:300]}")
        return None, token_usage

    try:
        result = PlannerDraft.model_validate(json.loads(json_text))
    except Exception as exc:
        print(f"[trip_planner_agent] JSON parsing failed: {type(exc).__name__}: {exc}")
        print(f"[trip_planner_agent] Raw response preview: {str(raw_text)[:300]}")
        return None, token_usage

    if len(result.days) != day_count:
        print(
            "[trip_planner_agent] The number of days in the structured result does not match, "
            f"expected={day_count}, actual={len(result.days)}"
        )
        return None, token_usage

    return result, token_usage


def generate_day_edit_draft(
    request: TripEditRequest,
    target_day: DayPlan,
) -> tuple[DayEditDraft | None, dict[str, int]]:
    """
    Generate a single-day edit draft using the LLM. Returns (draft, token_usage).

    This function is only responsible for producing the edit result for the
    target day; how it is ultimately merged back into the full itinerary is
    handled by the service layer.
    """
    empty_usage = {"prompt_tokens": 0, "completion_tokens": 0}
    llm = _build_chat_llm()
    if llm is None:
        return None, empty_usage

    current_day_payload = {
        "day_index": target_day.day_index,
        "date": target_day.date.isoformat() if target_day.date else None,
        "theme": target_day.theme,
        "spots": [spot.model_dump(mode="json") for spot in target_day.spots],
        "meals": [meal.model_dump(mode="json") for meal in target_day.meals],
        "notes": list(target_day.notes),
    }

    current_itinerary_payload = request.current_itinerary.model_dump(mode="json")

    system_prompt = (
        "You are a travel itinerary editing assistant."
        "Based on the user's edit instruction, rewrite only the core plan for the target day."
        "You must output only a single JSON object — no Markdown, no explanatory text, no code blocks."
        "The edited result should preserve, as much as possible, the overall style, budget structure, and relaxed pace of the original itinerary."
    )

    human_prompt = f"""
Current full itinerary:
{json.dumps(current_itinerary_payload, ensure_ascii=False, indent=2)}

Target day that needs to be edited:
{json.dumps(current_day_payload, ensure_ascii=False, indent=2)}

User edit instruction: {request.user_instruction}
Edit scope: {request.edit_scope or 'Not specified'}
Constraints to preserve as much as possible: {', '.join(request.preserve_constraints) if request.preserve_constraints else 'None'}

Requirements:
1. Output only the edited result for the target day.
2. If the user asks for "more relaxed" or "don't overpack the schedule", reduce the pressure of fixed attractions and make the notes read more naturally.
3. Preserve, as much as possible, the original itinerary's city, style, dining tone, and budget structure.
4. Do not output any extra fields.
5. Return only the JSON object.

Example JSON structure:
{{
  "theme": "Edited theme for the day",
  "spot_name": "Edited main attraction",
  "spot_description": "Edited attraction description",
  "meal_name": "Edited meal name",
  "meal_notes": "Edited meal notes",
  "daily_note": "Edited note for the day"
}}
"""

    print("[trip_planner_agent] Preparing to call the LLM for a single-day edit...")
    print(f"[trip_planner_agent] model = {LLM_MODEL}")
    print(f"[trip_planner_agent] base_url = {LLM_BASE_URL or '<DEFAULT>'}")

    try:
        response = llm.invoke(
            [
                ("system", system_prompt),
                ("human", human_prompt),
            ]
        )
    except Exception as exc:
        print(f"[trip_planner_agent] Single-day edit call failed: {type(exc).__name__}: {exc}")
        return None, empty_usage

    token_usage = _extract_token_usage(response)
    print(f"[trip_planner_agent] Single-day edit call completed. tokens: prompt={token_usage['prompt_tokens']}, completion={token_usage['completion_tokens']}")

    raw_text = getattr(response, "content", "")
    if isinstance(raw_text, list):
        raw_text = "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in raw_text
        )

    json_text = _extract_json_object(str(raw_text))
    if json_text is None:
        print("[trip_planner_agent] Failed to extract JSON from the single-day edit result.")
        print(f"[trip_planner_agent] Raw response preview: {str(raw_text)[:300]}")
        return None, token_usage

    try:
        payload = json.loads(json_text)
        if not isinstance(payload, dict):
            raise ValueError("The single-day edit result is not a JSON object.")
        normalized_payload = _normalize_day_edit_payload(payload)
        return DayEditDraft.model_validate(normalized_payload), token_usage
    except Exception as exc:
        print(f"[trip_planner_agent] Single-day edit JSON parsing failed: {type(exc).__name__}: {exc}")
        print(f"[trip_planner_agent] Raw response preview: {str(raw_text)[:300]}")
        return None, token_usage
