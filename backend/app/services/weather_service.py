from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import (
    AMAP_API_KEY,
    AMAP_BASE_URL,
    AMAP_TIMEOUT_SECONDS,
    REDIS_WEATHER_TTL_SECONDS,
)
from app.services.cache_service import get_cached_json, set_cached_json
from app.services.map_service import geocode_address


logger = logging.getLogger(__name__)


def _ensure_amap_api_key() -> None:
    """Ensure that AMAP_API_KEY is configured in the current environment."""
    if not AMAP_API_KEY:
        raise RuntimeError("AMAP_API_KEY is not configured in the current environment; cannot call the weather service.")


def _build_client() -> httpx.Client:
    """Create a client for accessing the Amap weather API."""
    return httpx.Client(timeout=AMAP_TIMEOUT_SECONDS)


def _request_amap_weather(path: str, params: dict[str, Any]) -> dict[str, Any]:
    """Call the Amap weather endpoint and return the JSON result."""
    _ensure_amap_api_key()

    request_params = {
        "key": AMAP_API_KEY,
        **params,
    }

    with _build_client() as client:
        response = client.get(f"{AMAP_BASE_URL}{path}", params=request_params)
        response.raise_for_status()
        payload = response.json()

    if payload.get("status") != "1":
        info = payload.get("info", "Unknown error")
        raise RuntimeError(f"Amap weather API call failed: {info}")

    return payload


def _normalize_cache_text(value: str | None) -> str:
    """Apply simple normalization to text used in cache keys."""
    if value is None:
        return ""
    return value.strip().lower()


def get_weather_forecast(city: str) -> dict[str, Any]:
    """Get the upcoming weather forecast for the given city."""
    cache_key = f"weather:forecast:{_normalize_cache_text(city)}"
    cached_value = get_cached_json(cache_key)
    if cached_value is not None:
        logger.info("weather cache hit: city=%s", city)
        return cached_value
    logger.info("weather cache miss: city=%s", city)

    geocode = geocode_address(city, city=city)
    city_code = geocode.get("adcode") if geocode is not None else city

    payload = _request_amap_weather(
        "/weather/weatherInfo",
        {
            "city": city_code or city,
            "extensions": "all",
        },
    )

    forecasts = payload.get("forecasts", [])
    if not forecasts:
        raise RuntimeError("No weather forecast results were returned.")

    first = forecasts[0]
    casts = first.get("casts", [])

    days = [
        {
            "date": cast.get("date"),
            "week": cast.get("week"),
            "day_weather": cast.get("dayweather"),
            "night_weather": cast.get("nightweather"),
            "day_temp": cast.get("daytemp"),
            "night_temp": cast.get("nighttemp"),
            "day_wind": cast.get("daywind"),
            "night_wind": cast.get("nightwind"),
        }
        for cast in casts
    ]

    result = {
        "city": first.get("city") or city,
        "province": first.get("province"),
        "adcode": first.get("adcode"),
        "report_time": first.get("reporttime"),
        "days": days,
    }
    set_cached_json(cache_key, result, expire_seconds=REDIS_WEATHER_TTL_SECONDS)
    return result
