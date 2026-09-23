import logging

from app.config import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MAX_RETRIES,
    LLM_MODEL,
    LLM_TIMEOUT_SECONDS,
)
from app.rag.retriever import retrieve_travel_guide


logger = logging.getLogger(__name__)


# rag_tool.py itself does not perform retrieval directly,
# it is only responsible for turning "travel planning intent" into a "retrieval query".
def _append_unique(parts: list[str], value: str) -> None:
    normalized = value.strip()
    if not normalized:
        return
    if normalized not in parts:
        parts.append(normalized)


def _extract_note_keywords(special_notes: str | None, destination: str | None = None) -> list[str]:
    """Extract keywords better suited for retrieval from the user's notes, rather than concatenating the whole sentence directly."""
    if not special_notes:
        return []

    keywords: list[str] = []
    note = special_notes.strip()

    # Format: (trigger words, destination filter, output keywords)
    # Destination of None means generic, not limited to a specific destination
    rule_keywords = [
        (("sunset", "evening"), "Dali", ["sunset", "evening", "Erhai Lake", "Shuanglang"]),
        (("sunrise", "early morning"), "Dali", ["sunrise", "Caicun", "Longkan"]),
        (("photography", "photo-worthy", "photo shoot"), None, ["photography", "photo shoot", "photo-worthy"]),
        (("food", "snacks", "eating"), None, ["food", "snacks"]),
        (("relaxed", "slow-paced", "leisurely"), None, ["relaxed", "slow-paced", "leisurely"]),
        (("don't want to get up too early", "sleep in"), None, ["relaxed", "slow-paced"]),
        (("ancient town",), "Dali", ["ancient town", "Dali Old Town", "Xizhou Ancient Town"]),
        (("ancient town",), "Xi'an", ["ancient town", "Muslim Quarter"]),
        (("ancient town",), "Xiamen", ["ancient town", "Gulangyu", "Zengcuoan"]),
        (("cycling",), "Dali", ["cycling", "Erhai Lake Eco-Corridor"]),
        (("cycling",), "Xiamen", ["cycling", "Ring Island Road"]),
        (("panda", "giant panda"), "Chengdu", ["giant panda", "panda"]),
        (("diving",), "Sanya", ["diving", "Wuzhizhou Island"]),
        (("seafood",), "Sanya", ["seafood", "First Market"]),
    ]

    for triggers, required_dest, values in rule_keywords:
        if required_dest and destination and required_dest not in destination:
            continue
        if any(trigger in note for trigger in triggers):
            for value in values:
                _append_unique(keywords, value)

    return keywords


def _build_chat_llm():
    """Create a ChatOpenAI instance, used for query rewriting."""
    if not LLM_API_KEY:
        return None
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        return None
    return ChatOpenAI(
        model=LLM_MODEL,
        temperature=0.2,
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL or None,
        timeout=LLM_TIMEOUT_SECONDS,
        max_retries=LLM_MAX_RETRIES,
    )


def _extract_token_usage(response) -> dict[str, int]:
    """Extract token usage from a LangChain AIMessage."""
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    metadata = getattr(response, "response_metadata", None) or {}
    token_usage = metadata.get("token_usage", {})
    if token_usage:
        usage["prompt_tokens"] = token_usage.get("prompt_tokens", 0)
        usage["completion_tokens"] = token_usage.get("completion_tokens", 0)
    return usage


