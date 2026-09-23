from pathlib import Path
import sys

import pytest
from pydantic import ValidationError


# Allow direct imports from backend/app when running tests from this file.
CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models.schemas import (  # noqa: E402
    BudgetBreakdown,
    DayPlan,
    HotelItem,
    Itinerary,
    MealItem,
    SpotItem,
    TransportItem,
    TripEditRequest,
    TripRequest,
    TripSaveRequest,
)


def build_trip_request() -> TripRequest:
    '''Build a sample TripRequest object for testing'''
    return TripRequest(
        destination="Dali",
        start_date="2026-04-10",
        end_date="2026-04-12",
        travelers=2,
        budget=3200,
        preferences=["natural scenery", "photography", "food"],
        pace="relaxed",
        dietary_preferences=["mild spice"],
        hotel_level="comfort",
        special_notes="Don't want to get up too early, hope to see a sunset.",
    )


def build_itinerary() -> Itinerary:
    '''Build a sample Itinerary object for testing'''
    day_one = DayPlan(
        day_index=1,
        date="2026-04-10",
        theme="Leisurely stroll through the old town",
        spots=[
            SpotItem(
                name="Dali Old Town",
                start_time="10:00",
                end_time="12:00",
                description="Start with a slow walk through the old town to settle into the trip's pace.",
                estimated_cost=0,
                location="Dali Old Town",
            )
        ],
        meals=[
            MealItem(
                name="Old Town Rice Noodle Shop",
                meal_type="lunch",
                estimated_cost=60,
                notes="Mild flavor available on request.",
            )
        ],
        hotel=HotelItem(
            name="Old Town Comfort Guesthouse",
            level="comfort",
            estimated_cost=280,
            location="Near Dali Old Town",
        ),
        transport=[
            TransportItem(
                mode="taxi",
                from_place="Dali Station",
                to_place="Dali Old Town",
                estimated_cost=35,
                duration="40 minutes",
            )
        ],
        notes=["Keep the first day relaxed and not too rushed."],
    )

    return Itinerary(
        trip_id="trip_dali_demo_001",
        destination="Dali",
        summary="A sample 3-day itinerary suited for a relaxed trip for two.",
        days=[day_one],
        estimated_budget=1550,
        budget_breakdown=BudgetBreakdown(
            transport=335,
            hotel=640,
            meals=180,
            tickets=120,
            other=275,
            total=1550,
        ),
        tips=["Large temperature swings between morning/night; bring a light jacket."],
        source_notes=["This result is currently manually crafted demo data for Day 2."],
    )


def test_trip_request_can_be_created_successfully() -> None:
    '''Test whether the TripRequest model can be created successfully'''
    request = build_trip_request()

    assert request.destination == "Dali"
    assert request.travelers == 2
    assert request.budget == 3200
    assert request.preferences == ["natural scenery", "photography", "food"]


def test_trip_request_rejects_invalid_travelers() -> None:
    '''Test that TripRequest raises ValidationError when travelers is 0'''
    with pytest.raises(ValidationError):
        TripRequest(
            destination="Dali",
            start_date="2026-04-10",
            end_date="2026-04-12",
            travelers=0,
            budget=3200,
        )


def test_trip_request_rejects_negative_budget() -> None:
    '''Test that TripRequest raises ValidationError when budget is negative'''
    with pytest.raises(ValidationError):
        TripRequest(
            destination="Dali",
            start_date="2026-04-10",
            end_date="2026-04-12",
            travelers=2,
            budget=-1,
        )


def test_itinerary_can_be_created_successfully() -> None:
    '''Test whether the Itinerary model can be created successfully'''
    itinerary = build_itinerary()

    assert itinerary.trip_id == "trip_dali_demo_001"
    assert itinerary.destination == "Dali"
    assert len(itinerary.days) == 1
    assert itinerary.days[0].theme == "Leisurely stroll through the old town"
    assert itinerary.budget_breakdown.total == 1550


def test_day_plan_contains_nested_objects() -> None:
    '''Test whether nested objects within the DayPlan model are created correctly'''
    itinerary = build_itinerary()
    first_day = itinerary.days[0]

    assert isinstance(first_day.spots[0], SpotItem)
    assert isinstance(first_day.meals[0], MealItem)
    assert isinstance(first_day.hotel, HotelItem)
    assert isinstance(first_day.transport[0], TransportItem)


def test_trip_edit_request_can_wrap_existing_itinerary() -> None:
    '''Test whether the TripEditRequest model can correctly wrap an existing Itinerary'''
    itinerary = build_itinerary()

    edit_request = TripEditRequest(
        trip_id=itinerary.trip_id,
        current_itinerary=itinerary,
        user_instruction="Make day 2 more relaxed",
        edit_scope="day_2",
        preserve_constraints=["keep a relaxed pace"],
    )

    assert edit_request.trip_id == "trip_dali_demo_001"
    assert edit_request.current_itinerary.destination == "Dali"
    assert edit_request.user_instruction == "Make day 2 more relaxed"


def test_trip_save_request_can_hold_full_itinerary() -> None:
    '''Test whether the TripSaveRequest model can correctly hold a complete Itinerary'''
    itinerary = build_itinerary()

    save_request = TripSaveRequest(
        trip_id=itinerary.trip_id,
        itinerary=itinerary,
        user_id="user_001",
    )

    assert save_request.trip_id == "trip_dali_demo_001"
    assert save_request.itinerary.summary == "A sample 3-day itinerary suited for a relaxed trip for two."
    assert save_request.user_id == "user_001"
