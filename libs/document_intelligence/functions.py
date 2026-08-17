"""End-to-end document processing and reuse."""

import asyncio
import hashlib
import json
from uuid import UUID, uuid4

import logfire
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from libs.blob_storage.functions import create_blobs, delete_blob, read_blob
from libs.blob_storage.schemas import BlobUpload
from libs.database.crud.documents import (
    delete_document,
    find_processed_document,
    get_document_for_indexing,
    get_persisted_document,
    list_expired_documents,
    persist_document,
    persist_document_index,
)
from libs.database.functions import get_api_db_engine
from libs.database.schemas import (
    DocumentPersistenceInput,
    PersistedDocument,
    ProcessedDocument,
    StoredDocumentArtifacts,
)
from libs.document_intelligence.conversion import chunk_document, convert_document
from libs.document_intelligence.embeddings import embed_document_chunks
from libs.document_intelligence.schemas import DocumentUpload
from libs.document_intelligence.security import approve_document
from libs.pydantic_ai_core.schemas import (
    DEFAULT_EMBEDDING_MODEL,
    PydanticAIEmbeddingModel,
)

DOCUMENT_STORAGE_BUCKET = "newman-labs"


async def delete_expired_documents(
    *,
    engine: AsyncEngine | None = None,
) -> int:
    """Delete expired private objects and records in bounded batches."""
    engine = engine or get_api_db_engine()
    deleted_documents = 0
    while True:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            expired_documents = await list_expired_documents(session=session)
        if not expired_documents:
            return deleted_documents

        for document in expired_documents:
            for object_key in document.storage_object_keys:
                await delete_blob(bucket=document.storage_bucket, key=object_key)
            async with (
                AsyncSession(engine, expire_on_commit=False) as session,
                session.begin(),
            ):
                deleted = await delete_document(
                    session=session,
                    document_id=document.document_id,
                )
            deleted_documents += deleted


async def index_document(
    *,
    document_id: UUID,
    embedding_model: PydanticAIEmbeddingModel = DEFAULT_EMBEDDING_MODEL,
) -> PersistedDocument:
    """Promote a stored Docling parse into an indexed research document."""
    if not isinstance(embedding_model, PydanticAIEmbeddingModel):
        raise TypeError("embedding_model must be an approved embedding model")
    engine = get_api_db_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        index_state = await get_document_for_indexing(
            session=session,
            document_id=document_id,
            embedding_model=embedding_model,
        )
    if index_state is None:
        raise ValueError("Document does not exist or has expired")
    if index_state.is_indexed:
        return index_state.document

    chunks = index_state.chunks
    if not chunks:
        stored_docling_document = await read_blob(
            bucket=index_state.document.storage_bucket,
            key=index_state.document.docling_document_object_key,
        )
        chunks = await chunk_document(source=stored_docling_document.content)
    embedded_chunks = await embed_document_chunks(
        chunks=chunks,
        model=embedding_model,
    )
    async with (
        AsyncSession(engine, expire_on_commit=False) as session,
        session.begin(),
    ):
        return await persist_document_index(
            session=session,
            document_id=index_state.document.document_id,
            parse_id=index_state.document.parse_id,
            embedded_chunks=embedded_chunks,
        )


async def get_document(*, document_id: UUID) -> ProcessedDocument:
    """Return one active document with object-backed parser output loaded."""
    engine = get_api_db_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        persisted = await get_persisted_document(
            session=session,
            document_id=document_id,
        )
    if persisted is None:
        raise ValueError("Document does not exist or has expired")

    markdown, docling_document = await asyncio.gather(
        read_blob(
            bucket=persisted.storage_bucket,
            key=persisted.markdown_object_key,
        ),
        read_blob(
            bucket=persisted.storage_bucket,
            key=persisted.docling_document_object_key,
        ),
    )
    return ProcessedDocument(
        **persisted.model_dump(),
        markdown=markdown.content.decode("utf-8"),
        docling_document=json.loads(docling_document.content),
    )


