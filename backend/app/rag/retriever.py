import logging

from app.config import REDIS_RAG_TTL_SECONDS
from app.rag.vector_db import search_guide_chunks
from app.services.cache_service import get_cached_json, set_cached_json


logger = logging.getLogger(__name__)


def _normalize_cache_text(value: str) -> str:
    """把检索 query 做简单标准化，避免大小写和空格造成重复 key。"""
    return " ".join(value.strip().lower().split())


def retrieve_travel_guide(query: str, top_k: int = 3) -> list[str]:
    """返回最相关的攻略片段，供上层组装上下文。"""
    cache_key = f"rag:guide:{_normalize_cache_text(query)}:{top_k}"
    cached_value = get_cached_json(cache_key)
    if cached_value is not None:
        logger.info("rag cache hit: query=%s top_k=%s", query, top_k)
        return [str(item) for item in cached_value]
    logger.info("rag cache miss: query=%s top_k=%s", query, top_k)

    matched_chunks = search_guide_chunks(query=query, top_k=top_k)

    results: list[str] = []
    for chunk in matched_chunks:
        results.append(
            f"[来源: {chunk['source']} | 标题: {chunk['title']}]\n{chunk['text']}"
        )

    set_cached_json(cache_key, results, expire_seconds=REDIS_RAG_TTL_SECONDS)
    return results
