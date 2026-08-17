"""Deterministic document chunk persistence model."""

from __future__ import annotations

import datetime as dt  # ruff: ignore[typing-only-standard-library-import] - SQLAlchemy resolves mapped annotations at runtime.
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from libs.database.models.base import Base

if TYPE_CHECKING:
    from libs.database.models.document_embedding import DocumentEmbeddingRecord
    from libs.database.models.document_parse import DocumentParseRecord


class DocumentChunkRecord(Base):
    """Deterministic parse chunk independent of embedding models."""

    __tablename__ = "document_chunk"
    __table_args__ = (
        CheckConstraint("ordinal >= 0", name="ordinal_nonnegative"),
        CheckConstraint("token_count > 0", name="token_count_positive"),
        UniqueConstraint(
            "parse_id",
            "chunker_name",
            "chunker_version",
            "ordinal",
            name="parse_chunker_ordinal",
        ),
        {"schema": "document_intelligence"},
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    parse_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "document_intelligence.document_parse.id",
            ondelete="CASCADE",
        ),
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    contextualized_text: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer)
    content_sha256: Mapped[str] = mapped_column(Text)
    page_numbers: Mapped[list[int]] = mapped_column(ARRAY(Integer))
    chunker_name: Mapped[str] = mapped_column(Text)
    chunker_version: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    parse: Mapped[DocumentParseRecord] = relationship(back_populates="chunks")
    embeddings: Mapped[list[DocumentEmbeddingRecord]] = relationship(
        back_populates="chunk",
        cascade="all, delete-orphan",
    )
