"""Document lifecycle persistence model."""

from __future__ import annotations

import datetime as dt  # ruff: ignore[typing-only-standard-library-import] - SQLAlchemy resolves mapped annotations at runtime.
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from libs.database.models.base import Base

if TYPE_CHECKING:
    from libs.database.models.document_parse import DocumentParseRecord


class DocumentRecord(Base):
    """Lifecycle and private-storage metadata for one approved upload."""

    __tablename__ = "document"
    __table_args__ = (
        CheckConstraint(
            "status IN ('stored', 'converted', 'embedded', 'failed', 'deleted')",
            name="status",
        ),
        CheckConstraint("size_bytes > 0", name="size_positive"),
        CheckConstraint(
            "security_scan ->> 'verdict' IN ('allow', 'flag')",
            name="security_approved",
        ),
        Index("ix_document_content_sha256", "content_sha256"),
        Index("ix_document_expires_at", "expires_at"),
        {"schema": "document_intelligence"},
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    status: Mapped[str] = mapped_column(Text)
    storage_bucket: Mapped[str] = mapped_column(Text)
    storage_object_key: Mapped[str] = mapped_column(Text, unique=True)
    original_filename: Mapped[str] = mapped_column(Text)
    media_type: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    content_sha256: Mapped[str] = mapped_column(Text)
    security_scan: Mapped[dict[str, object]] = mapped_column(JSONB)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    parses: Mapped[list[DocumentParseRecord]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )
