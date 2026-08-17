"""Persistence model for Houston 311 current state."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Double,
    Index,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from libs.database.models.base import Base


class Houston311Request(Base):
    """Latest observed state for one stable Houston 311 case."""

    __tablename__ = "houston_311_request"
    __table_args__ = (
        CheckConstraint(
            "latitude IS NULL OR latitude BETWEEN -90 AND 90",
            name="latitude_range",
        ),
        CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180",
            name="longitude_range",
        ),
        CheckConstraint(
            "first_seen_at <= last_seen_at",
            name="observation_order",
        ),
        Index("ix_houston_311_request_created_at", "created_at"),
        Index("ix_houston_311_request_council_district", "council_district"),
        Index("ix_houston_311_request_source_object_id", "source_object_id"),
        {"schema": "raw"},
    )

    case_number: Mapped[str] = mapped_column(Text, primary_key=True)
    source_object_id: Mapped[int] = mapped_column(BigInteger)
    case_number_365: Mapped[str | None] = mapped_column(Text)
    incident_address: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Double)
    longitude: Mapped[float | None] = mapped_column(Double)
    status: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    title: Mapped[str | None] = mapped_column(Text)
    case_type: Mapped[str | None] = mapped_column(Text)
    sla_time: Mapped[str | None] = mapped_column(Text)
    service_area: Mapped[str | None] = mapped_column(Text)
    council_district: Mapped[str | None] = mapped_column(Text)
    key_map: Mapped[str | None] = mapped_column(Text)
    department: Mapped[str | None] = mapped_column(Text)
    division: Mapped[str | None] = mapped_column(Text)
    state_code: Mapped[str | None] = mapped_column(Text)
    state_code_name: Mapped[str | None] = mapped_column(Text)
    swm_quadrant: Mapped[str | None] = mapped_column(Text)
    recycling_quadrant: Mapped[str | None] = mapped_column(Text)
    heavy_trash_quadrant: Mapped[str | None] = mapped_column(Text)
    resolution_notes: Mapped[str | None] = mapped_column(Text)
    meaningful_hash: Mapped[str] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