async def process_document(
    *,
    source: DocumentUpload,
    index_for_search: bool = False,
    embedding_model: PydanticAIEmbeddingModel = DEFAULT_EMBEDDING_MODEL,
) -> ProcessedDocument:
    """Scan, convert, store, and return one document with its parser output."""
    with logfire.span(
        "Approve document {document_id}",
        document_id=str(source.document_id),
    ):
        approved = await approve_document(source=source)
    content_sha256 = hashlib.sha256(source.content).hexdigest()
    engine = get_api_db_engine()

    async with AsyncSession(engine, expire_on_commit=False) as session:
        existing = await find_processed_document(
            session=session,
            content_sha256=content_sha256,
        )
    if existing is not None:
        if index_for_search:
            await index_document(
                document_id=existing.document_id,
                embedding_model=embedding_model,
            )
        return await get_document(document_id=existing.document_id)

    with logfire.span(
        "Convert document {document_id}",
        document_id=str(source.document_id),
    ):
        converted = await convert_document(
            source=approved,
            index_for_search=index_for_search,
        )
    embedded_chunks = (
        await embed_document_chunks(
            chunks=converted.chunks,
            model=embedding_model,
        )
        if index_for_search
        else []
    )
    parse_id = uuid4()
    object_root = f"documents/{source.document_id}"
    with logfire.span(
        "Store document artifacts {document_id}",
        document_id=str(source.document_id),
    ):
        stored_blobs = await create_blobs(
            blobs=[
                BlobUpload(
                    bucket=DOCUMENT_STORAGE_BUCKET,
                    key=f"{object_root}/original.pdf",
                    content=source.content,
                    content_type=source.media_type,
                ),
                BlobUpload(
                    bucket=DOCUMENT_STORAGE_BUCKET,
                    key=f"{object_root}/parses/{parse_id}/document.md",
                    content=converted.markdown.encode(),
                    content_type="text/markdown; charset=utf-8",
                ),
                BlobUpload(
                    bucket=DOCUMENT_STORAGE_BUCKET,
                    key=f"{object_root}/parses/{parse_id}/docling.json",
                    content=json.dumps(
                        converted.docling_document,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    ).encode(),
                    content_type="application/json",
                ),
            ]
        )
    original, markdown, docling_document = stored_blobs

    stored = StoredDocumentArtifacts(
        original=original,
        markdown=markdown,
        docling_document=docling_document,
    )

    try:  # ruff: ignore[too-many-statements-in-try-clause] - keep locked deduplication and persistence in one transaction.
        with logfire.span(
            "Persist document metadata {document_id}",
            document_id=str(source.document_id),
        ):
            async with (
                AsyncSession(engine, expire_on_commit=False) as session,
                session.begin(),
            ):
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:hash, 0))"),
                    {"hash": content_sha256},
                )
                existing = await find_processed_document(
                    session=session,
                    content_sha256=content_sha256,
                )
                if existing is None:
                    persisted = await persist_document(
                        session=session,
                        document_input=DocumentPersistenceInput(
                            source=approved,
                            stored=stored,
                            converted=converted,
                            embedded_chunks=embedded_chunks,
                        ),
                    )
                else:
                    persisted = existing
    except Exception:
        for stored_blob in reversed(stored_blobs):
            await delete_blob(bucket=stored_blob.bucket, key=stored_blob.key)
        raise

    if existing is not None:
        for stored_blob in reversed(stored_blobs):
            await delete_blob(bucket=stored_blob.bucket, key=stored_blob.key)
        if index_for_search:
            await index_document(
                document_id=existing.document_id,
                embedding_model=embedding_model,
            )
        return await get_document(document_id=existing.document_id)
    return ProcessedDocument(
        **persisted.model_dump(),
        markdown=converted.markdown,
        docling_document=converted.docling_document,
    )
