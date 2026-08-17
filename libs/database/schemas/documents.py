"""Document persistence contracts."""

from uuid import UUID

from pydantic import Field, JsonValue

from libs.blob_storage.schemas import StoredBlob
from libs.core.pydantic_base import NewmanLabsModel
from libs.document_intelligence.schemas import (
    ApprovedDocument,
    ConvertedDocument,
    DocumentChunk,
    EmbeddedDocumentChunk,
    EmbeddingProvider,
)


class PersistedDocument(NewmanLabsModel):
    """Stored parse needed to reuse one processed document."""

    document_id: UUID
    parse_id: UUID
    chunk_count: int = Field(ge=0)
    storage_bucket: str = Field(min_length=1)
    original_object_key: str = Field(min_length=1)
    markdown_object_key: str = Field(min_length=1)
    docling_document_object_key: str = Field(min_length=1)


class ProcessedDocument(PersistedDocument):
    """Persisted document identity and its retained parser output."""

    markdown: str = Field(min_length=1)
    docling_document: dict[str, JsonValue]


class DocumentIndexState(NewmanLabsModel):
    """Stored document, deterministic chunks, and one model's index state."""

    document: PersistedDocument
    chunks: list[DocumentChunk]
    is_indexed: bool


class ExpiredDocument(NewmanLabsModel):
    """Private object reference for one document due for retention cleanup."""

    document_id: UUID
    storage_bucket: str = Field(min_length=1)
    storage_object_keys: list[str] = Field(min_length=1)


class StoredDocumentArtifacts(NewmanLabsModel):
    """Private objects created for one parsed document."""

    original: StoredBlob
    markdown: StoredBlob
    docling_document: StoredBlob


class DocumentPersistenceInput(NewmanLabsModel):
    """Complete document data required for atomic persistence."""

    source: ApprovedDocument
    stored: StoredDocumentArtifacts
    converted: ConvertedDocument
    embedded_chunks: list[EmbeddedDocumentChunk] = Field(default_factory=list)


class DocumentSearchResult(NewmanLabsModel):
    """Document chunk returned by cosine-distance retrieval."""

    document_id: UUID
    chunk_id: UUID
    ordinal: int = Field(ge=0)
    text: str = Field(min_length=1)
    contextualized_text: str = Field(min_length=1)
    page_numbers: list[int]
    chunker_name: str = Field(min_length=1)
    chunker_version: str = Field(min_length=1)
    embedding_provider: EmbeddingProvider
    embedding_model: str = Field(min_length=1)
    embedding_model_revision: str = Field(min_length=1)
    embedding_dimensions: int = Field(ge=1)
    cosine_distance: float = Field(ge=0)
