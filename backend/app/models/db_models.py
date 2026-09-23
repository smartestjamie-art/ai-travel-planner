from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.config import Base


class TripRecord(Base):
    """Minimal trip table used by the current version."""

    __tablename__ = "trip_records"

    # Internal database primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Itinerary identifier used on the business side
    trip_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    destination: Mapped[str] = mapped_column(String(100))
    summary: Mapped[str] = mapped_column(Text)
    # JSON string of the complete itinerary
    itinerary_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
