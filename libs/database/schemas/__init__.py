"""Pydantic contracts consumed and returned by database operations."""

from libs.database.schemas.documents import (
    DocumentIndexState,
    DocumentPersistenceInput,
    DocumentSearchResult,
    ExpiredDocument,
    PersistedDocument,
    ProcessedDocument,
    StoredDocumentArtifacts,
)
from libs.database.schemas.ingestion_runs import SourceIngestionResult

__all__ = [
    "DocumentIndexState",
    "DocumentPersistenceInput",
    "DocumentSearchResult",
    "ExpiredDocument",
    "PersistedDocument",
    "ProcessedDocument",
    "SourceIngestionResult",
    "StoredDocumentArtifacts",
]
