from __future__ import annotations

from datetime import date as DateType, timedelta

from app.agents.trip_planner_agent import (
    collect_trip_context,
    generate_day_edit_draft,
    generate_planner_draft,
)
from app.config import ENABLE_AMAP_ENRICHMENT
from app.models.schemas import (
    BudgetBreakdown,
    DayPlan,
    HotelItem,
    Itinerary,
    MealItem,
    SpotItem,
    TokenUsage,
    TransportItem,
    TripEditRequest,
    TripRequest,
)
from app.services.map_service import enrich_itinerary_with_map_data


TECHNICAL_TIP_KEYWORDS = (
    "LLM",
    "RAG",
    "LangChain",
    "Chroma",
    "demo",
    "test",
    "rule",
    "model",
    "source code",
    "trip_service",
)


def _clean_user_tips(tips: list[str], destination: str | None = None) -> list[str]:
    """Filter out internal implementation notes, keeping only tips the user can actually act on."""
    cleaned_tips: list[str] = []
    for tip in tips:
        normalized_tip = tip.strip()
        if not normalized_tip:
            continue
        if any(keyword in normalized_tip for keyword in TECHNICAL_TIP_KEYWORDS):
            continue
        if normalized_tip not in cleaned_tips:
            cleaned_tips.append(normalized_tip)

    if cleaned_tips:
        return cleaned_tips

    place_text = destination or "your destination"
    return [
        f"Check the day-of forecast for {place_text} and pack rain gear or a light jacket — mornings, evenings, and waterfront areas can feel cooler than expected.",
        "Old towns, eco-corridors, and cobblestone streets are best explored at a slow pace — wear comfortable, non-slip shoes.",
        "Head to popular attractions outside peak hours, and leave a comfortable buffer for photos, meals, and transport.",
    ]


def _build_demo_spot_names(destination: str, rag_contexts: list[str], day_count: int) -> list[str]:
    """Pick more realistic-sounding demo attraction names from the retrieved guide passages."""
    candidate_names: list[str] = []
    joined_context = "\n".join(rag_contexts)

    if "Dali Old Town" in joined_context:
        candidate_names.append("Dali Old Town")
    if "Xizhou Ancient Town" in joined_context:
        candidate_names.append("Xizhou Ancient Town")
    if "Three Pagodas of Chongsheng Temple" in joined_context:
        candidate_names.append("Three Pagodas of Chongsheng Temple")
    if "Erhai Lake Eco-Corridor" in joined_context:
        candidate_names.append("Erhai Lake Eco-Corridor")

    while len(candidate_names) < day_count:
        candidate_names.append(f"{destination} recommended spot {len(candidate_names) + 1}")

    return candidate_names[:day_count]


def _stable_bucket(text: str, modulo: int) -> int:
    """Derive a stable bucket value from text, used for deterministic price variation."""
    return sum(ord(char) for char in text) % modulo if modulo > 0 else 0


def _prorate_amounts(total: float, weights: list[float]) -> list[float]:
    """Split an amount by weights while keeping the split total equal to the original amount."""
    if not weights:
        return []

    safe_weights = [max(weight, 0.01) for weight in weights]
    total_cents = max(int(round(total * 100)), 0)
    weight_sum = sum(safe_weights)
    raw_cents = [(total_cents * weight) / weight_sum for weight in safe_weights]
    base_cents = [int(value) for value in raw_cents]
    remainder = total_cents - sum(base_cents)

    ranked_indexes = sorted(
        range(len(raw_cents)),
        key=lambda index: (raw_cents[index] - base_cents[index], -index),
        reverse=True,
    )
    for index in ranked_indexes[:remainder]:
        base_cents[index] += 1

    return [round(value / 100, 2) for value in base_cents]


