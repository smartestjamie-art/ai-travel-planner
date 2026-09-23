from pathlib import Path
import sys

from fastapi.testclient import TestClient


# Allow test files to directly import modules under backend/app.
CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.main import app  # noqa: E402
import app.api.routes.export as export_route  # noqa: E402
import app.services.trip_service as trip_service  # noqa: E402

client = TestClient(app)


def build_generate_payload() -> dict:
    """Build a valid request body for generating a trip itinerary."""
    return {
        "destination": "Dali",
        "start_date": "2026-04-10",
        "end_date": "2026-04-12",
        "travelers": 2,
        "budget": 3200,
        "preferences": ["natural scenery", "photography", "food"],
        "pace": "relaxed",
        "dietary_preferences": ["mild spice"],
        "hotel_level": "comfortable",
        "special_notes": "Don't want to wake up too early, and would like a spot suitable for watching the sunset",
    }


def test_generate_trip_returns_itinerary_successfully() -> None:
    """Test that POST /trip/generate returns a structured itinerary."""
    response = client.post("/trip/generate", json=build_generate_payload())

    assert response.status_code == 200
    data = response.json()
    assert data["destination"] == "Dali"
    assert "trip_id" in data
    assert "summary" in data
    assert "days" in data
    assert isinstance(data["days"], list)
    assert len(data["days"]) == 3
    assert "budget_breakdown" in data
    assert data["budget_breakdown"]["total"] >= 0


def test_generate_trip_rejects_invalid_request() -> None:
    """Test that an invalid request is rejected by FastAPI/Pydantic."""
    payload = build_generate_payload()
    payload["travelers"] = 0

    response = client.post("/trip/generate", json=payload)

    assert response.status_code == 422


def test_root_endpoint_returns_running_message() -> None:
    """Test that the root path / returns the service startup message."""
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "Trip Planner Demo backend is running."}


def test_health_endpoint_returns_ok_status() -> None:
    """Test that /health returns the health check result."""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_edit_trip_returns_updated_itinerary_successfully(monkeypatch) -> None:
    """Test that POST /trip/edit returns the updated itinerary."""
    monkeypatch.setattr(trip_service, "generate_day_edit_draft", lambda request, target_day: (None, {"prompt_tokens": 0, "completion_tokens": 0}))

    generated_response = client.post("/trip/generate", json=build_generate_payload())
    generated_itinerary = generated_response.json()

    edit_payload = {
        "trip_id": generated_itinerary["trip_id"],
        "current_itinerary": generated_itinerary,
        "user_instruction": "Make day 2 more relaxed",
        "edit_scope": "day_2",
        "preserve_constraints": ["keep the budget structure"],
    }

    response = client.post("/trip/edit", json=edit_payload)

    assert response.status_code == 200
    data = response.json()
    assert data["trip_id"] == generated_itinerary["trip_id"]
    assert data["days"][1]["theme"].endswith("(adjusted to be more relaxed)")


def test_edit_trip_rejects_invalid_request() -> None:
    """Test that an invalid edit request is rejected by FastAPI/Pydantic."""
    response = client.post(
        "/trip/edit",
        json={
            "trip_id": "trip_demo",
            "user_instruction": "Make day 2 more relaxed",
        },
    )

    assert response.status_code == 422


def test_save_trip_returns_trip_id_successfully() -> None:
    """Test that POST /trip/save returns a successful save result."""
    generated_response = client.post("/trip/generate", json=build_generate_payload())
    generated_itinerary = generated_response.json()

    response = client.post(
        "/trip/save",
        json={
            "trip_id": generated_itinerary["trip_id"],
            "itinerary": generated_itinerary,
            "user_id": "user_001",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["trip_id"] == generated_itinerary["trip_id"]
    assert data["message"] == "Trip itinerary saved successfully."


def test_get_trip_detail_returns_saved_itinerary() -> None:
    """Test that GET /trip/{trip_id} returns the saved itinerary."""
    generated_response = client.post("/trip/generate", json=build_generate_payload())
    generated_itinerary = generated_response.json()

    client.post(
        "/trip/save",
        json={
            "trip_id": generated_itinerary["trip_id"],
            "itinerary": generated_itinerary,
            "user_id": "user_001",
        },
    )

    response = client.get(f"/trip/{generated_itinerary['trip_id']}")

    assert response.status_code == 200
    data = response.json()
    assert data["trip_id"] == generated_itinerary["trip_id"]
    assert data["itinerary"]["destination"] == "Dali"


def test_get_trip_detail_returns_404_for_missing_trip() -> None:
    """Test that querying a nonexistent trip_id returns 404."""
    response = client.get("/trip/trip_not_exists")

    assert response.status_code == 404


def test_list_trips_returns_saved_trip_summaries() -> None:
    """Test that GET /trip returns a summary list of saved trips."""
    generated_response = client.post("/trip/generate", json=build_generate_payload())
    generated_itinerary = generated_response.json()

    client.post(
        "/trip/save",
        json={
            "trip_id": generated_itinerary["trip_id"],
            "itinerary": generated_itinerary,
            "user_id": "user_001",
        },
    )

    response = client.get("/trip")

    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "items" in data
    assert isinstance(data["items"], list)
    assert any(item["trip_id"] == generated_itinerary["trip_id"] for item in data["items"])


def test_export_trip_markdown_returns_markdown_text() -> None:
    """Test that GET /export/{trip_id}/markdown can export Markdown text."""
    generated_response = client.post("/trip/generate", json=build_generate_payload())
    generated_itinerary = generated_response.json()

    client.post(
        "/trip/save",
        json={
            "trip_id": generated_itinerary["trip_id"],
            "itinerary": generated_itinerary,
            "user_id": "user_001",
        },
    )

    response = client.get(f"/export/{generated_itinerary['trip_id']}/markdown")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert generated_itinerary["destination"] in response.text
    assert generated_itinerary["summary"] in response.text


def test_export_trip_pdf_returns_pdf_bytes(monkeypatch) -> None:
    """Test that GET /export/{trip_id}/pdf can export a PDF."""
    generated_response = client.post("/trip/generate", json=build_generate_payload())
    generated_itinerary = generated_response.json()

    client.post(
        "/trip/save",
        json={
            "trip_id": generated_itinerary["trip_id"],
            "itinerary": generated_itinerary,
            "user_id": "user_001",
        },
    )

    monkeypatch.setattr(
        export_route,
        "itinerary_to_pdf_bytes",
        lambda trip_detail: b"%PDF-1.4\n%mock pdf\n",
    )

    response = client.get(f"/export/{generated_itinerary['trip_id']}/pdf")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.content.startswith(b"%PDF")


def test_generate_trip_response_includes_rag_context() -> None:
    """Test that the generate endpoint's response includes minimal RAG traces."""
    response = client.post("/trip/generate", json=build_generate_payload())

    assert response.status_code == 200
    data = response.json()
    joined_notes = "\n".join(data["source_notes"])

    assert len(data["source_notes"]) >= 2
    assert "Dali" in joined_notes
