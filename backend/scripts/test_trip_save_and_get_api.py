from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib import request
from urllib.parse import quote


CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Read generated_trip.json and test the real /trip/save and /trip/{trip_id} endpoints."
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="FastAPI service address",
    )
    parser.add_argument(
        "--input-file",
        default="generated_trip.json",
        help="Itinerary file previously saved via /trip/generate",
    )
    parser.add_argument(
        "--user-id",
        default="user_001",
        help="User ID to use when saving",
    )
    return parser


def load_generated_trip(input_file: str) -> dict:
    """Read generated_trip.json."""
    file_path = Path(input_file)
    with file_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def post_json(url: str, payload: dict) -> dict:
    """Send a JSON POST request and return the JSON response."""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req) as response:
        response_text = response.read().decode("utf-8")
        return json.loads(response_text)


def get_json(url: str) -> dict:
    """Send a GET request and return the JSON response."""
    req = request.Request(url=url, method="GET")
    with request.urlopen(req) as response:
        response_text = response.read().decode("utf-8")
        return json.loads(response_text)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    itinerary = load_generated_trip(args.input_file)
    trip_id = itinerary["trip_id"]

    save_payload = {
        "trip_id": trip_id,
        "itinerary": itinerary,
        "user_id": args.user_id,
    }

    print("=== Save Request ===")
    print(json.dumps(save_payload, ensure_ascii=False, indent=2))
    print()

    save_response = post_json(f"{args.base_url}/trip/save", save_payload)

    print("=== Save Response ===")
    print(json.dumps(save_response, ensure_ascii=False, indent=2))
    print()

    encoded_trip_id = quote(trip_id, safe="")
    get_response = get_json(f"{args.base_url}/trip/{encoded_trip_id}")

    print("=== Query Response ===")
    print(json.dumps(get_response, ensure_ascii=False, indent=2))
    print()

    print("=== Quick Check ===")
    print(f"saved_trip_id: {save_response.get('trip_id')}")
    print(f"queried_trip_id: {get_response.get('trip_id')}")
    itinerary_data = get_response.get("itinerary", {})
    print(f"destination: {itinerary_data.get('destination')}")
    print(f"days_count: {len(itinerary_data.get('days', []))}")
    print(f"summary: {itinerary_data.get('summary')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
