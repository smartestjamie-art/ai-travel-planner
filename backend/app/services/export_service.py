from __future__ import annotations

from io import BytesIO
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape

from app.models.schemas import Itinerary, TripDetailResponse


TECHNICAL_EXPORT_KEYWORDS = (
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


def _safe_text(value: object) -> str:
    """Escape special characters for a ReportLab Paragraph so content isn't parsed as markup."""
    return escape(str(value or ""))


def _clean_export_tips(tips: list[str]) -> list[str]:
    """Filter out internal implementation notes from the exported file."""
    cleaned_tips: list[str] = []
    for tip in tips:
        normalized_tip = tip.strip()
        if not normalized_tip:
            continue
        if any(keyword in normalized_tip for keyword in TECHNICAL_EXPORT_KEYWORDS):
            continue
        if normalized_tip not in cleaned_tips:
            cleaned_tips.append(normalized_tip)
    return cleaned_tips


def _public_source_notes(source_notes: list[str]) -> list[str]:
    """Keep only user-facing source notes, filtering out backend implementation details."""
    public_notes: list[str] = []
    for note in source_notes:
        normalized_note = note.strip()
        if not normalized_note:
            continue
        if any(keyword in normalized_note for keyword in TECHNICAL_EXPORT_KEYWORDS):
            continue
        if normalized_note.startswith("[Source:"):
            public_notes.append(normalized_note)
    return public_notes


def _render_budget_lines(itinerary: Itinerary) -> list[str]:
    """Render the budget breakdown as a Markdown list."""
    budget = itinerary.budget_breakdown
    return [
        f"- Transport: {budget.transport:.2f} CNY",
        f"- Hotel: {budget.hotel:.2f} CNY",
        f"- Meals: {budget.meals:.2f} CNY",
        f"- Tickets: {budget.tickets:.2f} CNY",
        f"- Other: {budget.other:.2f} CNY",
        f"- Total: {budget.total:.2f} CNY",
    ]


def itinerary_to_markdown(trip_detail: TripDetailResponse) -> str:
    """Render the full itinerary as easy-to-share Markdown text."""
    itinerary = trip_detail.itinerary

    lines: list[str] = [
        f"# {itinerary.destination} Itinerary",
        "",
        f"- Trip ID: {trip_detail.trip_id}",
        f"- Destination: {itinerary.destination}",
        f"- Estimated budget: {itinerary.estimated_budget:.2f} CNY",
        "",
        "## Overview",
        itinerary.summary,
        "",
        "## Daily Schedule",
    ]

    for day in itinerary.days:
        lines.extend(
            [
                "",
                f"### Day {day.day_index} {day.theme or ''}".rstrip(),
                f"- Date: {day.date.isoformat()}" if day.date else "- Date: TBD",
            ]
        )

        for spot in day.spots:
            lines.extend(
                [
                    f"- Main attraction: {spot.name}",
                    f"  - Time: {spot.start_time or 'TBD'} - {spot.end_time or 'TBD'}",
                    f"  - Notes: {spot.description or 'None'}",
                ]
            )

        for meal in day.meals:
            lines.extend(
                [
                    f"- Meal suggestion: {meal.name} ({meal.meal_type})",
                    f"  - Notes: {meal.notes or 'None'}",
                ]
            )

        if day.hotel is not None:
            lines.append(
                f"- Accommodation: {day.hotel.name} ({day.hotel.level or 'Unrated'})"
            )

        for note in day.notes:
            lines.append(f"- Note: {note}")

    lines.extend(["", "## Budget Breakdown", *_render_budget_lines(itinerary)])

    export_tips = _clean_export_tips(itinerary.tips)
    if export_tips:
        lines.extend(["", "## Travel Tips"])
        lines.extend(f"- {tip}" for tip in export_tips)

    public_notes = _public_source_notes(itinerary.source_notes)
    if public_notes:
        lines.extend(["", "## References"])
        lines.extend(f"- {note}" for note in public_notes)

    return "\n".join(lines).strip() + "\n"


def _register_pdf_font() -> str:
    """Register a font suitable for rendering CJK text in the PDF."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    font_name = "STSong-Light"
    try:
        pdfmetrics.getFont(font_name)
    except KeyError:
        pdfmetrics.registerFont(UnicodeCIDFont(font_name))
    return font_name


def _draw_pdf_footer(canvas, doc, trip_detail: TripDetailResponse, font_name: str) -> None:
    """Draw the footer and page number at the bottom of every page."""
    from reportlab.lib import colors
    from reportlab.lib.units import mm

    page_width, _ = doc.pagesize
    footer_y = 10 * mm
    line_y = 14 * mm

    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#cbd2d9"))
    canvas.setLineWidth(0.5)
    canvas.line(doc.leftMargin, line_y, page_width - doc.rightMargin, line_y)

    canvas.setFont(font_name, 9)
    canvas.setFillColor(colors.HexColor("#52606d"))
    canvas.drawString(doc.leftMargin, footer_y, f"Trip Planner Demo | {trip_detail.trip_id}")
    canvas.drawRightString(page_width - doc.rightMargin, footer_y, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


def _load_pdf_image(image_url: str, max_width: float, max_height: float):
    """Download an attraction image and convert it into a ReportLab-renderable object, returning None on failure."""
    from reportlab.platypus import Image

    if not image_url:
        return None

    try:
        request = Request(
            image_url,
            headers={"User-Agent": "TripPlannerDemo/1.0"},
        )
        with urlopen(request, timeout=5) as response:
            image_bytes = response.read(2_000_000)
    except Exception:
        return None

    try:
        image = Image(BytesIO(image_bytes))
        image._restrictSize(max_width, max_height)
        return image
    except Exception:
        return None


def itinerary_to_pdf_bytes(trip_detail: TripDetailResponse) -> bytes:
    """Render the full itinerary as a cleanly formatted PDF binary."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:
        raise RuntimeError(
            "PDF export requires reportlab; please install it first: pip install reportlab"
        ) from exc

    font_name = _register_pdf_font()
    itinerary = trip_detail.itinerary

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"{trip_detail.trip_id}.pdf",
    )

    base_styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TripTitle",
        parent=base_styles["Title"],
        fontName=font_name,
        fontSize=22,
        leading=28,
        textColor=colors.HexColor("#16324f"),
        spaceAfter=8,
        wordWrap="CJK",
    )
    subtitle_style = ParagraphStyle(
        "TripSubtitle",
        parent=base_styles["BodyText"],
        fontName=font_name,
        fontSize=10.5,
        leading=14,
        textColor=colors.HexColor("#4b5d73"),
        spaceAfter=10,
        wordWrap="CJK",
    )
    section_style = ParagraphStyle(
        "TripSection",
        parent=base_styles["Heading2"],
        fontName=font_name,
        fontSize=13.5,
        leading=19,
        textColor=colors.HexColor("#0f4c5c"),
        spaceBefore=10,
        spaceAfter=6,
        wordWrap="CJK",
    )
    day_style = ParagraphStyle(
        "TripDay",
        parent=base_styles["Heading3"],
        fontName=font_name,
        fontSize=12,
        leading=17,
        textColor=colors.HexColor("#1b4332"),
        spaceBefore=6,
        spaceAfter=4,
        wordWrap="CJK",
    )
    body_style = ParagraphStyle(
        "TripBody",
        parent=base_styles["BodyText"],
        fontName=font_name,
        fontSize=10.5,
        leading=15,
        textColor=colors.HexColor("#222222"),
        spaceAfter=4,
        wordWrap="CJK",
    )
    note_style = ParagraphStyle(
        "TripNote",
        parent=body_style,
        leftIndent=8,
        bulletIndent=0,
        spaceAfter=3,
    )

    story = [
        Paragraph(f"{_safe_text(itinerary.destination)} Itinerary", title_style),
        Paragraph(
            f"Trip ID: {_safe_text(trip_detail.trip_id)}<br/>"
            f"Destination: {_safe_text(itinerary.destination)}<br/>"
            f"Estimated budget: {itinerary.estimated_budget:.2f} CNY",
            subtitle_style,
        ),
    ]

    meta_table = Table(
        [
            ["Trip length", str(len(itinerary.days))],
            ["Created at", trip_detail.created_at.isoformat() if trip_detail.created_at else "Not recorded"],
            ["Updated at", trip_detail.updated_at.isoformat() if trip_detail.updated_at else "Not recorded"],
        ],
        colWidths=[28 * mm, 120 * mm],
    )
    meta_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#243b53")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eaf4f4")),
                ("BACKGROUND", (1, 0), (1, -1), colors.HexColor("#f8fbff")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cdd7e1")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.extend([meta_table, Spacer(1, 8)])

    story.append(Paragraph("Overview", section_style))
    story.append(Paragraph(_safe_text(itinerary.summary), body_style))

    story.append(Paragraph("Daily Schedule", section_style))
    for day in itinerary.days:
        title = f"Day {day.day_index}"
        if day.theme:
            title += f" · {day.theme}"
        story.append(Paragraph(title, day_style))

        if day.date:
            story.append(Paragraph(f"Date: {day.date.isoformat()}", body_style))

        for spot in day.spots:
            story.append(Paragraph(f"Main attraction: {_safe_text(spot.name)}", body_style))
            image_url = getattr(spot, "image_url", None)
            spot_image = _load_pdf_image(image_url or "", max_width=72 * mm, max_height=42 * mm)
            if spot_image is not None:
                story.extend([spot_image, Spacer(1, 4)])
            story.append(
                Paragraph(
                    f"Time: {_safe_text(spot.start_time or 'TBD')} - {_safe_text(spot.end_time or 'TBD')}",
                    note_style,
                )
            )
            if spot.address or spot.location:
                story.append(
                    Paragraph(
                        f"Address: {_safe_text(spot.address or spot.location)}",
                        note_style,
                    )
                )
            story.append(Paragraph(f"Notes: {_safe_text(spot.description or 'None')}", note_style))

        for meal in day.meals:
            story.append(
                Paragraph(
                    f"Meal suggestion: {_safe_text(meal.name)} ({_safe_text(meal.meal_type)})",
                    body_style,
                )
            )
            story.append(Paragraph(f"Notes: {_safe_text(meal.notes or 'None')}", note_style))

        if day.hotel is not None:
            story.append(
                Paragraph(
                    f"Accommodation: {_safe_text(day.hotel.name)} ({_safe_text(day.hotel.level or 'Unrated')})",
                    body_style,
                )
            )

        for note in day.notes:
            story.append(Paragraph(f"Note: {_safe_text(note)}", note_style))

        story.append(Spacer(1, 4))

    story.append(Paragraph("Budget Breakdown", section_style))
    budget = itinerary.budget_breakdown
    budget_table = Table(
        [
            ["Item", "Amount (CNY)"],
            ["Transport", f"{budget.transport:.2f}"],
            ["Hotel", f"{budget.hotel:.2f}"],
            ["Meals", f"{budget.meals:.2f}"],
            ["Tickets", f"{budget.tickets:.2f}"],
            ["Other", f"{budget.other:.2f}"],
            ["Total", f"{budget.total:.2f}"],
        ],
        colWidths=[48 * mm, 48 * mm],
    )
    budget_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d9edf7")),
                ("BACKGROUND", (0, 1), (-1, -2), colors.white),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#eef6f2")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#1f2933")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd2d9")),
                ("ALIGN", (1, 1), (1, -1), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.extend([budget_table, Spacer(1, 6)])

    export_tips = _clean_export_tips(itinerary.tips)
    if export_tips:
        story.append(Paragraph("Travel Tips", section_style))
        for tip in export_tips:
            story.append(Paragraph(f"- {_safe_text(tip)}", body_style))

    public_notes = _public_source_notes(itinerary.source_notes)
    if public_notes:
        story.append(Paragraph("References", section_style))
        for note in public_notes:
            story.append(Paragraph(f"- {_safe_text(note)}", body_style))

    def draw_footer(canvas, document) -> None:
        _draw_pdf_footer(canvas, document, trip_detail, font_name)

    doc.build(
        story,
        onFirstPage=draw_footer,
        onLaterPages=draw_footer,
    )
    return buffer.getvalue()
