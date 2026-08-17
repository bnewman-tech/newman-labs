"""Local PostgreSQL tests for document persistence and vector retrieval."""

import hashlib
import math
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from libs.blob_storage.schemas import StoredBlob
from libs.database.crud.documents import (
    delete_document,
    find_similar_document_chunks,
    list_expired_documents,
    persist_document,
    persist_document_index,
)
from libs.database.functions import get_api_db_engine
from libs.database.models.document import DocumentRecord
from libs.database.models.document_embedding import DocumentEmbeddingRecord
from libs.database.models.document_parse import DocumentParseRecord
from libs.database.schemas import (
    DocumentPersistenceInput,
    StoredDocumentArtifacts,
)
from libs.document_intelligence.schemas import (
    ApprovedDocument,
    ConvertedDocument,
    DocumentChunk,
    DocumentSecurityScan,
    EmbeddedDocumentChunk,
    EmbeddingProvider,
    SecurityVerdict,
)
from libs.pydantic_ai_core.schemas import (
    EMBEDDING_MODEL_CONTRACTS,
    PydanticAIEmbeddingModel,
)


@pytest.mark.integration
async def test_document_persistence_and_exact_vector_search(  # ruff: ignore[too-many-locals, too-many-statements] - one transaction proves the complete lifecycle.
) -> None:
    """One transaction retains evidence and retrieves the closest chunk."""
    document_id = uuid4()
    content = b"%PDF-1.7\nnewman vector test"
    checksum = hashlib.sha256(content).hexdigest()
    source_chunks = [
        DocumentChunk(
            ordinal=0,
            text="newman closest evidence",
            contextualized_text="Closest section\nnewman closest evidence",
            token_count=7,
            content_sha256="a" * 64,
            page_numbers=[1],
            chunker_name="docling_hybrid",
            chunker_version="newman-test-v1",
        ),
        DocumentChunk(
            ordinal=1,
            text="newman farther evidence",
            contextualized_text="Farther section\nnewman farther evidence",
            token_count=7,
            content_sha256="b" * 64,
            page_numbers=[2],
            chunker_name="docling_hybrid",
            chunker_version="newman-test-v1",
        ),
    ]
    vector_one = [0.0] * 768
    vector_one[700] = 1.0
    vector_two = [0.0] * 768
    vector_two[700:702] = [0.8, 0.6]
    document_input = DocumentPersistenceInput(
        source=ApprovedDocument(
            document_id=document_id,
            original_filename="newman-vector-test.pdf",
            media_type="application/pdf",
            content=content,
            security_scan=DocumentSecurityScan(
                scanner_name="doc_firewall",
                scanner_version="newman-test-v1",
                verdict=SecurityVerdict.ALLOW,
                risk_score=0.0,
            ),
        ),
        stored=StoredDocumentArtifacts(
            original=StoredBlob(
                bucket="newman-labs",
                key=f"documents/{document_id}/original.pdf",
                content_type="application/pdf",
                content_sha256=checksum,
            ),
            markdown=StoredBlob(
                bucket="newman-labs",
                key=f"documents/{document_id}/parses/newman/document.md",
                content_type="text/markdown; charset=utf-8",
                content_sha256="c" * 64,
            ),
            docling_document=StoredBlob(
                bucket="newman-labs",
                key=f"documents/{document_id}/parses/newman/docling.json",
                content_type="application/json",
                content_sha256="d" * 64,
            ),
        ),
        converted=ConvertedDocument(
            document_id=document_id,
            content_sha256=checksum,
            page_count=2,
            parser_name="docling_pdf_accurate",
            parser_version="2.119.0",
            markdown="newman closest evidence\n\nnewman farther evidence",
            docling_document={"name": "newman-vector-test"},
            chunks=source_chunks,
        ),
        embedded_chunks=[
            EmbeddedDocumentChunk(
                **source_chunks[0].model_dump(),
                embedding=vector_one,
                embedding_provider=EmbeddingProvider.SENTENCE_TRANSFORMERS,
                embedding_model="lightonai/DenseOn",
                embedding_model_revision=EMBEDDING_MODEL_CONTRACTS[PydanticAIEmbeddingModel.DENSE_ON].revision,
                embedding_dimensions=768,
            ),
            EmbeddedDocumentChunk(
                **source_chunks[1].model_dump(),
                embedding=vector_two,
                embedding_provider=EmbeddingProvider.SENTENCE_TRANSFORMERS,
                embedding_model="lightonai/DenseOn",
                embedding_model_revision=EMBEDDING_MODEL_CONTRACTS[PydanticAIEmbeddingModel.DENSE_ON].revision,
                embedding_dimensions=768,
            ),
        ],
    )

    async with AsyncSession(get_api_db_engine(), expire_on_commit=False) as session:
        transaction = await session.begin()
        try:
            persisted = await persist_document(
                session=session,
                document_input=document_input,
            )
            with pytest.raises(ValueError, match="stored document chunks"):
                await persist_document_index(
                    session=session,
                    document_id=persisted.document_id,
                    parse_id=persisted.parse_id,
                    embedded_chunks=[
                        document_input.embedded_chunks[0].model_copy(update={"text": "newman mismatched evidence"}),
                        document_input.embedded_chunks[1],
                    ],
                )
            results = await find_similar_document_chunks(
                session=session,
                query_embedding=vector_one,
                limit=2,
            )

            assert (persisted.document_id, persisted.chunk_count) == (document_id, 2)
            assert persisted.storage_bucket == "newman-labs"
            assert (
                persisted.original_object_key.endswith("original.pdf"),
                persisted.markdown_object_key.endswith("document.md"),
            ) == (True, True)
            document_parse = await session.get(
                DocumentParseRecord,
                persisted.parse_id,
            )
            assert document_parse is not None
            assert document_parse.markdown_sha256 == "c" * 64
            assert document_parse.docling_document_sha256 == "d" * 64
            assert [result.ordinal for result in results] == [0, 1]
            assert results[0].cosine_distance == pytest.approx(0.0)
            assert results[0].text == "newman closest evidence"
            assert results[0].contextualized_text == ("Closest section\nnewman closest evidence")
            assert results[0].chunker_name == "docling_hybrid"
            assert results[0].embedding_dimensions == 768
            assert (
                results[0].embedding_model_revision
                == EMBEDDING_MODEL_CONTRACTS[PydanticAIEmbeddingModel.DENSE_ON].revision
            )

            gateway_vector = [0.0] * 1_536
            gateway_vector[1_500] = 1.0
            session.add(
                DocumentEmbeddingRecord(
                    chunk_id=results[0].chunk_id,
                    embedding_provider=EmbeddingProvider.PYDANTIC_AI_GATEWAY.value,
                    embedding_model="text-embedding-3-small",
                    embedding_model_revision="latest",
                    embedding_dimensions=1_536,
                    embedding=gateway_vector,
                )
            )
            await session.flush()
            alternate_results = await find_similar_document_chunks(
                session=session,
                query_embedding=gateway_vector,
                embedding_model=PydanticAIEmbeddingModel.TEXT_EMBEDDING_3_SMALL,
            )

            assert alternate_results[0].chunk_id == results[0].chunk_id
            assert alternate_results[0].embedding_dimensions == 1_536

            savepoint = await session.begin_nested()
            session.add(
                DocumentEmbeddingRecord(
                    chunk_id=results[0].chunk_id,
                    embedding_provider=(EmbeddingProvider.SENTENCE_TRANSFORMERS.value),
                    embedding_model="newman-invalid-model",
                    embedding_model_revision="newman-test-revision",
                    embedding_dimensions=3,
                    embedding=[1.0, 0.0],
                )
            )
            with pytest.raises(IntegrityError):
                await session.flush()
            await savepoint.rollback()

            document = await session.get(DocumentRecord, document_id)
            assert document is not None
            assert document.security_scan == {
                "scanner_name": "doc_firewall",
                "scanner_version": "newman-test-v1",
                "verdict": "allow",
                "risk_score": 0.0,
                "findings": [],
            }
            document.expires_at = datetime.now(tz=UTC) - timedelta(days=1)
            await session.flush()
            expired = await list_expired_documents(session=session)

            assert [item.document_id for item in expired] == [document_id]
            assert await delete_document(
                session=session,
                document_id=document_id,
            )
            await session.flush()
            assert await session.get(DocumentRecord, document_id) is None
            assert (
                await session.scalar(select(DocumentParseRecord).where(DocumentParseRecord.id == persisted.parse_id))
                is None
            )
        finally:
            await transaction.rollback()


@pytest.mark.parametrize(
    ("query_embedding", "limit", "match"),
    [
        ([math.nan, *([0.0] * 767)], 5, "finite"),
        ([math.inf, *([0.0] * 767)], 5, "finite"),
        ([0.0] * 768, 5, "zero vector"),
        ([1.0, *([0.0] * 767)], 0, "between 1 and 100"),
        ([1.0, *([0.0] * 767)], 101, "between 1 and 100"),
        ([1.0], 5, "dimensions"),
    ],
)
async def test_document_search_rejects_invalid_query_contract(
    query_embedding: list[float],
    limit: int,
    match: str,
) -> None:
    """Invalid vectors and unbounded result requests fail before SQL execution."""
    async with AsyncSession(get_api_db_engine(), expire_on_commit=False) as session:
        with pytest.raises(ValueError, match=match):
            await find_similar_document_chunks(
                session=session,
                query_embedding=query_embedding,
                limit=limit,
            )
