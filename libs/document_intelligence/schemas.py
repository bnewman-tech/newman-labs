"""Typed contracts for untrusted documents and their derived data."""

from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import Field, FiniteFloat, JsonValue, model_validator

from libs.core.pydantic_base import NewmanLabsModel

MAX_EMBEDDING_DIMENSIONS = 16_000
DOCUMENT_FILENAME_MAX_LENGTH = 255


class EmbeddingProvider(StrEnum):
    """Embedding runtimes approved for persisted document vectors."""

    PYDANTIC_AI_GATEWAY = "pydantic_ai_gateway"
    SENTENCE_TRANSFORMERS = "sentence_transformers"


class SecurityVerdict(StrEnum):
    """Scanner outcomes accepted by the document-processing boundary."""

    ALLOW = "allow"
    FLAG = "flag"
    BLOCK = "block"
    ERROR = "error"
    TIMEOUT = "timeout"


class DocumentSecurityScan(NewmanLabsModel):
    """A safe operational summary from the configured document scanner."""

    scanner_name: str = Field(min_length=1)
    scanner_version: str = Field(min_length=1)
    verdict: SecurityVerdict
    risk_score: FiniteFloat | None = Field(default=None, ge=0, le=1)
    findings: list[str] = Field(default_factory=list)


class DocumentUpload(NewmanLabsModel):
    """An untrusted document submitted for processing."""

    document_id: UUID
    original_filename: str = Field(
        min_length=1,
        max_length=DOCUMENT_FILENAME_MAX_LENGTH,
    )
    media_type: str
    content: bytes = Field(repr=False)


class ApprovedDocument(DocumentUpload):
    """A document that Newman Labs scanned and approved."""

    security_scan: DocumentSecurityScan

    @model_validator(mode="after")
    def validate_security_scan(self) -> Self:
        """Require a non-blocking scan before creating the trusted contract."""
        if self.security_scan.verdict not in {
            SecurityVerdict.ALLOW,
            SecurityVerdict.FLAG,
        }:
            raise ValueError("Approved documents require an allow or flag security verdict")
        return self


class DocumentChunk(NewmanLabsModel):
    """One native Docling retrieval chunk and its embedding context."""

    ordinal: int = Field(ge=0)
    text: str = Field(min_length=1)
    contextualized_text: str = Field(min_length=1)
    token_count: int = Field(ge=1)
    content_sha256: str = Field(min_length=64, max_length=64)
    page_numbers: list[int] = Field(default_factory=list)
    chunker_name: str = Field(min_length=1)
    chunker_version: str = Field(min_length=1)


class EmbeddedDocumentChunk(DocumentChunk):
    """A retrieval chunk paired with its model-specific vector."""

    embedding: list[FiniteFloat] = Field(min_length=1)
    embedding_provider: EmbeddingProvider
    embedding_model: str = Field(min_length=1)
    embedding_model_revision: str = Field(min_length=1)
    embedding_dimensions: int = Field(ge=1, le=MAX_EMBEDDING_DIMENSIONS)

    @model_validator(mode="after")
    def validate_embedding(self) -> Self:
        """Require one declared dimension per value and a cosine-searchable vector."""
        if len(self.embedding) != self.embedding_dimensions:
            raise ValueError("Embedding length does not match its declared dimensions")
        if not any(self.embedding):
            raise ValueError("Embedding must not be a zero vector")
        return self


class ConvertedDocument(NewmanLabsModel):
    """Normalized Docling output ready for persistence and embedding."""

    document_id: UUID
    content_sha256: str = Field(min_length=64, max_length=64)
    page_count: int = Field(ge=1)
    parser_name: str = Field(min_length=1)
    parser_version: str = Field(min_length=1)
    markdown: str = Field(min_length=1)
    docling_document: dict[str, JsonValue]
    chunks: list[DocumentChunk] = Field(default_factory=list)