def llm_rewrite_query(
    destination: str,
    preferences: list[str] | None = None,
    pace: str | None = None,
    special_notes: str | None = None,
) -> tuple[str | None, dict[str, int]]:
    """Use an LLM to rewrite the user's travel requirements into a query suitable for vector retrieval. Returns (query, token_usage)."""
    empty_usage = {"prompt_tokens": 0, "completion_tokens": 0}
    llm = _build_chat_llm()
    if llm is None:
        return None, empty_usage

    system_prompt = (
        "You are an expert at rewriting RAG retrieval queries. "
        "Your task is to rewrite the user's travel requirements into a combination of keywords suitable for vector retrieval. "
        "Output requirements: "
        "1. Output only the retrieval keywords, separated by spaces "
        "2. Do not output explanations, punctuation, or any extraneous text "
        "3. Keywords should be specific, preferring attraction names, activity types, and scene characteristics "
        "4. Include the destination city name"
    )

    parts = [f"Destination: {destination}"]
    if preferences:
        parts.append(f"Preferences: {', '.join(preferences)}")
    if pace:
        parts.append(f"Pace: {pace}")
    if special_notes:
        parts.append(f"Notes: {special_notes}")
    human_prompt = "\n".join(parts)

    try:
        response = llm.invoke([
            ("system", system_prompt),
            ("human", human_prompt),
        ])
        token_usage = _extract_token_usage(response)
        raw_text = getattr(response, "content", "")
        if isinstance(raw_text, list):
            raw_text = "".join(
                item.get("text", "") if isinstance(item, dict) else str(item)
                for item in raw_text
            )
        query = raw_text.strip()
        if query:
            logger.info("llm_rewrite_query: input=%s -> output=%s", human_prompt, query)
            return query, token_usage
    except Exception:
        logger.warning("llm_rewrite_query failed, falling back to rule-based", exc_info=True)

    return None, empty_usage


def _rule_based_query(
    destination: str,
    preferences: list[str] | None = None,
    pace: str | None = None,
    special_notes: str | None = None,
) -> str:
    """Rule-based query rewrite, used as a fallback for LLM rewriting."""
    parts: list[str] = [destination]

    if preferences:
        for preference in preferences:
            _append_unique(parts, preference)

    if pace:
        _append_unique(parts, pace)

    for keyword in _extract_note_keywords(special_notes, destination=destination):
        _append_unique(parts, keyword)

    for stable_term in ["attractions", "itinerary", "travel guide", "recommendations"]:
        _append_unique(parts, stable_term)

    return " ".join(part for part in parts if part).strip()


def build_destination_query(
    destination: str,
    preferences: list[str] | None = None,
    pace: str | None = None,
    special_notes: str | None = None,
) -> tuple[str, dict[str, int]]:
    """Rewrite the destination, preferences, pace, and notes into a query better suited for retrieval. Returns (query, token_usage)."""
    llm_query, token_usage = llm_rewrite_query(
        destination=destination,
        preferences=preferences,
        pace=pace,
        special_notes=special_notes,
    )
    if llm_query:
        return llm_query, token_usage

    logger.info("build_destination_query: LLM rewrite unavailable, using rule-based")
    return _rule_based_query(
        destination=destination,
        preferences=preferences,
        pace=pace,
        special_notes=special_notes,
    ), {"prompt_tokens": 0, "completion_tokens": 0}


def _build_destination_query(
    destination: str,
    preferences: list[str] | None = None,
    pace: str | None = None,
    special_notes: str | None = None,
) -> tuple[str, dict[str, int]]:
    """Kept for backward compatibility with old callers; internally delegates to the public query builder."""
    return build_destination_query(
        destination=destination,
        preferences=preferences,
        pace=pace,
        special_notes=special_notes,
    )


def get_destination_guide_context(
    destination: str,
    preferences: list[str] | None = None,
    pace: str | None = None,
    special_notes: str | None = None,
    top_k: int = 5,
) -> tuple[list[str], dict[str, int], dict[str, int], dict[str, int]]:
    """Return local travel guide snippets based on the destination and preferences. Returns (contexts, rewrite_usage, rerank_usage, embedding_usage)."""
    query, rewrite_usage = build_destination_query(
        destination=destination,
        preferences=preferences,
        pace=pace,
        special_notes=special_notes,
    )
    contexts, rerank_usage, embedding_usage = retrieve_travel_guide(query=query, top_k=top_k)
    return contexts, rewrite_usage, rerank_usage, embedding_usage
