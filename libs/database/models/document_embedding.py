"""Document embedding persistence model."""

from __future__ import annotations

import datetime as dt  # ruff: ignore[typing-only-standard-library-import] - SQLAlchemy resolves mapped annotations at runtime.
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from libs.database.models.base import Base
from libs.document_intelligence.schemas import MAX_EMBEDDING_DIMENSIONS

if TYPE_CHECKING:
    from libs.database.models.document_chunk import DocumentChunkRecord


class DocumentEmbeddingRecord(Base):
    """One model-specific vector for a deterministic document chunk."""

    __tablename__ = "document_embedding"
    __table_args__ = (
        CheckConstraint(
            f"embedding_dimensions BETWEEN 1 AND {MAX_EMBEDDING_DIMENSIONS}",
            name="embedding_dimensions_supported",
        ),
        CheckConstraint(
            "vector_dims(embedding) = embedding_dimensions",
            name="embedding_dimensions_match",
        ),
        UniqueConstraint(
            "chunk_id",
            "embedding_provider",
            "embedding_model",
            "embedding_model_revision",
            "embedding_dimensions",
            name="chunk_embedding_identity",
        ),
        {"schema": "document_intelligence"},
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    chunk_id: Mapped[UUID] = mapped_column(
        ForeignKey("document_intelligence.document_chunk.id", ondelete="CASCADE"),
    )
    embedding_provider: Mapped[str] = mapped_column(Text)
    embedding_model: Mapped[str] = mapped_column(Text)
    embedding_model_revision: Mapped[str] = mapped_column(Text)
    embedding_dimensions: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list[float]] = mapped_column(Vector())
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    chunk: Mapped[DocumentChunkRecord] = relationship(back_populates="embeddings")
