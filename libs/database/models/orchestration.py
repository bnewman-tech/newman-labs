"""Operational persistence models shared by managed data flows."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from libs.database.models.base import Base


class IngestionRunRecord(Base):
    """Append-only outcome of one source ingestion attempt."""

    __tablename__ = "ingestion_run"
    __table_args__ = (
        CheckConstraint(
            "status IN ('succeeded', 'failed')",
            name="status",
        ),
        CheckConstraint(
            "extracted_rows >= 0 AND inserted_rows >= 0 "
            "AND updated_rows >= 0 AND unchanged_rows >= 0 "
            "AND deactivated_rows >= 0 AND deleted_rows >= 0",
            name="row_counts_nonnegative",
        ),
        Index(
            "ix_ingestion_run_source_completed_at",
            "source_name",
            "completed_at",
        ),
        {"schema": "orchestration"},
    )

    run_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    source_name: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_cursor: Mapped[str | None] = mapped_column(Text)
    extracted_rows: Mapped[int] = mapped_column(Integer, server_default="0")
    inserted_rows: Mapped[int] = mapped_column(Integer, server_default="0")
    updated_rows: Mapped[int] = mapped_column(Integer, server_default="0")
    unchanged_rows: Mapped[int] = mapped_column(Integer, server_default="0")
    deactivated_rows: Mapped[int] = mapped_column(Integer, server_default="0")
    deleted_rows: Mapped[int] = mapped_column(Integer, server_default="0")
    previous_watermark: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_watermark: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    warnings: Mapped[list[str]] = mapped_column(
        JSONB,
        server_default=text("'[]'::jsonb"),
    )
    error_type: Mapped[str | None] = mapped_column(Text)
