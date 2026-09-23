from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.weather_service import get_weather_forecast


class WeatherForecastDay(BaseModel):
    """Weather forecast for a single day."""

    date: str | None = Field(default=None, description="Date")
    week: str | None = Field(default=None, description="Day-of-week index")
    day_weather: str | None = Field(default=None, description="Daytime weather")
    night_weather: str | None = Field(default=None, description="Nighttime weather")
    day_temp: str | None = Field(default=None, description="Daytime temperature")
    night_temp: str | None = Field(default=None, description="Nighttime temperature")
    day_wind: str | None = Field(default=None, description="Daytime wind direction")
    night_wind: str | None = Field(default=None, description="Nighttime wind direction")


class WeatherForecastResponse(BaseModel):
    """Response for the weather forecast endpoint."""

    city: str = Field(..., description="City name")
    province: str | None = Field(default=None, description="Province")
    adcode: str | None = Field(default=None, description="Administrative area code")
    report_time: str | None = Field(default=None, description="Forecast report time")
    days: list[WeatherForecastDay] = Field(default_factory=list, description="Upcoming weather")


router = APIRouter(prefix="/weather", tags=["weather"])


@router.get("/forecast", response_model=WeatherForecastResponse)
def get_forecast(city: str = Query(..., description="Destination city")) -> WeatherForecastResponse:
    """Return the weather forecast for a given city name."""
    try:
        payload = get_weather_forecast(city)
        return WeatherForecastResponse(**payload)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
