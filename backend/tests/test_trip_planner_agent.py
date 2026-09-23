import json
from pathlib import Path
import sys
from types import ModuleType


# Allow test files to import modules under backend/app directly.
CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import app.agents.trip_planner_agent as trip_planner_agent  # noqa: E402
from app.models.schemas import (  # noqa: E402
    BudgetBreakdown,
    DayPlan,
    Itinerary,
    MealItem,
    SpotItem,
    TripEditRequest,
    TripRequest,
)


def build_trip_request() -> TripRequest:
    """Build a valid TripRequest for reuse across agent tests."""
    return TripRequest(
        destination="Kyoto",
        start_date="2026-04-10",
        end_date="2026-04-12",
        travelers=2,
        budget=3200,
        preferences=["nature scenery", "photography", "food"],
        pace="relaxed",
        dietary_preferences=["mild spice"],
        hotel_level="comfort",
        special_notes="Don't want to wake up too early; hoping for a spot good for sunset viewing",
    )


def build_planner_draft(day_count: int) -> trip_planner_agent.PlannerDraft:
    """Build a fake PlannerDraft simulating a normal LLM response."""
    return trip_planner_agent.PlannerDraft(
        summary="This is a draft itinerary for a relaxed Kyoto trip.",
        tips=["Big day/night temperature swings, bring a light jacket."],
        days=[
            trip_planner_agent.PlannerDayDraft(
                day_index=index + 1,
                theme=f"Day {index + 1} theme",
                spot_name=f"Spot {index + 1}",
                spot_description=f"Reason to recommend spot {index + 1}.",
                meal_name=f"Restaurant {index + 1}",
                meal_notes=f"Meal notes {index + 1}",
                daily_note=f"Notes for the day {index + 1}",
            )
            for index in range(day_count)
        ],
    )


def install_fake_langchain_openai(monkeypatch, result: trip_planner_agent.PlannerDraft) -> tuple[type, type]:
    """Inject a fake langchain_openai module into sys.modules and return the two fake classes."""

    class FakeResponse:
        def __init__(self, content):
            self.content = content
            self.response_metadata = {
                "token_usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150,
                }
            }

    class FakeChatOpenAI:
        last_init_kwargs = None
        last_messages = None

        def __init__(self, **kwargs):
            FakeChatOpenAI.last_init_kwargs = kwargs

        def invoke(self, messages):
            FakeChatOpenAI.last_messages = messages
            return FakeResponse(result.model_dump_json())

    fake_module = ModuleType("langchain_openai")
    fake_module.ChatOpenAI = FakeChatOpenAI
    monkeypatch.setitem(sys.modules, "langchain_openai", fake_module)

    return FakeChatOpenAI, FakeResponse


def test_collect_trip_context_calls_rag_tool_with_expected_arguments(monkeypatch) -> None:
    """Test that collect_trip_context passes its arguments correctly to rag_tool."""
    captured = {}

    def fake_get_destination_guide_context(destination, preferences, pace, special_notes, top_k):
        captured["destination"] = destination
        captured["preferences"] = preferences
        captured["pace"] = pace
        captured["special_notes"] = special_notes
        captured["top_k"] = top_k
        return (
            ["Guide snippet 1", "Guide snippet 2"],
            {"prompt_tokens": 0, "completion_tokens": 0},
            {"prompt_tokens": 0, "completion_tokens": 0},
            {"prompt_tokens": 0, "completion_tokens": 0},
        )

    monkeypatch.setattr(
        trip_planner_agent,
        "get_destination_guide_context",
        fake_get_destination_guide_context,
    )

    results, _, _, _ = trip_planner_agent.collect_trip_context(
        "Kyoto",
        ["food", "photography"],
        pace="relaxed",
        special_notes="Want to see the sunset, don't want to wake up early",
    )

    assert results == ["Guide snippet 1", "Guide snippet 2"]
    assert captured == {
        "destination": "Kyoto",
        "preferences": ["food", "photography"],
        "pace": "relaxed",
        "special_notes": "Want to see the sunset, don't want to wake up early",
        "top_k": 5,
    }


