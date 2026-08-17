"""Transactional document persistence and retrieval."""

import hashlib
import math
from datetime import UTC, datetime, timedelta
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import Select, cast, delete, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.database.models.document import DocumentRecord
from libs.database.models.document_chunk import DocumentChunkRecord
from libs.database.models.document_embedding import DocumentEmbeddingRecord
from libs.database.models.document_parse import DocumentParseRecord
from libs.database.schemas import (
    DocumentIndexState,
    DocumentPersistenceInput,
    DocumentSearchResult,
    ExpiredDocument,
    PersistedDocument,
)
from libs.document_intelligence.schemas import (
    DocumentChunk,
    EmbeddedDocumentChunk,
    EmbeddingProvider,
)
from libs.pydantic_ai_core.schemas import (
    DEFAULT_EMBEDDING_MODEL,
    EMBEDDING_MODEL_CONTRACTS,
    PydanticAIEmbeddingModel,
)

DOCUMENT_RETENTION_DAYS = 30
MAX_DOCUMENT_SEARCH_RESULTS = 100
DOCUMENT_RETENTION_BATCH_SIZE = 100


async def persist_document(
    *,
    session: AsyncSession,
    document_input: DocumentPersistenceInput,
) -> PersistedDocument:
    """Stage one document, immutable parse, and its chunks atomically."""
    source = document_input.source
    stored = document_input.stored
    converted = document_input.converted
    embedded_chunks = document_input.embedded_chunks
    if source.document_id != converted.document_id:
        raise ValueError("Document identifiers do not match")
    if not (hashlib.sha256(source.content).hexdigest() == stored.original.content_sha256 == converted.content_sha256):
        raise ValueError("Source, stored, and converted document hashes do not match")
    if (
        len({
            stored.original.bucket,
            stored.markdown.bucket,
            stored.docling_document.bucket,
        })
        != 1
    ):
        raise ValueError("Document artifacts must use one storage bucket")
    if len(embedded_chunks) != len(converted.chunks):
        raise ValueError("Converted chunks must be empty or fully embedded")
    for converted_chunk, embedded_chunk in zip(
        converted.chunks,
        embedded_chunks,
        strict=True,
    ):
        if (
            embedded_chunk.model_dump(
                exclude={
                    "embedding",
                    "embedding_provider",
                    "embedding_model",
                    "embedding_model_revision",
                    "embedding_dimensions",
                }
            )
            != converted_chunk.model_dump()
        ):
            raise ValueError("Embedded chunk does not match conversion")

    document = DocumentRecord(
        id=source.document_id,
        status="converted",
        storage_bucket=stored.original.bucket,
        storage_object_key=stored.original.key,
        original_filename=source.original_filename,
        media_type=source.media_type,
        size_bytes=len(source.content),
        content_sha256=converted.content_sha256,
        security_scan=source.security_scan.model_dump(mode="json"),
        expires_at=datetime.now(tz=UTC) + timedelta(days=DOCUMENT_RETENTION_DAYS),
    )
    document_parse = DocumentParseRecord(
        document=document,
        parser_name=converted.parser_name,
        parser_version=converted.parser_version,
        page_count=converted.page_count,
        markdown_object_key=stored.markdown.key,
        markdown_sha256=stored.markdown.content_sha256,
        docling_document_object_key=stored.docling_document.key,
        docling_document_sha256=stored.docling_document.content_sha256,
    )
    session.add(document)
    await session.flush()
    if embedded_chunks:
        return await persist_document_index(
            session=session,
            document_id=document.id,
            parse_id=document_parse.id,
            embedded_chunks=embedded_chunks,
        )
    return PersistedDocument(
        document_id=document.id,
        parse_id=document_parse.id,
        chunk_count=len(embedded_chunks),
        storage_bucket=document.storage_bucket,
        original_object_key=document.storage_object_key,
        markdown_object_key=document_parse.markdown_object_key,
        docling_document_object_key=document_parse.docling_document_object_key,
    )


