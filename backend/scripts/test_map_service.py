from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.map_service import estimate_route, geocode_address, search_places  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Manually test the Amap map service.")
    parser.add_argument("--keyword", default="Dali Ancient City", help="POI search keyword")
    parser.add_argument("--city", default="Dali", help="City to search in")
    parser.add_argument("--address", default="Dali Ancient City, Dali Bai Autonomous Prefecture, Yunnan Province", help="Address to geocode")
    args = parser.parse_args()

    print("=== POI Search ===")
    places = search_places(keyword=args.keyword, city=args.city)
    print(json.dumps(places, ensure_ascii=False, indent=2))

    print("\n=== Geocoding ===")
    geocode = geocode_address(address=args.address, city=args.city)
    print(json.dumps(geocode, ensure_ascii=False, indent=2))

    if geocode and geocode.get("latitude") is not None and geocode.get("longitude") is not None:
        print("\n=== Route Estimate (same-point example) ===")
        route = estimate_route(
            origin_longitude=geocode["longitude"],
            origin_latitude=geocode["latitude"],
            destination_longitude=geocode["longitude"],
            destination_latitude=geocode["latitude"],
        )
        print(json.dumps(route, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
