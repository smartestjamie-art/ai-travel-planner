from pathlib import Path
import sys


# Allow test files to import modules under backend/app directly.
CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import app.rag.retriever as retriever  # noqa: E402


def test_retrieve_travel_guide_formats_chunks_as_text(monkeypatch) -> None:
    """Test that the retriever formats retrieval results as directly citable text snippets."""

    def fake_search_guide_chunks_with_usage(
        query: str, top_k: int = 3
    ) -> tuple[list[dict[str, str]], dict[str, int]]:
        assert query == "Dali Old Town food"
        assert top_k == 6
        return [
            {
                "source": "dali_guide.md",
                "title": "Dali Old Town",
                "text": "Dali Old Town is great for a slow-paced stroll and photos.",
            }
        ], {"prompt_tokens": 0, "completion_tokens": 0}

    monkeypatch.setattr(retriever, "search_guide_chunks_with_usage", fake_search_guide_chunks_with_usage)
    monkeypatch.setattr(
        retriever,
        "rerank_guide_chunks",
        lambda query, matched_chunks, top_k, destination=None: (
            matched_chunks[:top_k],
            {"prompt_tokens": 0, "completion_tokens": 0},
        ),
    )

    results, _, _ = retriever.retrieve_travel_guide("Dali Old Town food", top_k=2)

    assert results == ["[Source: dali_guide.md | Title: Dali Old Town]\nDali Old Town is great for a slow-paced stroll and photos."]


def test_retrieve_travel_guide_returns_empty_when_no_chunks(monkeypatch) -> None:
    """Test that an empty list is returned when no chunks are retrieved."""

    def fake_search_guide_chunks_with_usage(
        query: str, top_k: int = 3
    ) -> tuple[list[dict[str, str]], dict[str, int]]:
        assert query == "Mars desert polar expedition"
        assert top_k == 6
        return [], {"prompt_tokens": 0, "completion_tokens": 0}

    monkeypatch.setattr(retriever, "search_guide_chunks_with_usage", fake_search_guide_chunks_with_usage)
    monkeypatch.setattr(
        retriever,
        "rerank_guide_chunks",
        lambda query, matched_chunks, top_k, destination=None: (
            matched_chunks[:top_k],
            {"prompt_tokens": 0, "completion_tokens": 0},
        ),
    )

    results, _, _ = retriever.retrieve_travel_guide("Mars desert polar expedition", top_k=2)

    assert results == []