async def persist_document_index(  # ruff: ignore[complex-structure] - Keep locking, validation, and atomic multi-model persistence together.
    *,
    session: AsyncSession,
    document_id: UUID,
    parse_id: UUID,
    embedded_chunks: list[EmbeddedDocumentChunk],
) -> PersistedDocument:
    """Atomically add one retrieval index to a converted document."""
    if not embedded_chunks:
        raise ValueError("Document indexing requires embedded chunks")
    embedding_contract = (
        embedded_chunks[0].embedding_provider,
        embedded_chunks[0].embedding_model,
        embedded_chunks[0].embedding_model_revision,
        embedded_chunks[0].embedding_dimensions,
    )
    if any(
        (
            chunk.embedding_provider,
            chunk.embedding_model,
            chunk.embedding_model_revision,
            chunk.embedding_dimensions,
        )
        != embedding_contract
        for chunk in embedded_chunks
    ):
        raise ValueError("Every document chunk must use one embedding contract")

    row = (
        await session.execute(
            select(DocumentRecord, DocumentParseRecord)
            .join(
                DocumentParseRecord,
                DocumentParseRecord.document_id == DocumentRecord.id,
            )
            .where(
                DocumentRecord.id == document_id,
                DocumentParseRecord.id == parse_id,
                DocumentRecord.expires_at > func.now(),
            )
            .with_for_update(of=DocumentRecord)
        )
    ).one_or_none()
    if row is None:
        raise ValueError("Document does not exist or has expired")
    document, document_parse = row
    if document.status not in {"converted", "embedded"}:
        raise ValueError(f"Document status {document.status!r} cannot be indexed")

    stored_chunks = list(
        await session.scalars(
            select(DocumentChunkRecord)
            .where(DocumentChunkRecord.parse_id == document_parse.id)
            .order_by(DocumentChunkRecord.ordinal)
        )
    )
    if stored_chunks:
        if len(stored_chunks) != len(embedded_chunks):
            raise ValueError("Embedded chunks do not match the stored document chunks")
        for stored_chunk, embedded_chunk in zip(
            stored_chunks,
            embedded_chunks,
            strict=True,
        ):
            if DocumentChunk(
                ordinal=stored_chunk.ordinal,
                text=stored_chunk.text,
                contextualized_text=stored_chunk.contextualized_text,
                token_count=stored_chunk.token_count,
                content_sha256=stored_chunk.content_sha256,
                page_numbers=stored_chunk.page_numbers,
                chunker_name=stored_chunk.chunker_name,
                chunker_version=stored_chunk.chunker_version,
            ) != DocumentChunk.model_validate(
                embedded_chunk.model_dump(
                    exclude={
                        "embedding",
                        "embedding_provider",
                        "embedding_model",
                        "embedding_model_revision",
                        "embedding_dimensions",
                    }
                )
            ):
                raise ValueError("Embedded chunks do not match the stored document chunks")

    existing_embedding_count = await session.scalar(
        select(func.count(DocumentEmbeddingRecord.id))
        .join(
            DocumentChunkRecord,
            DocumentChunkRecord.id == DocumentEmbeddingRecord.chunk_id,
        )
        .where(
            DocumentChunkRecord.parse_id == document_parse.id,
            DocumentEmbeddingRecord.embedding_provider == embedding_contract[0].value,
            DocumentEmbeddingRecord.embedding_model == embedding_contract[1],
            DocumentEmbeddingRecord.embedding_model_revision == embedding_contract[2],
            DocumentEmbeddingRecord.embedding_dimensions == embedding_contract[3],
        )
    )
    if stored_chunks and existing_embedding_count == len(stored_chunks):
        return PersistedDocument(
            document_id=document.id,
            parse_id=document_parse.id,
            chunk_count=len(stored_chunks),
            storage_bucket=document.storage_bucket,
            original_object_key=document.storage_object_key,
            markdown_object_key=document_parse.markdown_object_key,
            docling_document_object_key=document_parse.docling_document_object_key,
        )
    if existing_embedding_count:
        raise RuntimeError("Document has an incomplete embedding index")

    if not stored_chunks:
        stored_chunks = [
            DocumentChunkRecord(
                parse_id=document_parse.id,
                ordinal=chunk.ordinal,
                text=chunk.text,
                contextualized_text=chunk.contextualized_text,
                token_count=chunk.token_count,
                content_sha256=chunk.content_sha256,
                page_numbers=chunk.page_numbers,
                chunker_name=chunk.chunker_name,
                chunker_version=chunk.chunker_version,
            )
            for chunk in embedded_chunks
        ]
        session.add_all(stored_chunks)
        await session.flush()

    for stored_chunk, embedded_chunk in zip(
        stored_chunks,
        embedded_chunks,
        strict=True,
    ):
        session.add(
            DocumentEmbeddingRecord(
                chunk_id=stored_chunk.id,
                embedding_provider=embedded_chunk.embedding_provider.value,
                embedding_model=embedded_chunk.embedding_model,
                embedding_model_revision=embedded_chunk.embedding_model_revision,
                embedding_dimensions=embedded_chunk.embedding_dimensions,
                embedding=embedded_chunk.embedding,
            )
        )
    document.status = "embedded"
    await session.flush()
    return PersistedDocument(
        document_id=document.id,
        parse_id=document_parse.id,
        chunk_count=len(embedded_chunks),
        storage_bucket=document.storage_bucket,
        original_object_key=document.storage_object_key,
        markdown_object_key=document_parse.markdown_object_key,
        docling_document_object_key=document_parse.docling_document_object_key,
    )


