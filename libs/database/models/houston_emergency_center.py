"""Houston Emergency Center persistence models."""

from datetime import datetime

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Double,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from libs.database.models.base import Base


class HoustonEmergencyCenterIncident(Base):
    """Observed lifecycle of one retained Houston Emergency Center incident."""

    __tablename__ = "houston_emergency_center_incident"
    __table_args__ = (
        CheckConstraint(
            "first_seen_at <= last_seen_at",
            name="observation_order",
        ),
        CheckConstraint(
            "(is_active AND ended_at IS NULL) OR (NOT is_active AND ended_at IS NOT NULL)",
            name="lifecycle_state",
        ),
        CheckConstraint(
            "ended_at IS NULL OR ended_at >= opened_at",
            name="end_after_open",
        ),
        CheckConstraint("agency IN ('F', 'P')", name="agency"),
        CheckConstraint("source_incident_id > 0", name="source_id_positive"),
        CheckConstraint(
            "reported_unit_count >= 0",
            name="unit_count_nonnegative",
        ),
        CheckConstraint("latitude BETWEEN -90 AND 90", name="latitude_range"),
        CheckConstraint(
            "longitude BETWEEN -180 AND 180",
            name="longitude_range",
        ),
        Index("ix_houston_emergency_center_incident_agency", "agency"),
        Index("ix_houston_emergency_center_incident_opened_at", "opened_at"),
        Index("ix_houston_emergency_center_incident_is_active", "is_active"),
        Index("ix_houston_emergency_center_incident_key_map", "key_map"),
        UniqueConstraint(
            "agency",
            "source_incident_id",
            "opened_at",
            name="agency_source_incident_opened_at",
        ),
        {"schema": "raw"},
    )

    incident_id: Mapped[str] = mapped_column(Text, primary_key=True)
    source_incident_id: Mapped[int] = mapped_column(BigInteger)
    agency: Mapped[str] = mapped_column(Text)
    address: Mapped[str] = mapped_column(Text)
    cross_street: Mapped[str | None] = mapped_column(Text)
    longitude: Mapped[float] = mapped_column(Double)
    latitude: Mapped[float] = mapped_column(Double)
    key_map: Mapped[str | None] = mapped_column(Text)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    incident_type: Mapped[str] = mapped_column(Text)
    alarm_level: Mapped[str | None] = mapped_column(Text)
    reported_unit_count: Mapped[int] = mapped_column(Integer)
    units: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    combined_response: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    meaningful_hash: Mapped[str] = mapped_column(Text)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
