"""Document parser-result persistence model."""

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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from libs.database.models.base import Base

if TYPE_CHECKING:
    from libs.database.models.document import DocumentRecord
    from libs.database.models.document_chunk import DocumentChunkRecord


class DocumentParseRecord(Base):
    """Immutable output produced by one parser and parser version."""

    __tablename__ = "document_parse"
    __table_args__ = (
        CheckConstraint("page_count > 0", name="page_count_positive"),
        UniqueConstraint(
            "document_id",
            "parser_name",
            "parser_version",
            name="document_parse_identity",
        ),
        {"schema": "document_intelligence"},
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("document_intelligence.document.id", ondelete="CASCADE"),
    )
    parser_name: Mapped[str] = mapped_column(Text)
    parser_version: Mapped[str] = mapped_column(Text)
    page_count: Mapped[int] = mapped_column(Integer)
    markdown_object_key: Mapped[str] = mapped_column(Text, unique=True)
    markdown_sha256: Mapped[str] = mapped_column(Text)
    docling_document_object_key: Mapped[str] = mapped_column(Text, unique=True)
    docling_document_sha256: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    document: Mapped[DocumentRecord] = relationship(back_populates="parses")
    chunks: Mapped[list[DocumentChunkRecord]] = relationship(
        back_populates="parse",
        cascade="all, delete-orphan",
    )
