from __future__ import annotations

from datetime import date as DateType, datetime

from pydantic import BaseModel, Field


class TripRequest(BaseModel):
    """Request body used to generate a new itinerary."""

    destination: str = Field(..., description="Destination, e.g. Dali")
    start_date: DateType = Field(..., description="Trip start date")
    end_date: DateType = Field(..., description="Trip end date")
    travelers: int = Field(..., ge=1, description="Number of travelers")
    budget: float = Field(..., ge=0, description="Total budget")
    preferences: list[str] = Field(default_factory=list, description="Travel preference tags")
    pace: str | None = Field(default=None, description="Travel pace, e.g. relaxed, moderate, packed")
    dietary_preferences: list[str] = Field(
        default_factory=list,
        description="Dietary preferences or restrictions",
    )
    hotel_level: str | None = Field(default=None, description="Preferred hotel tier")
    special_notes: str | None = Field(default=None, description="Additional requirements")


class TripEditRequest(BaseModel):
    """Request body used to modify an existing itinerary."""

    trip_id: str = Field(..., description="ID of the trip to edit")
    current_itinerary: "Itinerary" = Field(..., description="The current, complete itinerary")
    user_instruction: str = Field(..., description="The user's new modification request")
    edit_scope: str | None = Field(default=None, description="Scope of the edit")
    preserve_constraints: list[str] = Field(
        default_factory=list,
        description="Conditions that should be preserved as much as possible",
    )


class TripSaveRequest(BaseModel):
    """Request body used to save the current itinerary."""

    trip_id: str = Field(..., description="ID of the trip to save")
    itinerary: "Itinerary" = Field(..., description="Complete itinerary data")
    user_id: str | None = Field(default=None, description="User ID; may be left empty in the current version")


class SpotItem(BaseModel):
    """A single attraction arrangement."""

    name: str = Field(..., description="Attraction name")
    start_time: str | None = Field(default=None, description="Start time")
    end_time: str | None = Field(default=None, description="End time")
    description: str | None = Field(default=None, description="Description of the visit")
    estimated_cost: float = Field(default=0.0, ge=0, description="Estimated cost")
    location: str | None = Field(default=None, description="Description of the attraction's location")
    image_url: str | None = Field(default=None, description="URL of the attraction's image")
    address: str | None = Field(default=None, description="Detailed address of the attraction")
    latitude: float | None = Field(default=None, description="Latitude of the attraction")
    longitude: float | None = Field(default=None, description="Longitude of the attraction")
    poi_id: str | None = Field(default=None, description="POI identifier returned by the map service")


class MealItem(BaseModel):
    """A single meal arrangement."""

    name: str = Field(..., description="Name of the restaurant or meal suggestion")
    meal_type: str = Field(..., description="Breakfast, lunch, dinner, etc.")
    estimated_cost: float = Field(default=0.0, ge=0, description="Estimated cost")
    notes: str | None = Field(default=None, description="Additional notes")


class HotelItem(BaseModel):
    """A single lodging arrangement."""

    name: str = Field(..., description="Hotel name")
    level: str | None = Field(default=None, description="Hotel tier")
    estimated_cost: float = Field(default=0.0, ge=0, description="Estimated cost")
    location: str | None = Field(default=None, description="Hotel location")
    address: str | None = Field(default=None, description="Detailed address of the hotel")
    latitude: float | None = Field(default=None, description="Latitude of the hotel")
    longitude: float | None = Field(default=None, description="Longitude of the hotel")


class TransportItem(BaseModel):
    """A single leg of transportation."""

    mode: str = Field(..., description="Mode of transport, e.g. walking, taxi, bus")
    from_place: str | None = Field(default=None, description="Departure location")
    to_place: str | None = Field(default=None, description="Destination")
    estimated_cost: float = Field(default=0.0, ge=0, description="Estimated cost")
    duration: str | None = Field(default=None, description="Estimated duration")
    distance_km: float | None = Field(default=None, ge=0, description="Estimated distance, in kilometers")
    estimated_minutes: int | None = Field(default=None, ge=0, description="Estimated duration, in minutes")


class BudgetBreakdown(BaseModel):
    """Budget breakdown."""

    transport: float = Field(default=0.0, ge=0, description="Transportation budget")
    hotel: float = Field(default=0.0, ge=0, description="Lodging budget")
    meals: float = Field(default=0.0, ge=0, description="Dining budget")
    tickets: float = Field(default=0.0, ge=0, description="Admission tickets budget")
    other: float = Field(default=0.0, ge=0, description="Other budget")
    total: float = Field(default=0.0, ge=0, description="Total budget")


