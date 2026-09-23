from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import (
    AMAP_API_KEY,
    AMAP_BASE_URL,
    AMAP_DEFAULT_CITY,
    AMAP_TIMEOUT_SECONDS,
    REDIS_MAP_TTL_SECONDS,
)
from app.models.schemas import HotelItem, Itinerary, SpotItem, TransportItem
from app.services.cache_service import get_cached_json, set_cached_json


logger = logging.getLogger(__name__)


def _ensure_amap_api_key() -> None:
    """Ensure the current environment has an AMap key configured."""
    if not AMAP_API_KEY:
        raise RuntimeError("AMAP_API_KEY is not configured in the current environment; cannot call the AMap service.")


def _build_client() -> httpx.Client:
    """Create an HTTP client for accessing the AMap API."""
    return httpx.Client(timeout=AMAP_TIMEOUT_SECONDS)


def _request_amap(path: str, params: dict[str, Any]) -> dict[str, Any]:
    """Call the AMap API and return the JSON result."""
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
        raise RuntimeError(f"AMap API call failed: {info}")

    return payload


def _parse_float(value: str | None) -> float | None:
    """Safely convert a string to a float."""
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _split_location(location: str | None) -> tuple[float | None, float | None]:
    """Split the 'longitude,latitude' text returned by AMap into two floats."""
    if not location or "," not in location:
        return None, None

    longitude_text, latitude_text = location.split(",", 1)
    return _parse_float(latitude_text), _parse_float(longitude_text)


def _normalize_cache_text(value: str | None) -> str:
    """Simple normalization for text used in cache keys."""
    if value is None:
        return ""
    return value.strip().lower()


def geocode_address(address: str, city: str | None = None) -> dict[str, Any] | None:
    """Get latitude/longitude information from an address."""
    cache_key = (
        f"map:geocode:{_normalize_cache_text(address)}:{_normalize_cache_text(city or AMAP_DEFAULT_CITY)}"
    )
    cached_value = get_cached_json(cache_key)
    if cached_value is not None:
        logger.info("map geocode cache hit: address=%s city=%s", address, city or AMAP_DEFAULT_CITY)
        return cached_value
    logger.info("map geocode cache miss: address=%s city=%s", address, city or AMAP_DEFAULT_CITY)

    payload = _request_amap(
        "/geocode/geo",
        {
            "address": address,
            "city": city or AMAP_DEFAULT_CITY,
        },
    )

    geocodes = payload.get("geocodes", [])
    if not geocodes:
        return None

    first = geocodes[0]
    latitude, longitude = _split_location(first.get("location"))
    result = {
        "formatted_address": first.get("formatted_address", address),
        "province": first.get("province"),
        "city": first.get("city"),
        "district": first.get("district"),
        "adcode": first.get("adcode"),
        "latitude": latitude,
        "longitude": longitude,
    }
    set_cached_json(cache_key, result, expire_seconds=REDIS_MAP_TTL_SECONDS)
    return result


def search_places(
    keyword: str,
    city: str | None = None,
    page_size: int = 5,
) -> list[dict[str, Any]]:
    """Search POIs by keyword."""
    cache_key = (
        f"map:place:{_normalize_cache_text(keyword)}:{_normalize_cache_text(city or AMAP_DEFAULT_CITY)}:{page_size}"
    )
    cached_value = get_cached_json(cache_key)
    if cached_value is not None:
        logger.info("map place cache hit: keyword=%s city=%s", keyword, city or AMAP_DEFAULT_CITY)
        return cached_value
    logger.info("map place cache miss: keyword=%s city=%s", keyword, city or AMAP_DEFAULT_CITY)

    payload = _request_amap(
        "/place/text",
        {
            "keywords": keyword,
            "city": city or AMAP_DEFAULT_CITY,
            "offset": page_size,
            "page": 1,
            "extensions": "all",
        },
    )

    pois = payload.get("pois", [])
    results: list[dict[str, Any]] = []
    for poi in pois:
        latitude, longitude = _split_location(poi.get("location"))
        photos = poi.get("photos") if isinstance(poi.get("photos"), list) else []
        first_photo = photos[0] if photos and isinstance(photos[0], dict) else {}
        results.append(
            {
                "name": poi.get("name"),
                "address": poi.get("address"),
                "cityname": poi.get("cityname"),
                "adname": poi.get("adname"),
                "type": poi.get("type"),
                "poi_id": poi.get("id"),
                "image_url": first_photo.get("url"),
                "latitude": latitude,
                "longitude": longitude,
            }
        )

    set_cached_json(cache_key, results, expire_seconds=REDIS_MAP_TTL_SECONDS)
    return results


