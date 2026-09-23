from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib import request


CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Read generated_trip.json and call the real /trip/edit endpoint."
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
        "--instruction",
        default="Make day two more relaxed, don't pack the schedule too full",
        help="User edit instruction",
    )
    parser.add_argument(
        "--edit-scope",
        default="day_2",
        help="Edit scope, e.g. day_2",
    )
    return parser


def load_generated_trip(input_file: str) -> dict:
    """Read generated_trip.json."""
    file_path = Path(input_file)
    with file_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def build_edit_payload(
    itinerary: dict,
    instruction: str,
    edit_scope: str,
) -> dict:
    """Assemble the request body for /trip/edit."""
    return {
        "trip_id": itinerary["trip_id"],
        "current_itinerary": itinerary,
        "user_instruction": instruction,
        "edit_scope": edit_scope,
        "preserve_constraints": ["Preserve the budget structure"],
    }


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


def print_day_summary(title: str, itinerary: dict, day_index: int) -> None:
    """Print a brief summary of a given day."""
    print(title)
    matched_day = next(
        (day for day in itinerary.get("days", []) if day.get("day_index") == day_index),
        None,
    )
    if matched_day is None:
        print(f"day_{day_index} not found")
        print()
        return

    print(f"theme: {matched_day.get('theme')}")
    if matched_day.get("spots"):
        print(f"spot: {matched_day['spots'][0].get('name')}")
        print(f"spot_description: {matched_day['spots'][0].get('description')}")
    if matched_day.get("notes"):
        print(f"notes: {matched_day['notes']}")
    print()


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    original_itinerary = load_generated_trip(args.input_file)
    payload = build_edit_payload(
        itinerary=original_itinerary,
        instruction=args.instruction,
        edit_scope=args.edit_scope,
    )

    print("=== Edit request ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print()

    response = post_json(f"{args.base_url}/trip/edit", payload)

    print("=== Itinerary after editing ===")
    print(json.dumps(response, ensure_ascii=False, indent=2))
    print()

    target_day = 2
    print_day_summary("=== day_2 before editing ===", original_itinerary, target_day)
    print_day_summary("=== day_2 after editing ===", response, target_day)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