def _estimate_ticket_cost(spot_name: str, description: str | None = None) -> float:
    """Estimate admission cost from attraction keywords, closer to a real itinerary than a fixed number."""
    text = f"{spot_name} {description or ''}".lower()
    bucket = _stable_bucket(text, 4)

    if any(keyword in text for keyword in ("old town", "ancient town", "park", "corridor", "village", "wetland", "district")):
        return [0.0, 20.0, 30.0, 40.0][bucket]
    if any(keyword in text for keyword in ("temple", "pagoda", "museum", "ruins", "resort")):
        return round(60.0 + (bucket * 18.0), 2)
    if any(keyword in text for keyword in ("cable car", "ropeway", "cruise", "show", "snow mountain")):
        return round(120.0 + (bucket * 28.0), 2)
    return round(35.0 + (bucket * 12.0), 2)


def _build_hotel_weights(day_count: int, start_date: DateType) -> list[float]:
    """Nudge nightly hotel cost up slightly for weekends and the last night of the trip."""
    weights: list[float] = []
    for index in range(day_count):
        current_date = start_date + timedelta(days=index)
        weight = 1.0
        if current_date.weekday() in (4, 5):
            weight += 0.18
        if index == day_count - 1:
            weight += 0.08
        if index % 2 == 1:
            weight += 0.05
        weights.append(weight)
    return weights


