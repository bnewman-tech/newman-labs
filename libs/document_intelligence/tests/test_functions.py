"""Integration tests for the complete document-processing workflow."""

import hashlib
import json
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from docling_core.types.doc import DocItemLabel, DoclingDocument
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.blob_storage.schemas import BlobContents, StoredBlob
from libs.database.functions import get_api_db_engine
from libs.database.models.document import DocumentRecord
from libs.database.models.document_chunk import DocumentChunkRecord
from libs.database.models.document_embedding import DocumentEmbeddingRecord
from libs.database.schemas import StoredDocumentArtifacts
from libs.document_intelligence import functions
from libs.document_intelligence.functions import (
    delete_expired_documents,
    index_document,
    process_document,
)
from libs.document_intelligence.schemas import (
    ApprovedDocument,
    ConvertedDocument,
    DocumentChunk,
    DocumentSecurityScan,
    DocumentUpload,
    EmbeddedDocumentChunk,
    EmbeddingProvider,
    SecurityVerdict,
)
from libs.document_intelligence.security import DocumentRejectedError
from libs.pydantic_ai_core.schemas import (
    DEFAULT_EMBEDDING_MODEL,
    EMBEDDING_MODEL_CONTRACTS,
    PydanticAIEmbeddingModel,
)


@dataclass(frozen=True, slots=True)
class DocumentScenario:
    """Complete deterministic input for one document workflow test."""

    source: DocumentUpload
    approved: ApprovedDocument
    converted: ConvertedDocument
    chunk: DocumentChunk
    embedded: EmbeddedDocumentChunk
    stored: StoredDocumentArtifacts


