import hashlib
import json
import logging
import re

import httpx

from app.config import LLM_API_KEY, REDIS_RAG_TTL_SECONDS, REDIS_RERANK_TTL_SECONDS, RERANK_MODEL
from app.rag.vector_db import search_guide_chunks_with_usage
from app.services.cache_service import get_cached_json, set_cached_json


DASHSCOPE_RERANK_URL = "https://dashscope.aliyuncs.com/compatible-api/v1/reranks"


logger = logging.getLogger(__name__)


def _normalize_cache_text(value: str) -> str:
    """Normalize the search query in a simple way to avoid duplicate cache keys caused by case and whitespace differences."""
    return " ".join(value.strip().lower().split())


def _extract_query_keywords(query: str) -> list[str]:
    """Split the query into keywords used for lightweight rerank scoring."""
    raw_parts = re.split(r"[\s,，。；;、]+", query)
    return [part.strip() for part in raw_parts if part.strip()]


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _score_chunk_for_rerank(
    query: str,
    chunk: dict[str, str],
    destination: str | None = None,
) -> int:
    """Lightly score retrieved chunks based on query keywords."""
    title = chunk.get("title", "")
    text = chunk.get("text", "")
    source = chunk.get("source", "")
    combined_text = f"{title}\n{text}"
    reasons: list[str] = []

    score = 0
    for keyword in _extract_query_keywords(query):
        if keyword in title:
            score += 3
            reasons.append(f"title+3:{keyword}")
        if keyword in text:
            score += 1
            reasons.append(f"text+1:{keyword}")

    # Content at the very start of a document is usually low-information noise.
    if title == "Document start":
        score -= 8
        reasons.append("noise-8:document-start")

    # Itinerary-type chunks are better suited to "attractions / itinerary / recommendation" requests.
    if "Itinerary" in title and "(Agent Extraction Sample)" not in title:
        score += 4
        reasons.append("domain+4:itinerary-title")

    # "Classic itinerary reference" chunks tend to be overly comprehensive and dominate Top1, so down-weight them for non-itinerary queries.
    if "(Agent Extraction Sample)" in title:
        score -= 4
        reasons.append("domain-4:itinerary-reference-penalty")

    # "Destination overview" content is too generic to be the best candidate for specific queries (food, family, etc.).
    if "Destination Overview" in title:
        score -= 2
        reasons.append("domain-2:destination-intro-penalty")

    # Dining/budget chunks are usually not the best candidates for "sunset / photography / relaxed" style goals.
    if _contains_any(title, ["Food", "Budget"]) and not _contains_any(
        combined_text,
        ["sunset", "evening", "photo", "photography", "Erhai", "Shuanglang", "slow-paced", "relaxed"],
    ):
        score -= 3
        reasons.append("domain-3:dining-budget-weak-relevance")

    # Destination mismatch penalty: down-weight a chunk whose source doesn't match the query's destination.
    if destination:
        chunk_lower = f"{source} {title} {text}".lower()
        if destination.lower() not in chunk_lower:
            score -= 5
            reasons.append(f"dest-5:non-{destination}-chunk")

    chunk["rerank_reasons"] = reasons
    return score


_NOISE_TITLES = {"Document start"}


def _extract_rerank_token_usage(response_data: dict) -> tuple[dict[str, int], bool]:
    """Only read the official usage returned by the API; do not estimate locally when usage is absent."""
    usage = response_data.get("usage") or response_data.get("output", {}).get("usage") or {}
    prompt_tokens = (
        usage.get("prompt_tokens")
        or usage.get("input_tokens")
        or usage.get("input_token_count")
        or 0
    )
    completion_tokens = (
        usage.get("completion_tokens")
        or usage.get("output_tokens")
        or usage.get("output_token_count")
        or 0
    )
    total_tokens = usage.get("total_tokens") or usage.get("total_token_count") or 0

    if not prompt_tokens and not completion_tokens and total_tokens:
        prompt_tokens = total_tokens

    if prompt_tokens or completion_tokens:
        return {
            "prompt_tokens": int(prompt_tokens),
            "completion_tokens": int(completion_tokens),
        }, True

    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
    }, False