def _build_meal_weights(day_count: int, preferences: list[str]) -> list[float]:
    """Give users with a food preference a higher dining budget on some days."""
    foodie_bonus = 0.12 if "Food" in preferences else 0.0
    return [
        1.0 + foodie_bonus + (0.08 if index == day_count // 2 else 0.0) + ((index % 3) * 0.04)
        for index in range(day_count)
    ]


def _build_transport_weights(day_count: int, pace: str | None) -> list[float]:
    """Nudge the transport budget based on trip pace and the first/last day."""
    pace_bonus = 0.12 if pace == "Packed" else -0.04 if pace == "Relaxed" else 0.04
    return [
        1.0 + pace_bonus + (0.16 if index in (0, day_count - 1) else 0.0) + (index * 0.03)
        for index in range(day_count)
    ]


def _apply_route_based_transport_costs(itinerary: Itinerary) -> None:
    """When route distances are available, use them to refine transport cost and duration."""
    for day in itinerary.days:
        for transport in day.transport:
            if transport.estimated_minutes is not None:
                transport.duration = f"{transport.estimated_minutes} min"

            if transport.distance_km is None:
                continue

            mode = transport.mode or ""
            if "bus" in mode.lower() or "transit" in mode.lower():
                cost = max(2.0, 2.0 + (transport.distance_km * 0.25))
            elif "walk" in mode.lower():
                cost = 0.0
            elif "charter" in mode.lower() or "private car" in mode.lower():
                cost = 30.0 + (transport.distance_km * 3.8)
            else:
                cost = 10.0 + (transport.distance_km * 2.2)

            transport.estimated_cost = round(cost, 2)


def _refresh_budget_breakdown(itinerary: Itinerary, request_budget: float | None = None) -> Itinerary:
    """Recompute the budget summary from individual line items, so it doesn't look too templated."""
    _apply_route_based_transport_costs(itinerary)

    transport_total = round(
        sum(item.estimated_cost for day in itinerary.days for item in day.transport),
        2,
    )
    hotel_total = round(
        sum(day.hotel.estimated_cost for day in itinerary.days if day.hotel is not None),
        2,
    )
    meal_total = round(
        sum(item.estimated_cost for day in itinerary.days for item in day.meals),
        2,
    )
    ticket_total = round(
        sum(item.estimated_cost for day in itinerary.days for item in day.spots),
        2,
    )

    subtotal = transport_total + hotel_total + meal_total + ticket_total
    if request_budget is not None:
        other_total = round(max(0.0, min(request_budget * 0.12, request_budget - subtotal)), 2)
    else:
        other_total = round(max(subtotal * 0.06, 0.0), 2)

    total = round(subtotal + other_total, 2)
    itinerary.budget_breakdown = BudgetBreakdown(
        transport=transport_total,
        hotel=hotel_total,
        meals=meal_total,
        tickets=ticket_total,
        other=other_total,
        total=total,
    )
    itinerary.estimated_budget = total
    return itinerary


def _maybe_enrich_itinerary_with_map_data(
    itinerary: Itinerary,
    city: str | None = None,
    request_budget: float | None = None,
) -> Itinerary:
    """Optionally enrich with map data based on a feature flag, then refresh the budget summary."""
    if ENABLE_AMAP_ENRICHMENT:
        try:
            itinerary = enrich_itinerary_with_map_data(itinerary, city=city)
        except Exception:
            pass

    return _refresh_budget_breakdown(itinerary, request_budget=request_budget)


def generate_trip_itinerary(request: TripRequest) -> Itinerary:
    """Generate a complete itinerary using a more realistic budget-estimation approach."""
    day_count = (request.end_date - request.start_date).days + 1
    day_count = max(day_count, 1)

    rag_contexts, rewrite_usage, rerank_usage, embedding_usage = collect_trip_context(
        destination=request.destination,
        preferences=request.preferences,
        pace=request.pace,
        special_notes=request.special_notes,
    )
    llm_draft, planner_usage = generate_planner_draft(request, rag_contexts, day_count)

    token_usage = TokenUsage(
        rewrite_prompt_tokens=rewrite_usage.get("prompt_tokens", 0),
        rewrite_completion_tokens=rewrite_usage.get("completion_tokens", 0),
        embedding_prompt_tokens=embedding_usage.get("prompt_tokens", 0),
        embedding_completion_tokens=embedding_usage.get("completion_tokens", 0),
        planner_prompt_tokens=planner_usage.get("prompt_tokens", 0),
        planner_completion_tokens=planner_usage.get("completion_tokens", 0),
        rerank_prompt_tokens=rerank_usage.get("prompt_tokens", 0),
        rerank_completion_tokens=rerank_usage.get("completion_tokens", 0),
    )
    print(
        "[token_usage] Query Rewrite: "
        f"prompt={token_usage.rewrite_prompt_tokens}, "
        f"completion={token_usage.rewrite_completion_tokens}"
    )
    print(
        "[token_usage] Rerank: "
        f"prompt={token_usage.rerank_prompt_tokens}, "
        f"completion={token_usage.rerank_completion_tokens}"
    )
    print(
        "[token_usage] Query Embedding: "
        f"prompt={token_usage.embedding_prompt_tokens}, "
        f"completion={token_usage.embedding_completion_tokens}"
    )
    print(
        "[token_usage] Planner: "
        f"prompt={token_usage.planner_prompt_tokens}, "
        f"completion={token_usage.planner_completion_tokens}"
    )
    print(
        "[token_usage] Total: "
        f"prompt={token_usage.total_prompt_tokens}, "
        f"completion={token_usage.total_completion_tokens}, "
        f"all={token_usage.total_tokens}"
    )
    fallback_spot_names = _build_demo_spot_names(request.destination, rag_contexts, day_count)

    raw_days: list[dict[str, object]] = []
    ticket_costs: list[float] = []
    for index in range(day_count):
        day_number = index + 1
        current_date = request.start_date + timedelta(days=index)
        llm_day = None
        if llm_draft is not None:
            llm_day = next((item for item in llm_draft.days if item.day_index == day_number), None)

        spot_name = llm_day.spot_name if llm_day is not None else fallback_spot_names[index]
        theme = llm_day.theme if llm_day is not None else f"{request.destination} Day {day_number} — relaxed sightseeing"
        spot_description = (
            llm_day.spot_description
            if llm_day is not None
            else "Arranged based on the local guide and travel preferences — a relaxed half-day visit."
        )
        meal_name = llm_day.meal_name if llm_day is not None else f"{request.destination} local specialty meal {day_number}"
        meal_note = (
            llm_day.meal_notes
            if llm_day is not None
            else "A dining suggestion reserved based on your preferences and the local guide."
        )
        daily_note = (
            llm_day.daily_note
            if llm_day is not None
            else "Today is mostly relaxed sightseeing — adjust how long you linger based on your energy and the weather."
        )
        ticket_cost = _estimate_ticket_cost(spot_name, spot_description)

        raw_days.append(
            {
                "day_index": day_number,
                "date": current_date,
                "theme": theme,
                "spot_name": spot_name,
                "spot_description": spot_description,
                "meal_name": meal_name,
                "meal_note": meal_note,
                "daily_note": daily_note,
                "ticket_cost": ticket_cost,
            }
        )
        ticket_costs.append(ticket_cost)

    ticket_total = round(sum(ticket_costs), 2)
    target_total = request.budget * (
        0.78 if request.pace == "Relaxed" else 0.92 if request.pace == "Packed" else 0.85
    )
    other_budget = round(request.budget * (0.05 + min(day_count, 4) * 0.01), 2)
    allocatable_budget = max(target_total - ticket_total - other_budget, request.budget * 0.45)

    hotel_level = request.hotel_level or "Comfort"
    if "Luxury" in hotel_level:
        hotel_ratio = 0.62
    elif "Upscale" in hotel_level or "Premium" in hotel_level:
        hotel_ratio = 0.56
    elif "Budget" in hotel_level:
        hotel_ratio = 0.40
    else:
        hotel_ratio = 0.50

    meal_ratio = 0.28 if "Food" in request.preferences else 0.22
    transport_ratio = max(0.12, 1 - hotel_ratio - meal_ratio)
    ratio_sum = hotel_ratio + meal_ratio + transport_ratio

    hotel_total = allocatable_budget * hotel_ratio / ratio_sum
    meal_total = allocatable_budget * meal_ratio / ratio_sum
    transport_total = allocatable_budget * transport_ratio / ratio_sum

    daily_hotel_costs = _prorate_amounts(
        hotel_total,
        _build_hotel_weights(day_count, request.start_date),
    )
    daily_meal_costs = _prorate_amounts(
        meal_total,
        _build_meal_weights(day_count, request.preferences),
    )
    daily_transport_costs = _prorate_amounts(
        transport_total,
        _build_transport_weights(day_count, request.pace),
    )

    days: list[DayPlan] = []
    for index, raw_day in enumerate(raw_days):
        spot_name = str(raw_day["spot_name"])
        day_plan = DayPlan(
            day_index=int(raw_day["day_index"]),
            date=raw_day["date"],
            theme=str(raw_day["theme"]),
            spots=[
                SpotItem(
                    name=spot_name,
                    start_time="10:00",
                    end_time="12:00",
                    description=str(raw_day["spot_description"]),
                    estimated_cost=float(raw_day["ticket_cost"]),
                    location=request.destination,
                )
            ],
            meals=[
                MealItem(
                    name=str(raw_day["meal_name"]),
                    meal_type="lunch",
                    estimated_cost=daily_meal_costs[index],
                    notes=str(raw_day["meal_note"]),
                )
            ],
            hotel=HotelItem(
                name=f"{request.destination} {hotel_level} stay {index + 1}",
                level=hotel_level,
                estimated_cost=daily_hotel_costs[index],
                location=f"{request.destination} city center",
            ),
            transport=[
                TransportItem(
                    mode="Taxi",
                    from_place=f"{request.destination} starting point",
                    to_place=spot_name,
                    estimated_cost=daily_transport_costs[index],
                    duration="30 min",
                )
            ],
            notes=[
                f"Current travel pace: {request.pace or 'Moderate'}",
                str(raw_day["daily_note"]),
            ],
        )
        days.append(day_plan)

    preference_text = ", ".join(request.preferences) if request.preferences else "a general travel experience"
    source_notes = [
        "Itinerary is assembled by trip_service.py and can optionally use LangChain structured output.",
    ]
    source_notes.extend(rag_contexts[:2])

    tips = (
        llm_draft.tips
        if llm_draft is not None and llm_draft.tips
        else [
            f"Check the day-of forecast for {request.destination} and pack rain gear or a light jacket.",
            "Old towns, eco-corridors, and cobblestone streets are best explored at a slow pace — wear comfortable, non-slip shoes.",
        ]
    )
    if any("cycl" in context.lower() for context in rag_contexts):
        tips.append("The local guide notes the Erhai Lake eco-corridor is great for cycling — consider it for day two or three.")
    tips = _clean_user_tips(tips, request.destination)

    summary = (
        llm_draft.summary
        if llm_draft is not None
        else f"This is a {day_count}-day itinerary generated for {request.destination}, focused on: {preference_text}."
    )

    itinerary = Itinerary(
        trip_id=f"trip_{request.destination}_{request.start_date.isoformat()}",
        destination=request.destination,
        summary=summary,
        days=days,
        estimated_budget=0.0,
        budget_breakdown=BudgetBreakdown(),
        tips=tips,
        source_notes=source_notes,
        token_usage=token_usage,
    )
    return _maybe_enrich_itinerary_with_map_data(
        itinerary,
        city=request.destination,
        request_budget=request.budget,
    )


def edit_trip_itinerary(request: TripEditRequest) -> Itinerary:
    """Prefer editing the target day via the LLM; fall back to rule-based editing if that fails."""
    updated_itinerary = request.current_itinerary.model_copy(deep=True)

    target_day = updated_itinerary.days[0] if updated_itinerary.days else None
    if request.edit_scope and request.edit_scope.startswith("day_"):
        try:
            target_day_index = int(request.edit_scope.split("_")[1])
            matched_day = next(
                (day for day in updated_itinerary.days if day.day_index == target_day_index),
                None,
            )
            if matched_day is not None:
                target_day = matched_day
        except (IndexError, ValueError):
            pass

    llm_edit_applied = False
    edit_token_usage = {"prompt_tokens": 0, "completion_tokens": 0}
    if target_day is not None:
        day_edit_draft, edit_token_usage = generate_day_edit_draft(request, target_day)
        if day_edit_draft is not None:
            target_day.theme = day_edit_draft.theme
            if target_day.spots:
                target_day.spots[0].name = day_edit_draft.spot_name
                target_day.spots[0].description = day_edit_draft.spot_description
                target_day.spots[0].estimated_cost = _estimate_ticket_cost(
                    day_edit_draft.spot_name,
                    day_edit_draft.spot_description,
                )
                target_day.spots[0].address = None
                target_day.spots[0].latitude = None
                target_day.spots[0].longitude = None
                target_day.spots[0].poi_id = None
            if target_day.meals:
                target_day.meals[0].name = day_edit_draft.meal_name
                target_day.meals[0].notes = day_edit_draft.meal_notes

            if target_day.notes:
                target_day.notes[-1] = day_edit_draft.daily_note
            else:
                target_day.notes.append(day_edit_draft.daily_note)

            llm_edit_applied = True
        else:
            if "relaxed" in request.user_instruction.lower():
                target_day.theme = f"{target_day.theme} (adjusted to be more relaxed)"
                target_day.notes.append("The pace has been made more relaxed per your request.")

            if "don't schedule" in request.user_instruction.lower() and target_day.spots:
                target_day.spots[0].name = "Free time / flexible schedule"
                target_day.spots[0].description = "Fixed attractions have been reduced per your request, leaving more free time."
                target_day.spots[0].estimated_cost = 0.0
                target_day.spots[0].address = None
                target_day.spots[0].latitude = None
                target_day.spots[0].longitude = None
                target_day.spots[0].poi_id = None

    updated_itinerary.source_notes.append(
        f"Itinerary updated per your edit instruction: {request.user_instruction}"
    )
    updated_itinerary.tips = _clean_user_tips(
        updated_itinerary.tips,
        updated_itinerary.destination,
    )
    updated_itinerary.tips.append("The target day has been updated per your edit request — before you leave, double-check that day's transport, weather, and attraction opening hours.")

    updated_itinerary.token_usage = TokenUsage(
        rewrite_prompt_tokens=0,
        rewrite_completion_tokens=0,
        planner_prompt_tokens=edit_token_usage.get("prompt_tokens", 0),
        planner_completion_tokens=edit_token_usage.get("completion_tokens", 0),
    )

    reference_budget = (
        updated_itinerary.estimated_budget
        or updated_itinerary.budget_breakdown.total
        or None
    )
    return _maybe_enrich_itinerary_with_map_data(
        updated_itinerary,
        city=updated_itinerary.destination,
        request_budget=reference_budget,
    )
