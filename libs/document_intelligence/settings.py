"""Fixed document-processing policy."""

from datetime import timedelta

from libs.pydantic_ai_core.schemas import (
    DEFAULT_EMBEDDING_MODEL,
    EMBEDDING_MODEL_CONTRACTS,
)

DOCUMENT_CHUNK_MAX_TOKENS = 507
DOCUMENT_CHUNKER_NAME = "docling_hybrid"
DOCUMENT_STAGING_PREFIX = "document-processing"
DOCUMENT_STAGING_RETENTION = timedelta(days=1)
DOCUMENT_CHUNKER_VERSION = (
    f"tokenizer={DEFAULT_EMBEDDING_MODEL.model_name}@"
    f"{EMBEDDING_MODEL_CONTRACTS[DEFAULT_EMBEDDING_MODEL].revision}:"
    f"max_tokens={DOCUMENT_CHUNK_MAX_TOKENS}:"
    "merge_peers=true:repeat_table_header=true"
)