async def get_document_for_indexing(
    *,
    session: AsyncSession,
    document_id: UUID,
    embedding_model: PydanticAIEmbeddingModel,
) -> DocumentIndexState | None:
    """Return stored chunks and whether one embedding contract is complete."""
    contract = EMBEDDING_MODEL_CONTRACTS[embedding_model]
    embedding_provider = (
        EmbeddingProvider.SENTENCE_TRANSFORMERS
        if embedding_model is PydanticAIEmbeddingModel.DENSE_ON
        else EmbeddingProvider.PYDANTIC_AI_GATEWAY
    )
    model_name = embedding_model.model_name
    statement = (
        select(
            DocumentRecord.id,
            DocumentParseRecord.id,
            DocumentRecord.storage_bucket,
            DocumentRecord.storage_object_key,
            DocumentParseRecord.markdown_object_key,
            DocumentParseRecord.docling_document_object_key,
        )
        .join(
            DocumentParseRecord,
            DocumentParseRecord.document_id == DocumentRecord.id,
        )
        .where(
            DocumentRecord.id == document_id,
            DocumentRecord.status.in_(("converted", "embedded")),
            DocumentRecord.expires_at > func.now(),
        )
        .limit(1)
    )
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        return None
    chunks = list(
        await session.scalars(
            select(DocumentChunkRecord)
            .where(DocumentChunkRecord.parse_id == row[1])
            .order_by(DocumentChunkRecord.ordinal)
        )
    )
    embedding_count = await session.scalar(
        select(func.count(DocumentEmbeddingRecord.id))
        .join(
            DocumentChunkRecord,
            DocumentChunkRecord.id == DocumentEmbeddingRecord.chunk_id,
        )
        .where(
            DocumentChunkRecord.parse_id == row[1],
            DocumentEmbeddingRecord.embedding_provider == embedding_provider.value,
            DocumentEmbeddingRecord.embedding_model == model_name,
            DocumentEmbeddingRecord.embedding_model_revision == contract.revision,
            DocumentEmbeddingRecord.embedding_dimensions == contract.dimensions,
        )
    )
    if embedding_count not in {0, len(chunks)}:
        raise RuntimeError("Document has an incomplete embedding index")
    return DocumentIndexState(
        document=PersistedDocument(
            document_id=row[0],
            parse_id=row[1],
            chunk_count=len(chunks),
            storage_bucket=row[2],
            original_object_key=row[3],
            markdown_object_key=row[4],
            docling_document_object_key=row[5],
        ),
        chunks=[
            DocumentChunk(
                ordinal=chunk.ordinal,
                text=chunk.text,
                contextualized_text=chunk.contextualized_text,
                token_count=chunk.token_count,
                content_sha256=chunk.content_sha256,
                page_numbers=chunk.page_numbers,
                chunker_name=chunk.chunker_name,
                chunker_version=chunk.chunker_version,
            )
            for chunk in chunks
        ],
        is_indexed=bool(chunks) and embedding_count == len(chunks),
    )