@pytest.fixture(autouse=True)
def disable_logfire_spans(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep unit tests independent from runtime Logfire configuration."""
    monkeypatch.setattr(functions.logfire, "span", Mock(return_value=nullcontext()))


@pytest.fixture
def document_scenario() -> DocumentScenario:
    """Build one unique, internally consistent document scenario."""
    document_id = uuid4()
    content = f"%PDF-1.7\nnewman document {document_id}".encode()
    source = DocumentUpload(
        document_id=document_id,
        original_filename="newman-document.pdf",
        media_type="application/pdf",
        content=content,
    )
    chunk = DocumentChunk(
        ordinal=0,
        text="newman document evidence",
        contextualized_text="Evidence\nnewman document evidence",
        token_count=6,
        content_sha256="a" * 64,
        page_numbers=[1],
        chunker_name="docling_hybrid",
        chunker_version="newman-test-v1",
    )
    content_sha256 = hashlib.sha256(content).hexdigest()
    converted = ConvertedDocument(
        document_id=document_id,
        content_sha256=content_sha256,
        page_count=1,
        parser_name="docling_pdf_accurate",
        parser_version="newman-test-v1",
        markdown="newman document evidence",
        docling_document={"name": "newman-document"},
        chunks=[chunk],
    )
    return DocumentScenario(
        source=source,
        approved=ApprovedDocument(
            **source.model_dump(),
            security_scan=DocumentSecurityScan(
                scanner_name="doc_firewall",
                scanner_version="newman-test-v1",
                verdict=SecurityVerdict.ALLOW,
                risk_score=0.0,
            ),
        ),
        converted=converted,
        chunk=chunk,
        embedded=EmbeddedDocumentChunk(
            **chunk.model_dump(),
            embedding=[1.0, *([0.0] * 767)],
            embedding_provider=EmbeddingProvider.SENTENCE_TRANSFORMERS,
            embedding_model="lightonai/DenseOn",
            embedding_model_revision=EMBEDDING_MODEL_CONTRACTS[PydanticAIEmbeddingModel.DENSE_ON].revision,
            embedding_dimensions=768,
        ),
        stored=StoredDocumentArtifacts(
            original=StoredBlob(
                bucket="newman-labs",
                key=f"documents/{document_id}/original.pdf",
                content_type="application/pdf",
                content_sha256=content_sha256,
                etag='"newman-original-etag"',
            ),
            markdown=StoredBlob(
                bucket="newman-labs",
                key=f"documents/{document_id}/parses/newman/document.md",
                content_type="text/markdown; charset=utf-8",
                content_sha256="b" * 64,
                etag='"newman-markdown-etag"',
            ),
            docling_document=StoredBlob(
                bucket="newman-labs",
                key=f"documents/{document_id}/parses/newman/docling.json",
                content_type="application/json",
                content_sha256="c" * 64,
                etag='"newman-docling-etag"',
            ),
        ),
    )


async def test_process_document_rejects_before_any_downstream_work(
    monkeypatch: pytest.MonkeyPatch,
    document_scenario: DocumentScenario,
) -> None:
    """A failed security scan cannot reach the database, parser, or storage."""
    approve_document = AsyncMock(side_effect=DocumentRejectedError("newman security rejection"))
    convert_document = AsyncMock()
    create_blobs = AsyncMock()
    monkeypatch.setattr(functions, "approve_document", approve_document)
    monkeypatch.setattr(functions, "convert_document", convert_document)
    monkeypatch.setattr(functions, "create_blobs", create_blobs)

    with pytest.raises(DocumentRejectedError, match="security rejection"):
        await process_document(source=document_scenario.source)

    convert_document.assert_not_awaited()
    create_blobs.assert_not_awaited()


@pytest.mark.integration
async def test_process_document_reuses_and_indexes_saved_content(  # ruff: ignore[too-many-locals, too-many-statements] - One lifecycle proves parse and chunk reuse across embedding models.
    monkeypatch: pytest.MonkeyPatch,
    document_scenario: DocumentScenario,
) -> None:
    """Basic extraction returns retained evidence without repeat conversion."""
    convert_document = AsyncMock(return_value=document_scenario.converted.model_copy(update={"chunks": []}))
    embed_document_chunks = AsyncMock()
    create_blobs = AsyncMock(
        return_value=[
            document_scenario.stored.original,
            document_scenario.stored.markdown,
            document_scenario.stored.docling_document,
        ]
    )
    delete_blob = AsyncMock()
    read_blob = AsyncMock(
        side_effect=[
            BlobContents(
                **document_scenario.stored.markdown.model_dump(exclude={"content_sha256"}),
                content=document_scenario.converted.markdown.encode(),
                content_sha256=document_scenario.stored.markdown.content_sha256,
            ),
            BlobContents(
                **document_scenario.stored.docling_document.model_dump(exclude={"content_sha256"}),
                content=json.dumps(document_scenario.converted.docling_document).encode(),
                content_sha256=document_scenario.stored.docling_document.content_sha256,
            ),
        ]
    )
    approve_document = AsyncMock(return_value=document_scenario.approved)
    monkeypatch.setattr(functions, "approve_document", approve_document)
    monkeypatch.setattr(functions, "convert_document", convert_document)
    monkeypatch.setattr(functions, "embed_document_chunks", embed_document_chunks)
    monkeypatch.setattr(functions, "create_blobs", create_blobs)
    monkeypatch.setattr(functions, "delete_blob", delete_blob)
    monkeypatch.setattr(functions, "read_blob", read_blob)

    first = await process_document(source=document_scenario.source)
    repeated = await process_document(source=document_scenario.source.model_copy(update={"document_id": uuid4()}))

    assert first.document_id == document_scenario.source.document_id
    assert first.markdown_object_key == document_scenario.stored.markdown.key
    assert repeated == first
    assert repeated.markdown == document_scenario.converted.markdown
    assert repeated.docling_document == document_scenario.converted.docling_document
    assert approve_document.await_count == 2
    assert first.chunk_count == 0
    convert_document.assert_awaited_once_with(
        source=document_scenario.approved,
        index_for_search=False,
    )
    embed_document_chunks.assert_not_awaited()
    create_blobs.assert_awaited_once()
    delete_blob.assert_not_awaited()
    assert {call.kwargs["key"] for call in read_blob.await_args_list} == {
        document_scenario.stored.markdown.key,
        document_scenario.stored.docling_document.key,
    }
    async with AsyncSession(get_api_db_engine(), expire_on_commit=False) as session:
        document = await session.get(DocumentRecord, first.document_id)
        assert document is not None
        assert document.status == "converted"

    stored_docling_document = DoclingDocument(name="newman-stored-document")
    stored_docling_document.add_text(
        label=DocItemLabel.TEXT,
        text=document_scenario.chunk.text,
    )
    stored_content = stored_docling_document.model_dump_json().encode()
    read_blob = AsyncMock(
        return_value=BlobContents(
            **document_scenario.stored.docling_document.model_dump(exclude={"content_sha256"}),
            content=stored_content,
            content_sha256=hashlib.sha256(stored_content).hexdigest(),
        )
    )
    chunk_document = AsyncMock(return_value=[document_scenario.chunk])
    embed_document_chunks.return_value = [document_scenario.embedded]
    monkeypatch.setattr(functions, "read_blob", read_blob)
    monkeypatch.setattr(functions, "chunk_document", chunk_document)

    indexed = await index_document(document_id=first.document_id)
    reused_index = await index_document(document_id=first.document_id)
    gateway_model = PydanticAIEmbeddingModel.TEXT_EMBEDDING_3_SMALL
    embed_document_chunks.return_value = [
        document_scenario.embedded.model_copy(
            update={
                "embedding": [1.0, *([0.0] * 1_535)],
                "embedding_provider": EmbeddingProvider.PYDANTIC_AI_GATEWAY,
                "embedding_model": "text-embedding-3-small",
                "embedding_model_revision": "latest",
                "embedding_dimensions": 1_536,
            }
        )
    ]
    gateway_index = await index_document(
        document_id=first.document_id,
        embedding_model=gateway_model,
    )
    reused_gateway_index = await index_document(
        document_id=first.document_id,
        embedding_model=gateway_model,
    )

    assert indexed.document_id == first.document_id
    assert indexed.parse_id == first.parse_id
    assert indexed.chunk_count == 1
    assert reused_index == indexed
    assert gateway_index == indexed
    assert reused_gateway_index == indexed
    read_blob.assert_awaited_once_with(
        bucket=first.storage_bucket,
        key=first.docling_document_object_key,
    )
    chunk_document.assert_awaited_once_with(source=stored_content)
    assert [call.kwargs for call in embed_document_chunks.await_args_list] == [
        {"chunks": [document_scenario.chunk], "model": DEFAULT_EMBEDDING_MODEL},
        {"chunks": [document_scenario.chunk], "model": gateway_model},
    ]
    async with AsyncSession(get_api_db_engine(), expire_on_commit=False) as session:
        document = await session.get(DocumentRecord, first.document_id)
        assert document is not None
        assert document.status == "embedded"
        embedding_count = await session.scalar(
            select(func.count(DocumentEmbeddingRecord.id))
            .join(
                DocumentChunkRecord,
                DocumentChunkRecord.id == DocumentEmbeddingRecord.chunk_id,
            )
            .where(DocumentChunkRecord.parse_id == first.parse_id)
        )
        assert embedding_count == 2


@pytest.mark.integration
async def test_process_document_indexes_only_when_requested(
    monkeypatch: pytest.MonkeyPatch,
    document_scenario: DocumentScenario,
) -> None:
    """Indexed research adds Docling chunks and model embeddings."""
    convert_document = AsyncMock(return_value=document_scenario.converted)
    embed_document_chunks = AsyncMock(return_value=[document_scenario.embedded])
    monkeypatch.setattr(
        functions,
        "approve_document",
        AsyncMock(return_value=document_scenario.approved),
    )
    monkeypatch.setattr(functions, "convert_document", convert_document)
    monkeypatch.setattr(functions, "embed_document_chunks", embed_document_chunks)
    monkeypatch.setattr(
        functions,
        "create_blobs",
        AsyncMock(
            return_value=[
                document_scenario.stored.original,
                document_scenario.stored.markdown,
                document_scenario.stored.docling_document,
            ]
        ),
    )

    persisted = await process_document(
        source=document_scenario.source,
        index_for_search=True,
    )

    assert persisted.chunk_count == 1
    convert_document.assert_awaited_once_with(
        source=document_scenario.approved,
        index_for_search=True,
    )
    embed_document_chunks.assert_awaited_once_with(
        chunks=[document_scenario.chunk],
        model=DEFAULT_EMBEDDING_MODEL,
    )
    async with AsyncSession(get_api_db_engine(), expire_on_commit=False) as session:
        document = await session.get(DocumentRecord, persisted.document_id)
        assert document is not None
        assert document.status == "embedded"


@pytest.mark.integration
async def test_process_document_deletes_blob_when_persistence_fails(
    monkeypatch: pytest.MonkeyPatch,
    document_scenario: DocumentScenario,
) -> None:
    """A database failure cannot leave an untracked private original behind."""
    monkeypatch.setattr(
        functions,
        "approve_document",
        AsyncMock(return_value=document_scenario.approved),
    )
    monkeypatch.setattr(
        functions,
        "convert_document",
        AsyncMock(return_value=document_scenario.converted),
    )
    monkeypatch.setattr(
        functions,
        "embed_document_chunks",
        AsyncMock(return_value=[document_scenario.embedded]),
    )
    monkeypatch.setattr(
        functions,
        "create_blobs",
        AsyncMock(
            return_value=[
                document_scenario.stored.original,
                document_scenario.stored.markdown,
                document_scenario.stored.docling_document,
            ]
        ),
    )
    monkeypatch.setattr(
        functions,
        "persist_document",
        AsyncMock(side_effect=RuntimeError("newman persistence failure")),
    )
    delete_blob = AsyncMock()
    monkeypatch.setattr(functions, "delete_blob", delete_blob)

    with pytest.raises(RuntimeError, match="newman persistence failure"):
        await process_document(
            source=document_scenario.source,
            index_for_search=True,
        )

    assert [call.kwargs["key"] for call in delete_blob.await_args_list] == [
        document_scenario.stored.docling_document.key,
        document_scenario.stored.markdown.key,
        document_scenario.stored.original.key,
    ]


@pytest.mark.integration
async def test_process_document_relies_on_storage_batch_rollback(
    monkeypatch: pytest.MonkeyPatch,
    document_scenario: DocumentScenario,
) -> None:
    """The blob boundary owns cleanup when its atomic batch cannot complete."""
    monkeypatch.setattr(
        functions,
        "approve_document",
        AsyncMock(return_value=document_scenario.approved),
    )
    monkeypatch.setattr(
        functions,
        "convert_document",
        AsyncMock(return_value=document_scenario.converted),
    )
    monkeypatch.setattr(
        functions,
        "embed_document_chunks",
        AsyncMock(return_value=[document_scenario.embedded]),
    )
    monkeypatch.setattr(
        functions,
        "create_blobs",
        AsyncMock(side_effect=RuntimeError("newman storage failure")),
    )
    delete_blob = AsyncMock()
    monkeypatch.setattr(functions, "delete_blob", delete_blob)

    with pytest.raises(RuntimeError, match="newman storage failure"):
        await process_document(
            source=document_scenario.source,
            index_for_search=True,
        )

    delete_blob.assert_not_awaited()


@pytest.mark.integration
async def test_delete_expired_documents_removes_objects_and_database_records(
    monkeypatch: pytest.MonkeyPatch,
    document_scenario: DocumentScenario,
) -> None:
    """Retention cleanup removes private objects before database records."""
    monkeypatch.setattr(
        functions,
        "approve_document",
        AsyncMock(return_value=document_scenario.approved),
    )
    monkeypatch.setattr(
        functions,
        "convert_document",
        AsyncMock(return_value=document_scenario.converted),
    )
    monkeypatch.setattr(
        functions,
        "embed_document_chunks",
        AsyncMock(return_value=[document_scenario.embedded]),
    )
    monkeypatch.setattr(
        functions,
        "create_blobs",
        AsyncMock(
            return_value=[
                document_scenario.stored.original,
                document_scenario.stored.markdown,
                document_scenario.stored.docling_document,
            ]
        ),
    )
    delete_blob = AsyncMock()
    monkeypatch.setattr(functions, "delete_blob", delete_blob)
    persisted = await process_document(
        source=document_scenario.source,
        index_for_search=True,
    )

    async with (
        AsyncSession(get_api_db_engine(), expire_on_commit=False) as session,
        session.begin(),
    ):
        document = await session.get(DocumentRecord, persisted.document_id)
        assert document is not None
        document.expires_at = datetime.now(tz=UTC) - timedelta(seconds=1)

    assert await delete_expired_documents() == 1
    assert [call.kwargs["key"] for call in delete_blob.await_args_list] == [
        document_scenario.stored.original.key,
        document_scenario.stored.markdown.key,
        document_scenario.stored.docling_document.key,
    ]
    async with AsyncSession(get_api_db_engine(), expire_on_commit=False) as session:
        assert await session.get(DocumentRecord, persisted.document_id) is None