def test_generate_planner_draft_returns_none_when_api_key_is_missing(monkeypatch) -> None:
    """Test that None is returned directly when LLM_API_KEY is not configured."""
    monkeypatch.setattr(trip_planner_agent, "LLM_API_KEY", "")

    result, usage = trip_planner_agent.generate_planner_draft(
        request=build_trip_request(),
        rag_contexts=["Kyoto's old town is great for a leisurely stroll."],
        day_count=3,
    )

    assert result is None
    assert usage == {"prompt_tokens": 0, "completion_tokens": 0}


def test_generate_planner_draft_returns_structured_result_with_mock_llm(monkeypatch) -> None:
    """Test that the agent can call the structured LLM and return a PlannerDraft."""
    monkeypatch.setattr(trip_planner_agent, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(trip_planner_agent, "LLM_MODEL", "fake-model")
    monkeypatch.setattr(trip_planner_agent, "LLM_BASE_URL", "https://example.test")
    monkeypatch.setattr(trip_planner_agent, "LLM_TIMEOUT_SECONDS", 60)
    monkeypatch.setattr(trip_planner_agent, "LLM_MAX_RETRIES", 1)

    expected_result = build_planner_draft(day_count=3)
    FakeChatOpenAI, _ = install_fake_langchain_openai(monkeypatch, expected_result)

    result, usage = trip_planner_agent.generate_planner_draft(
        request=build_trip_request(),
        rag_contexts=["Kyoto's old town is great for an evening walk.", "The lakeside greenway is great for cycling."],
        day_count=3,
    )

    assert result == expected_result
    assert usage["prompt_tokens"] == 100
    assert usage["completion_tokens"] == 50
    assert FakeChatOpenAI.last_init_kwargs == {
        "model": "fake-model",
        "temperature": 0.3,
        "api_key": "test-key",
        "base_url": "https://example.test",
        "timeout": 60,
        "max_retries": 1,
    }


def test_generate_planner_draft_builds_prompt_with_request_and_rag_context(monkeypatch) -> None:
    """Test that the prompt includes the user's request info and local guide context."""
    monkeypatch.setattr(trip_planner_agent, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(trip_planner_agent, "LLM_MODEL", "fake-model")
    monkeypatch.setattr(trip_planner_agent, "LLM_BASE_URL", "")
    monkeypatch.setattr(trip_planner_agent, "LLM_TIMEOUT_SECONDS", 60)
    monkeypatch.setattr(trip_planner_agent, "LLM_MAX_RETRIES", 1)

    expected_result = build_planner_draft(day_count=3)
    FakeChatOpenAI, _ = install_fake_langchain_openai(monkeypatch, expected_result)

    trip_planner_agent.generate_planner_draft(
        request=build_trip_request(),
        rag_contexts=["Kyoto's old town is great for an evening walk.", "The lakeside greenway is great for cycling."],
        day_count=3,
    )

    messages = FakeChatOpenAI.last_messages
    assert messages is not None
    assert messages[0][0] == "system"
    assert "travel planning assistant" in messages[0][1]
    assert messages[1][0] == "human"
    assert "Destination: Kyoto" in messages[1][1]
    assert "Preferences: nature scenery, photography, food" in messages[1][1]
    assert "Local guide context:" in messages[1][1]
    assert "Kyoto's old town is great for an evening walk." in messages[1][1]
    assert "The lakeside greenway is great for cycling." in messages[1][1]


def test_generate_planner_draft_returns_none_when_day_count_mismatches(monkeypatch) -> None:
    """Test that the result falls back to None when the LLM returns an unexpected number of days."""
    monkeypatch.setattr(trip_planner_agent, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(trip_planner_agent, "LLM_MODEL", "fake-model")
    monkeypatch.setattr(trip_planner_agent, "LLM_BASE_URL", "")
    monkeypatch.setattr(trip_planner_agent, "LLM_TIMEOUT_SECONDS", 60)
    monkeypatch.setattr(trip_planner_agent, "LLM_MAX_RETRIES", 1)

    wrong_result = build_planner_draft(day_count=2)
    install_fake_langchain_openai(monkeypatch, wrong_result)

    result, usage = trip_planner_agent.generate_planner_draft(
        request=build_trip_request(),
        rag_contexts=["Kyoto's old town is great for an evening walk."],
        day_count=3,
    )

    assert result is None


def test_generate_day_edit_draft_accepts_nested_day_shape(monkeypatch) -> None:
    """Test that a single-day edit result is still parsed correctly even when it comes back in a DayPlan-style shape."""

    class FakeResponse:
        def __init__(self, content):
            self.content = content
            self.response_metadata = {
                "token_usage": {
                    "prompt_tokens": 80,
                    "completion_tokens": 30,
                    "total_tokens": 110,
                }
            }

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, messages):
            return FakeResponse(
                json.dumps(
                    {
                        "theme": "A more relaxed slow-paced day in the old town",
                        "spots": [
                            {
                                "name": "Lakeside old town",
                                "description": "Better suited for watching the sea, relaxing, and catching the sunset.",
                            }
                        ],
                        "meals": [
                            {
                                "name": "Seaview afternoon tea",
                                "notes": "Keep the relaxed pace, mild spice.",
                            }
                        ],
                        "notes": ["Head out slowly in the morning, go to the lakeside for sunset in the afternoon."],
                    },
                    ensure_ascii=False,
                )
            )

    fake_module = ModuleType("langchain_openai")
    fake_module.ChatOpenAI = FakeChatOpenAI
    monkeypatch.setitem(sys.modules, "langchain_openai", fake_module)

    monkeypatch.setattr(trip_planner_agent, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(trip_planner_agent, "LLM_MODEL", "fake-model")
    monkeypatch.setattr(trip_planner_agent, "LLM_BASE_URL", "")
    monkeypatch.setattr(trip_planner_agent, "LLM_TIMEOUT_SECONDS", 60)
    monkeypatch.setattr(trip_planner_agent, "LLM_MAX_RETRIES", 1)

    itinerary = build_planner_draft(day_count=3)
    target_day = DayPlan(
        day_index=2,
        date="2026-04-11",
        theme="Original theme",
        spots=[
            SpotItem(
                name="Old town district",
                start_time="10:00",
                end_time="12:00",
                description="Original spot description",
                estimated_cost=50.0,
                location="Kyoto",
            )
        ],
        meals=[
            MealItem(
                name="Local specialty snack",
                meal_type="lunch",
                estimated_cost=30.0,
                notes="Original meal notes",
            )
        ],
        notes=["Original notes"],
    )
    request = TripEditRequest(
        trip_id="trip_demo",
        current_itinerary=Itinerary(
            trip_id="trip_demo",
            destination="Kyoto",
            summary=itinerary.summary,
            days=[],
            estimated_budget=1000,
            budget_breakdown=BudgetBreakdown(
                transport=100,
                hotel=300,
                meals=200,
                tickets=100,
                other=100,
                total=800,
            ),
            tips=[],
            source_notes=[],
        ),
        user_instruction="Make day two more relaxed, don't pack the schedule too full",
        edit_scope="day_2",
        preserve_constraints=["Preserve the budget structure"],
    )

    result, usage = trip_planner_agent.generate_day_edit_draft(request, target_day)

    assert result is not None
    assert result.theme == "A more relaxed slow-paced day in the old town"
    assert usage["prompt_tokens"] == 80
    assert usage["completion_tokens"] == 30
    assert result.spot_name == "Lakeside old town"
    assert result.spot_description == "Better suited for watching the sea, relaxing, and catching the sunset."
    assert result.meal_name == "Seaview afternoon tea"
    assert result.meal_notes == "Keep the relaxed pace, mild spice."
    assert result.daily_note == "Head out slowly in the morning, go to the lakeside for sunset in the afternoon."