async def find_processed_document(
    *,
    session: AsyncSession,
    content_sha256: str,
) -> PersistedDocument | None:
    """Return the newest reusable parse for one exact document hash."""
    statement = (
        select(
            DocumentRecord.id,
            DocumentParseRecord.id,
            func.count(DocumentChunkRecord.id),
            DocumentRecord.storage_bucket,
            DocumentRecord.storage_object_key,
            DocumentParseRecord.markdown_object_key,
            DocumentParseRecord.docling_document_object_key,
        )
        .join(
            DocumentParseRecord,
            DocumentParseRecord.document_id == DocumentRecord.id,
        )
        .outerjoin(
            DocumentChunkRecord,
            DocumentChunkRecord.parse_id == DocumentParseRecord.id,
        )
        .where(
            DocumentRecord.content_sha256 == content_sha256,
            DocumentRecord.status.in_(("converted", "embedded")),
            DocumentRecord.expires_at > func.now(),
        )
        .group_by(
            DocumentRecord.id,
            DocumentParseRecord.id,
        )
        .order_by(DocumentRecord.created_at.desc())
        .limit(1)
    )
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        return None
    return PersistedDocument(
        document_id=row[0],
        parse_id=row[1],
        chunk_count=row[2],
        storage_bucket=row[3],
        original_object_key=row[4],
        markdown_object_key=row[5],
        docling_document_object_key=row[6],
    )


async def get_persisted_document(
    *,
    session: AsyncSession,
    document_id: UUID,
) -> PersistedDocument | None:
    """Return the active persisted parse for one document identifier."""
    statement = (
        select(
            DocumentRecord.id,
            DocumentParseRecord.id,
            func.count(DocumentChunkRecord.id),
            DocumentRecord.storage_bucket,
            DocumentRecord.storage_object_key,
            DocumentParseRecord.markdown_object_key,
            DocumentParseRecord.docling_document_object_key,
        )
        .join(
            DocumentParseRecord,
            DocumentParseRecord.document_id == DocumentRecord.id,
        )
        .outerjoin(
            DocumentChunkRecord,
            DocumentChunkRecord.parse_id == DocumentParseRecord.id,
        )
        .where(
            DocumentRecord.id == document_id,
            DocumentRecord.status.in_(("converted", "embedded")),
            DocumentRecord.expires_at > func.now(),
        )
        .group_by(DocumentRecord.id, DocumentParseRecord.id)
        .limit(1)
    )
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        return None
    return PersistedDocument(
        document_id=row[0],
        parse_id=row[1],
        chunk_count=row[2],
        storage_bucket=row[3],
        original_object_key=row[4],
        markdown_object_key=row[5],
        docling_document_object_key=row[6],
    )


async def list_expired_documents(
    *,
    session: AsyncSession,
) -> list[ExpiredDocument]:
    """Return the next deterministic batch due for retention deletion."""
    statement = (
        select(
            DocumentRecord.id,
            DocumentRecord.storage_bucket,
            DocumentRecord.storage_object_key,
            func.array_agg(DocumentParseRecord.markdown_object_key),
            func.array_agg(DocumentParseRecord.docling_document_object_key),
        )
        .join(
            DocumentParseRecord,
            DocumentParseRecord.document_id == DocumentRecord.id,
        )
        .where(DocumentRecord.expires_at <= func.now())
        .group_by(DocumentRecord.id)
        .order_by(DocumentRecord.expires_at, DocumentRecord.id)
        .limit(DOCUMENT_RETENTION_BATCH_SIZE)
    )
    return [
        ExpiredDocument(
            document_id=document_id,
            storage_bucket=storage_bucket,
            storage_object_keys=[
                storage_object_key,
                *markdown_object_keys,
                *docling_document_object_keys,
            ],
        )
        for (
            document_id,
            storage_bucket,
            storage_object_key,
            markdown_object_keys,
            docling_document_object_keys,
        ) in (await session.execute(statement)).all()
    ]