def estimate_route(
    origin_longitude: float,
    origin_latitude: float,
    destination_longitude: float,
    destination_latitude: float,
) -> dict[str, Any] | None:
    """Estimate the driving distance and duration between two points."""
    cache_key = (
        "map:route:"
        f"{origin_longitude:.6f},{origin_latitude:.6f}:"
        f"{destination_longitude:.6f},{destination_latitude:.6f}"
    )
    cached_value = get_cached_json(cache_key)
    if cached_value is not None:
        logger.info(
            "map route cache hit: origin=%s,%s destination=%s,%s",
            origin_longitude,
            origin_latitude,
            destination_longitude,
            destination_latitude,
        )
        return cached_value
    logger.info(
        "map route cache miss: origin=%s,%s destination=%s,%s",
        origin_longitude,
        origin_latitude,
        destination_longitude,
        destination_latitude,
    )

    payload = _request_amap(
        "/direction/driving",
        {
            "origin": f"{origin_longitude},{origin_latitude}",
            "destination": f"{destination_longitude},{destination_latitude}",
            "strategy": 0,
        },
    )

    route = payload.get("route", {})
    paths = route.get("paths", [])
    if not paths:
        return None

    first_path = paths[0]
    distance_meters = _parse_float(first_path.get("distance"))
    duration_seconds = _parse_float(first_path.get("duration"))

    result = {
        "distance_meters": distance_meters,
        "distance_km": round(distance_meters / 1000, 2) if distance_meters is not None else None,
        "duration_seconds": duration_seconds,
        "estimated_minutes": round(duration_seconds / 60) if duration_seconds is not None else None,
        "taxi_cost": _parse_float(route.get("taxi_cost")),
    }
    set_cached_json(cache_key, result, expire_seconds=REDIS_MAP_TTL_SECONDS)
    return result


def _pick_best_place(keyword: str, city: str | None = None) -> dict[str, Any] | None:
    """Prefer the first result from a POI search."""
    results = search_places(keyword=keyword, city=city, page_size=1)
    if not results:
        return None
    return results[0]


def _enrich_spot(spot: SpotItem, city: str | None = None) -> bool:
    """Fill in a single spot's address, coordinates, and POI information."""
    place = _pick_best_place(spot.name, city=city)
    if place is None and spot.location:
        place = _pick_best_place(spot.location, city=city)

    if place is None:
        query_address = spot.address or spot.location or spot.name
        geocode = geocode_address(query_address, city=city)
        if geocode is None:
            return False
        spot.address = geocode.get("formatted_address") or spot.address
        spot.latitude = geocode.get("latitude")
        spot.longitude = geocode.get("longitude")
        return True

    spot.address = place.get("address") or spot.address
    spot.image_url = place.get("image_url") or spot.image_url
    spot.latitude = place.get("latitude")
    spot.longitude = place.get("longitude")
    spot.poi_id = place.get("poi_id") or spot.poi_id
    return True


def _enrich_hotel(hotel: HotelItem, city: str | None = None) -> bool:
    """Fill in a single hotel's address and coordinates."""
    place = _pick_best_place(hotel.name, city=city)
    if place is None and hotel.location:
        place = _pick_best_place(hotel.location, city=city)

    if place is None:
        query_address = hotel.address or hotel.location or hotel.name
        geocode = geocode_address(query_address, city=city)
        if geocode is None:
            return False
        hotel.address = geocode.get("formatted_address") or hotel.address
        hotel.latitude = geocode.get("latitude")
        hotel.longitude = geocode.get("longitude")
        return True

    hotel.address = place.get("address") or hotel.address
    hotel.latitude = place.get("latitude")
    hotel.longitude = place.get("longitude")
    return True


def _geocode_place_text(place_text: str | None, city: str | None = None) -> dict[str, Any] | None:
    """Try to resolve a text place name into a result with coordinates."""
    if not place_text:
        return None

    place = _pick_best_place(place_text, city=city)
    if place is not None:
        return {
            "latitude": place.get("latitude"),
            "longitude": place.get("longitude"),
            "address": place.get("address"),
        }

    geocode = geocode_address(place_text, city=city)
    if geocode is not None:
        return {
            "latitude": geocode.get("latitude"),
            "longitude": geocode.get("longitude"),
            "address": geocode.get("formatted_address"),
        }
    return None


def _enrich_transport(transport: TransportItem, city: str | None = None) -> bool:
    """Fill in the distance and duration information for a single transport leg."""
    origin = _geocode_place_text(transport.from_place, city=city)
    destination = _geocode_place_text(transport.to_place, city=city)
    if not origin or not destination:
        return False

    if origin.get("latitude") is None or origin.get("longitude") is None:
        return False
    if destination.get("latitude") is None or destination.get("longitude") is None:
        return False

    route = estimate_route(
        origin_longitude=origin["longitude"],
        origin_latitude=origin["latitude"],
        destination_longitude=destination["longitude"],
        destination_latitude=destination["latitude"],
    )
    if route is None:
        return False

    transport.distance_km = route.get("distance_km")
    transport.estimated_minutes = route.get("estimated_minutes")
    if route.get("estimated_minutes") is not None and not transport.duration:
        transport.duration = f"{route['estimated_minutes']} minutes"
    return True


def enrich_itinerary_with_map_data(itinerary: Itinerary, city: str | None = None) -> Itinerary:
    """Use the AMap service to fill in map-related fields on the itinerary."""
    enriched_count = 0

    for day in itinerary.days:
        for spot in day.spots:
            try:
                if _enrich_spot(spot, city=city or itinerary.destination):
                    enriched_count += 1
            except Exception:
                continue

        if day.hotel is not None:
            try:
                if _enrich_hotel(day.hotel, city=city or itinerary.destination):
                    enriched_count += 1
            except Exception:
                pass

        for transport in day.transport:
            try:
                if _enrich_transport(transport, city=city or itinerary.destination):
                    enriched_count += 1
            except Exception:
                continue

    if enriched_count > 0:
        note = "Address, coordinate, or route estimate information was supplemented using AMap."
        if note not in itinerary.source_notes:
            itinerary.source_notes.append(note)

    return itinerary