def _rerank_with_dashscope(
    query: str,
    chunks: list[dict[str, str]],
    top_k: int,
) -> tuple[list[tuple[float, int]] | None, dict[str, int]]:
    """Call the DashScope qwen3-rerank model to perform semantic reranking. Returns (scored, token_usage)."""
    empty_usage = {"prompt_tokens": 0, "completion_tokens": 0}
    if not LLM_API_KEY or not chunks:
        print("[rerank] skip qwen3-rerank: missing LLM_API_KEY or empty chunks")
        return None, empty_usage

    # Filter out known noise chunks to avoid wasting rerank slots
    filtered = [
        (i, chunk) for i, chunk in enumerate(chunks)
        if chunk.get("title", "") not in _NOISE_TITLES
    ]
    if not filtered:
        print("[rerank] skip qwen3-rerank: all chunks are noise")
        return None, empty_usage

    original_indices = [i for i, _ in filtered]
    clean_chunks = [chunk for _, chunk in filtered]

    documents = [
        f"{chunk.get('title', '')}\n{chunk.get('text', '')}"
        for chunk in clean_chunks
    ]
    instruct = (
        "You are a travel-guide retrieval expert. "
        "Given a trip-planning query, retrieve the candidate document passage that is most specific, most detailed, "
        "and most directly answers the user's question. "
        "Prefer passages that name concrete attractions, activities, or practical information, "
        "and avoid low-information passages such as generic destination overviews or document openings."
    )
    payload = {
        "model": RERANK_MODEL,
        "documents": documents,
        "query": query,
        "top_n": min(top_k, len(documents)),
        "instruct": instruct,
    }

    try:
        print(
            f"[rerank] calling qwen3-rerank: query={query}, "
            f"candidate_count={len(clean_chunks)}, top_k={top_k}"
        )
        with httpx.Client(timeout=30) as client:
            response = client.post(
                DASHSCOPE_RERANK_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {LLM_API_KEY}",
                    "Content-Type": "application/json",
                },
            )
            print(f"[rerank] qwen3-rerank status_code={response.status_code}")
            if response.status_code != 200:
                print(f"[rerank] qwen3-rerank response preview={response.text[:500]}")
                logger.warning(
                    "dashscope rerank HTTP %d: %s",
                    response.status_code,
                    response.text[:500],
                )
                return None, empty_usage
            data = response.json()

        # Only extract the official token usage returned by the API; keep it at 0 when usage is absent, without estimating.
        token_usage, has_official_usage = _extract_rerank_token_usage(data)
        usage_source = "api" if has_official_usage else "none"
        print(
            "[rerank] qwen3-rerank token: "
            f"prompt={token_usage['prompt_tokens']}, "
            f"completion={token_usage['completion_tokens']}, "
            f"source={usage_source}"
        )
        if not has_official_usage:
            print(
                "[rerank] qwen3-rerank response has no official usage field; "
                "precise token count is unavailable from this response."
            )
        if token_usage["prompt_tokens"] or token_usage["completion_tokens"]:
            logger.info(
                "dashscope rerank token: prompt=%d, completion=%d",
                token_usage["prompt_tokens"],
                token_usage["completion_tokens"],
            )

        # Support both response formats
        results = data.get("output", {}).get("results", []) or data.get("results", [])
        if not results:
            print(
                "[rerank] qwen3-rerank empty results, "
                f"response preview={json.dumps(data, ensure_ascii=False)[:500]}"
            )
            logger.warning("dashscope rerank empty results, response: %s", json.dumps(data, ensure_ascii=False)[:500])
            return None, token_usage

        scored = [
            (float(item.get("relevance_score", 0)), original_indices[int(item.get("index", 0))])
            for item in results
            if int(item.get("index", 0)) < len(original_indices)
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        print(f"[rerank] qwen3-rerank success: results={len(scored)}")
        logger.info("dashscope rerank: query=%s, results=%d", query, len(scored))
        return scored, token_usage

    except Exception as exc:
        print(f"[rerank] qwen3-rerank failed: {type(exc).__name__}: {exc}")
        logger.warning("dashscope rerank failed: %s, falling back to rule-based", exc)
        return None, empty_usage


def _build_rerank_cache_key(query: str, chunks: list[dict[str, str]]) -> str:
    """Generate the rerank cache key from the query and chunk content."""
    """
query = " Dali natural scenery "; after _normalize_cache_text processing this becomes "dali natural scenery".

chunks = [{"source": "dali_guide.md", "title": "Cangshan"}, {"source": "dali_guide.md", "title": "Erhai Lake"}]

content_fingerprint = "dali_guide.md:Cangshan|dali_guide.md:Erhai Lake"

chunks_hash = hashlib.md5("dali_guide.md:Cangshan|dali_guide.md:Erhai Lake".encode()).hexdigest()[:12] → suppose this yields "a1b2c3d4e5f6"

Final cache key: "rerank:dali natural scenery:a1b2c3d4e5f6"
    """
    normalized_query = _normalize_cache_text(query)
    content_fingerprint = "|".join(
        f"{c.get('source', '')}:{c.get('title', '')}" for c in chunks
    )
    chunks_hash = hashlib.md5(content_fingerprint.encode()).hexdigest()[:12]
    return f"rerank:{normalized_query}:{chunks_hash}"


def rerank_guide_chunks(
    query: str,
    matched_chunks: list[dict[str, str]],
    top_k: int,
    destination: str | None = None,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Rerank retrieval candidates, preferring the cross-encoder with a fallback to rule-based scoring. Returns (chunks, rerank_token_usage)."""
    empty_usage = {"prompt_tokens": 0, "completion_tokens": 0}

    # Try to read the rerank result from the cache
    cache_key = _build_rerank_cache_key(query, matched_chunks)
    cached = get_cached_json(cache_key)
    if cached is not None:
        logger.info("rerank cache hit: query=%s", query)
        reranked: list[dict[str, str]] = []
        for item in cached:
            idx = item["i"]
            if 0 <= idx < len(matched_chunks):
                enriched = dict(matched_chunks[idx])
                enriched["rerank_score"] = item["s"]
                enriched["rerank_reasons"] = [f"cross-encoder:{item['s']:.4f}"]
                reranked.append(enriched)
        return reranked[:top_k], empty_usage
    logger.info("rerank cache miss: query=%s", query)

    # Prefer the DashScope cross-encoder rerank
    dashscope_results, rerank_token_usage = _rerank_with_dashscope(query, matched_chunks, top_k)
    if dashscope_results:
        print("[rerank] using qwen3-rerank results")
        # Write to cache: store only index and score, not the duplicated text
        cache_value = [
            {"i": idx, "s": round(score, 4)}
            for score, idx in dashscope_results
        ]
        set_cached_json(cache_key, cache_value, expire_seconds=REDIS_RERANK_TTL_SECONDS)

        reranked = []
        for score, original_index in dashscope_results:
            if 0 <= original_index < len(matched_chunks):
                enriched_chunk = dict(matched_chunks[original_index])
                enriched_chunk["rerank_score"] = round(score, 4)
                enriched_chunk["rerank_reasons"] = [f"cross-encoder:{score:.4f}"]
                reranked.append(enriched_chunk)
        return reranked[:top_k], rerank_token_usage

    # Fall back to rule-based rerank
    print("[rerank] qwen3-rerank unavailable, using rule-based rerank")
    logger.info("rerank_guide_chunks: using rule-based rerank")
    scored_chunks: list[tuple[int, int, dict[str, str]]] = []
    for index, chunk in enumerate(matched_chunks):
        enriched_chunk = dict(chunk)
        score = _score_chunk_for_rerank(query, enriched_chunk, destination=destination)
        enriched_chunk["rerank_score"] = score
        scored_chunks.append((score, -index, enriched_chunk))

    scored_chunks.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [chunk for _, _, chunk in scored_chunks[:top_k]], empty_usage


def retrieve_travel_guide_chunks(
    query: str, top_k: int = 3, destination: str | None = None
) -> tuple[list[dict[str, str]], dict[str, int], dict[str, int]]:
    """Return raw guide chunks with lightweight rerank applied. Returns (chunks, rerank_usage, embedding_usage)."""
    candidate_k = max(top_k * 2, 6)
    matched_chunks, embedding_usage = search_guide_chunks_with_usage(query=query, top_k=candidate_k)
    reranked_chunks, rerank_usage = rerank_guide_chunks(
        query=query, matched_chunks=matched_chunks, top_k=top_k, destination=destination
    )
    return reranked_chunks, rerank_usage, embedding_usage


def retrieve_travel_guide(
    query: str, top_k: int = 3
) -> tuple[list[str], dict[str, int], dict[str, int]]:
    """Return the most relevant guide chunks. Returns (texts, rerank_usage, embedding_usage)."""
    empty_usage = {"prompt_tokens": 0, "completion_tokens": 0}
    cache_key = f"rag:guide:{_normalize_cache_text(query)}:{top_k}"
    cached_value = get_cached_json(cache_key)
    if cached_value is not None:
        logger.info("rag cache hit: query=%s top_k=%s", query, top_k)
        return [str(item) for item in cached_value], empty_usage, empty_usage
    logger.info("rag cache miss: query=%s top_k=%s", query, top_k)

    matched_chunks, rerank_usage, embedding_usage = retrieve_travel_guide_chunks(query=query, top_k=top_k)

    results: list[str] = []
    for chunk in matched_chunks:
        results.append(
            f"[Source: {chunk['source']} | Title: {chunk['title']}]\n{chunk['text']}"
        )

    set_cached_json(cache_key, results, expire_seconds=REDIS_RAG_TTL_SECONDS)
    return results, rerank_usage, embedding_usage
