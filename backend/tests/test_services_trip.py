from pathlib import Path
import sys


# Allow test files to import modules under backend/app directly.
CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models.schemas import TripEditRequest, TripRequest  # noqa: E402
from app.services.trip_service import edit_trip_itinerary, generate_trip_itinerary  # noqa: E402
import app.services.trip_service as trip_service  # noqa: E402


'''
Given a TripRequest, does the service correctly return an Itinerary?

What this tests:
    Can accept a TripRequest
    Returns a correctly structured Itinerary
    Generates a reasonable demo result based on dates and preferences
'''
def build_trip_request() -> TripRequest:
    """Build a valid TripRequest for reuse across service tests."""
    return TripRequest(
        destination="Dali",
        start_date="2026-04-10",
        end_date="2026-04-12",
        travelers=2,
        budget=3200,
        preferences=["Nature & Scenery", "Photography", "Food"],
        pace="Relaxed",
        dietary_preferences=["Less Spicy"],
        hotel_level="Comfort",
        special_notes="Don't want to get up too early — would like a spot good for watching the sunset",
    )


def test_generate_trip_itinerary_returns_itinerary_object() -> None:
    """Test that the service returns a fully structured itinerary."""
    request = build_trip_request()

    itinerary = generate_trip_itinerary(request)

    assert itinerary.destination == "Dali"
    assert itinerary.trip_id.startswith("trip_")
    assert itinerary.summary != ""
    assert len(itinerary.days) == 3
    assert itinerary.budget_breakdown.total >= 0


def test_generate_trip_itinerary_builds_day_plans_by_date_range() -> None:
    """Test that the service generates a matching number of DayPlans based on the date range."""
    request = build_trip_request()

    itinerary = generate_trip_itinerary(request)

    assert len(itinerary.days) == 3
    assert itinerary.days[0].day_index == 1
    assert itinerary.days[1].day_index == 2
    assert itinerary.days[2].day_index == 3


def test_generate_trip_itinerary_keeps_request_preferences_in_summary() -> None:
    """Test that the user's preferences are written into the returned summary."""
    request = build_trip_request()

    itinerary = generate_trip_itinerary(request)

    assert "Nature & Scenery" in itinerary.summary
    assert "Photography" in itinerary.summary
    assert "Food" in itinerary.summary

'''
What this tests:
    Whether the service can modify an existing Itinerary
    Whether edit_scope="day_2" really edits the second day
    Whether the user's instruction really affects the result
'''
def test_edit_trip_itinerary_updates_target_day_theme(monkeypatch) -> None:
    """Test that the edit logic can update the theme and notes for the target day."""
    monkeypatch.setattr(trip_service, "generate_day_edit_draft", lambda request, target_day: (None, {"prompt_tokens": 0, "completion_tokens": 0}))
    original_itinerary = generate_trip_itinerary(build_trip_request())

    edit_request = TripEditRequest(
        trip_id=original_itinerary.trip_id,
        current_itinerary=original_itinerary,
        user_instruction="Make day two more relaxed",
        edit_scope="day_2",
        preserve_constraints=["Preserve the budget structure"],
    )

    updated_itinerary = edit_trip_itinerary(edit_request)

    assert updated_itinerary.days[1].theme.endswith("(adjusted to be more relaxed)")
    assert "The pace has been made more relaxed per your request." in updated_itinerary.days[1].notes


def test_edit_trip_itinerary_can_replace_first_spot_with_free_time(monkeypatch) -> None:
    """Test that a "don't schedule" instruction turns the attraction into free time."""
    monkeypatch.setattr(trip_service, "generate_day_edit_draft", lambda request, target_day: (None, {"prompt_tokens": 0, "completion_tokens": 0}))
    original_itinerary = generate_trip_itinerary(build_trip_request())

    edit_request = TripEditRequest(
        trip_id=original_itinerary.trip_id,
        current_itinerary=original_itinerary,
        user_instruction="Don't schedule any attractions for day two",
        edit_scope="day_2",
        preserve_constraints=[],
    )

    updated_itinerary = edit_trip_itinerary(edit_request)

    assert updated_itinerary.days[1].spots[0].name == "Free time / flexible schedule"
    assert "Fixed attractions have been reduced" in updated_itinerary.days[1].spots[0].description


def test_edit_trip_itinerary_can_apply_llm_day_edit(monkeypatch) -> None:
    """Test that when an LLM edit draft is available, it takes priority in rewriting the target day."""

    class FakeDayEditDraft:
        theme = "A more relaxed, slow-paced day at Erhai Lake"
        spot_name = "Shuanglang Old Town"
        spot_description = "Better suited for a slow-paced view of the lake and the sunset."
        meal_name = "Lakeview afternoon tea"
        meal_notes = "Mild spice, relaxed pace."
        daily_note = "Head out in the afternoon and go to Shuanglang for a slow sunset watch."

    monkeypatch.setattr(
        trip_service,
        "generate_day_edit_draft",
        lambda request, target_day: (FakeDayEditDraft(), {"prompt_tokens": 80, "completion_tokens": 30}),
    )
    original_itinerary = generate_trip_itinerary(build_trip_request())

    edit_request = TripEditRequest(
        trip_id=original_itinerary.trip_id,
        current_itinerary=original_itinerary,
        user_instruction="Make day two more relaxed, don't overpack the schedule",
        edit_scope="day_2",
        preserve_constraints=["Preserve the budget structure"],
    )

    updated_itinerary = edit_trip_itinerary(edit_request)

    assert updated_itinerary.days[1].theme == "A more relaxed, slow-paced day at Erhai Lake"
    assert updated_itinerary.days[1].spots[0].name == "Shuanglang Old Town"
    assert updated_itinerary.days[1].meals[0].name == "Lakeview afternoon tea"
    assert updated_itinerary.days[1].notes[-1] == "Head out in the afternoon and go to Shuanglang for a slow sunset watch."

def test_generate_trip_itinerary_includes_local_guide_context() -> None:
    """Test that the generated result already includes local guide retrieval context."""
    itinerary = generate_trip_itinerary(build_trip_request())

    joined_notes = "\n".join(itinerary.source_notes)
    joined_spots = "\n".join(day.spots[0].name for day in itinerary.days if day.spots)

    assert len(itinerary.source_notes) >= 2
    assert "Dali" in joined_notes
    assert (
        "Dali Old Town" in joined_spots
        or "Xizhou Ancient Town" in joined_spots
        or "Three Pagodas of Chongsheng Temple" in joined_spots
        or "Erhai Lake Eco-Corridor" in joined_spots
    )