async def delete_document(*, session: AsyncSession, document_id: UUID) -> bool:
    """Delete one document and its cascading parses after object removal."""
    result = await session.execute(
        delete(DocumentRecord).where(DocumentRecord.id == document_id).returning(DocumentRecord.id)
    )
    return result.scalar_one_or_none() is not None


async def find_similar_document_chunks(
    *,
    session: AsyncSession,
    query_embedding: list[float],
    embedding_model: PydanticAIEmbeddingModel = DEFAULT_EMBEDDING_MODEL,
    limit: int = 5,
) -> list[DocumentSearchResult]:
    """Return exact cosine matches within one provider, model, and dimension."""
    dimensions = len(query_embedding)
    if not isinstance(embedding_model, PydanticAIEmbeddingModel):
        raise TypeError("embedding_model must be an approved embedding model")
    contract = EMBEDDING_MODEL_CONTRACTS[embedding_model]
    if dimensions != contract.dimensions:
        raise ValueError("Query embedding dimensions do not match the selected model")
    if not all(math.isfinite(value) for value in query_embedding):
        raise ValueError("Query embedding values must be finite")
    if not any(query_embedding):
        raise ValueError("Query embedding must not be a zero vector")
    if not 1 <= limit <= MAX_DOCUMENT_SEARCH_RESULTS:
        raise ValueError(f"Search limit must be between 1 and {MAX_DOCUMENT_SEARCH_RESULTS}")
    selected_model = embedding_model.model_name
    selected_provider = (
        EmbeddingProvider.SENTENCE_TRANSFORMERS
        if embedding_model is PydanticAIEmbeddingModel.DENSE_ON
        else EmbeddingProvider.PYDANTIC_AI_GATEWAY
    )

    query_vector = cast(literal(query_embedding, type_=Vector()), Vector(dimensions))
    distance = (
        cast(
            DocumentEmbeddingRecord.embedding,
            Vector(dimensions),
        )
        .cosine_distance(query_vector)
        .label("cosine_distance")
    )
    statement: Select[
        tuple[
            DocumentChunkRecord,
            UUID,
            DocumentEmbeddingRecord,
            float,
        ]
    ] = (
        select(
            DocumentChunkRecord,
            DocumentParseRecord.document_id,
            DocumentEmbeddingRecord,
            distance,
        )
        .join(
            DocumentParseRecord,
            DocumentParseRecord.id == DocumentChunkRecord.parse_id,
        )
        .join(
            DocumentEmbeddingRecord,
            DocumentEmbeddingRecord.chunk_id == DocumentChunkRecord.id,
        )
        .where(
            DocumentEmbeddingRecord.embedding_provider == selected_provider.value,
            DocumentEmbeddingRecord.embedding_model == selected_model,
            DocumentEmbeddingRecord.embedding_model_revision == contract.revision,
            DocumentEmbeddingRecord.embedding_dimensions == dimensions,
        )
        .order_by(distance, DocumentEmbeddingRecord.id)
        .limit(limit)
    )
    rows = (await session.execute(statement)).all()
    return [
        DocumentSearchResult(
            document_id=document_id,
            chunk_id=chunk.id,
            ordinal=chunk.ordinal,
            text=chunk.text,
            contextualized_text=chunk.contextualized_text,
            page_numbers=chunk.page_numbers,
            chunker_name=chunk.chunker_name,
            chunker_version=chunk.chunker_version,
            embedding_provider=EmbeddingProvider(embedding.embedding_provider),
            embedding_model=embedding.embedding_model,
            embedding_model_revision=embedding.embedding_model_revision,
            embedding_dimensions=embedding.embedding_dimensions,
            cosine_distance=float(cosine_distance),
        )
        for chunk, document_id, embedding, cosine_distance in rows
    ]