class DayPlan(BaseModel):
    """Itinerary plan for a single day."""

    day_index: int = Field(..., ge=1, description="Day number")
    date: DateType | None = Field(default=None, description="Date of the day")
    theme: str | None = Field(default=None, description="Theme for the day")
    spots: list[SpotItem] = Field(default_factory=list, description="Attraction arrangements")
    meals: list[MealItem] = Field(default_factory=list, description="Meal arrangements")
    hotel: HotelItem | None = Field(default=None, description="Lodging arrangement")
    transport: list[TransportItem] = Field(default_factory=list, description="Transportation arrangements")
    notes: list[str] = Field(default_factory=list, description="Additional notes")


class TokenUsage(BaseModel):
    """Token consumption statistics for LLM calls."""

    rewrite_prompt_tokens: int = Field(default=0, ge=0, description="Query Rewrite input tokens")
    rewrite_completion_tokens: int = Field(default=0, ge=0, description="Query Rewrite output tokens")
    embedding_prompt_tokens: int = Field(default=0, ge=0, description="Query Embedding input tokens")
    embedding_completion_tokens: int = Field(default=0, ge=0, description="Query Embedding output tokens")
    planner_prompt_tokens: int = Field(default=0, ge=0, description="Itinerary generation input tokens")
    planner_completion_tokens: int = Field(default=0, ge=0, description="Itinerary generation output tokens")
    rerank_prompt_tokens: int = Field(default=0, ge=0, description="Rerank input tokens")
    rerank_completion_tokens: int = Field(default=0, ge=0, description="Rerank output tokens")

    @property
    def total_prompt_tokens(self) -> int:
        return (
            self.rewrite_prompt_tokens
            + self.embedding_prompt_tokens
            + self.planner_prompt_tokens
            + self.rerank_prompt_tokens
        )

    @property
    def total_completion_tokens(self) -> int:
        return (
            self.rewrite_completion_tokens
            + self.embedding_completion_tokens
            + self.planner_completion_tokens
            + self.rerank_completion_tokens
        )

    @property
    def total_tokens(self) -> int:
        return self.total_prompt_tokens + self.total_completion_tokens


class Itinerary(BaseModel):
    """A complete itinerary."""

    trip_id: str = Field(..., description="Unique identifier for the trip")
    destination: str = Field(..., description="Destination")
    summary: str = Field(..., description="Summary of the entire trip")
    days: list[DayPlan] = Field(default_factory=list, description="Day-by-day itinerary")
    estimated_budget: float = Field(default=0.0, ge=0, description="Total budget")
    budget_breakdown: BudgetBreakdown = Field(..., description="Budget breakdown")
    tips: list[str] = Field(default_factory=list, description="Travel tips")
    source_notes: list[str] = Field(
        default_factory=list,
        description="Additional notes produced by RAG or rule-based generation",
    )
    token_usage: TokenUsage | None = Field(default=None, description="LLM token consumption statistics")


class TripDetailResponse(BaseModel):
    """Response body returned when querying a saved itinerary."""

    trip_id: str = Field(..., description="Trip ID")
    itinerary: Itinerary = Field(..., description="The saved, complete itinerary")
    created_at: datetime | None = Field(default=None, description="Creation time")
    updated_at: datetime | None = Field(default=None, description="Last update time")


class TripSummaryItem(BaseModel):
    """Summary information for a saved itinerary."""

    trip_id: str = Field(..., description="Trip ID")
    destination: str = Field(..., description="Destination")
    summary: str = Field(..., description="Itinerary summary")
    created_at: datetime | None = Field(default=None, description="Creation time")
    updated_at: datetime | None = Field(default=None, description="Last update time")


class TripListResponse(BaseModel):
    """Response structure for the trip list endpoint."""

    total: int = Field(..., ge=0, description="Total number of items in the list")
    items: list[TripSummaryItem] = Field(default_factory=list, description="List of trip summaries")


class TripTokenStatsItem(BaseModel):
    """Token consumption for a single trip."""

    trip_id: str = Field(..., description="Trip ID")
    destination: str = Field(..., description="Destination")
    token_usage: TokenUsage = Field(..., description="Token consumption")


class TokenStatsResponse(BaseModel):
    """Response structure for the token consumption statistics endpoint."""

    trip_count: int = Field(..., ge=0, description="Number of trips included in the statistics")
    total_prompt_tokens: int = Field(default=0, ge=0, description="Total input tokens")
    total_completion_tokens: int = Field(default=0, ge=0, description="Total output tokens")
    total_tokens: int = Field(default=0, ge=0, description="Total tokens")
    items: list[TripTokenStatsItem] = Field(default_factory=list, description="Per-trip token breakdown")
