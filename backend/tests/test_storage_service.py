from pathlib import Path
import sys
import uuid


CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models.schemas import TripRequest  # noqa: E402
from app.services.storage_service import get_itinerary_by_trip_id, save_itinerary  # noqa: E402
from app.services.trip_service import generate_trip_itinerary  # noqa: E402


def build_trip_request() -> TripRequest:
    """Build a valid TripRequest for reuse in storage layer tests."""
    return TripRequest(
        destination="Dali",
        start_date="2026-04-10",
        end_date="2026-04-12",
        travelers=2,
        budget=3200,
        preferences=["natural scenery", "photography", "food"],
        pace="relaxed",
        dietary_preferences=["mild spice"],
        hotel_level="comfortable",
        special_notes="Don't want to wake up too early; would like a spot suitable for watching the sunset",
    )


def test_save_itinerary_returns_trip_id() -> None:
    """Test that saving an itinerary returns a trip_id."""
    itinerary = generate_trip_itinerary(build_trip_request())
    itinerary.trip_id = f"{itinerary.trip_id}_{uuid.uuid4().hex[:8]}"

    saved_trip_id = save_itinerary(itinerary)

    assert saved_trip_id == itinerary.trip_id


def test_get_itinerary_by_trip_id_returns_saved_result() -> None:
    """Test that a saved itinerary can be read back by trip_id."""
    itinerary = generate_trip_itinerary(build_trip_request())
    itinerary.trip_id = f"{itinerary.trip_id}_{uuid.uuid4().hex[:8]}"

    save_itinerary(itinerary)
    trip_detail = get_itinerary_by_trip_id(itinerary.trip_id)

    assert trip_detail is not None
    assert trip_detail.trip_id == itinerary.trip_id
    assert trip_detail.itinerary.destination == "Dali"
    assert len(trip_detail.itinerary.days) == 3


def test_get_itinerary_by_trip_id_returns_none_for_missing_trip() -> None:
    """Test that querying a non-existent trip_id returns None."""
    trip_detail = get_itinerary_by_trip_id("trip_not_exists")
    assert trip_detail is None
