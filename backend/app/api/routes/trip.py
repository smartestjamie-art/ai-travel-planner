from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    Itinerary,
    TokenStatsResponse,
    TripDetailResponse,
    TripEditRequest,
    TripListResponse,
    TripRequest,
    TripSaveRequest,
)
from app.services.storage_service import (
    delete_itinerary_by_trip_id,
    get_itinerary_by_trip_id,
    get_token_stats,
    list_saved_itineraries,
    save_itinerary,
)
from app.services.trip_service import edit_trip_itinerary, generate_trip_itinerary


router = APIRouter(prefix="/trip", tags=["trip"])


@router.get("", response_model=TripListResponse)
def list_trips() -> TripListResponse:
    """Return a summary list of saved trips."""
    return list_saved_itineraries()


@router.post("/generate", response_model=Itinerary)
def generate_trip(request: TripRequest) -> Itinerary:
    """Generate a structured itinerary."""
    return generate_trip_itinerary(request)


@router.get("/stats", response_model=TokenStatsResponse)
def get_trip_token_stats() -> TokenStatsResponse:
    """Return token consumption statistics for all saved trips."""
    return get_token_stats()


@router.post("/edit", response_model=Itinerary)
def edit_trip(request: TripEditRequest) -> Itinerary:
    """Return the updated itinerary based on the user's edit instructions."""
    return edit_trip_itinerary(request)


@router.post("/save")
def save_trip(request: TripSaveRequest) -> dict[str, str]:
    """Save the itinerary and return its trip_id."""
    saved_trip_id = save_itinerary(request.itinerary)
    return {
        "message": "Trip itinerary saved successfully.",
        "trip_id": saved_trip_id,
    }


@router.get("/{trip_id}", response_model=TripDetailResponse)
def get_trip_detail(trip_id: str) -> TripDetailResponse:
    """Look up a saved itinerary by trip_id."""
    trip_detail = get_itinerary_by_trip_id(trip_id)
    if trip_detail is None:
        raise HTTPException(status_code=404, detail="Trip not found.")
    return trip_detail


@router.delete("/{trip_id}")
def delete_trip(trip_id: str) -> dict[str, str]:
    """Delete a saved itinerary by trip_id."""
    deleted = delete_itinerary_by_trip_id(trip_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Trip not found.")
    return {
        "message": "Trip itinerary deleted successfully.",
        "trip_id": trip_id,
    }
