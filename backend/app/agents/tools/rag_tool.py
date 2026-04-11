from app.rag.retriever import retrieve_travel_guide


# rag_tool.py 自己不直接检索，
# 它只负责把“旅行规划语义”转成“检索查询”。
def _build_destination_query(
    destination: str,
    preferences: list[str] | None = None,
    pace: str | None = None,
    special_notes: str | None = None,
) -> str:
    """把目的地、偏好、节奏和备注拼成更贴近用户需求的检索词。"""
    parts: list[str] = [destination]

    if preferences:
        parts.extend(preferences)

    if pace:
        parts.append(pace)

    if special_notes:
        parts.append(special_notes)

    # 为向量检索补一些更稳定的旅游语义词，帮助召回景点、行程、攻略等片段。
    parts.extend(["景点", "行程", "攻略", "推荐"])

    return " ".join(part for part in parts if part).strip()


def get_destination_guide_context(
    destination: str,
    preferences: list[str] | None = None,
    pace: str | None = None,
    special_notes: str | None = None,
    top_k: int = 5,
) -> list[str]:
    """根据目的地和偏好返回本地攻略里的相关片段。"""
    query = _build_destination_query(
        destination=destination,
        preferences=preferences,
        pace=pace,
        special_notes=special_notes,
    )
    return retrieve_travel_guide(query=query, top_k=top_k)
