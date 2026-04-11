from app.rag.vector_db import search_guide_chunks


def retrieve_travel_guide(query: str, top_k: int = 3) -> list[str]:
    """返回最相关的攻略片段，供上层组装上下文。"""
    matched_chunks = search_guide_chunks(query=query, top_k=top_k)

    results: list[str] = []
    for chunk in matched_chunks:
        results.append(
            f"[来源: {chunk['source']} | 标题: {chunk['title']}]\n{chunk['text']}"
        )
    return results
