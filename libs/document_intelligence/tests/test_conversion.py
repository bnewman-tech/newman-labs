"""Tests for document intake and deterministic chunking."""

import asyncio
import threading
from contextlib import suppress
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from docling_core.transforms.chunker.hierarchical_chunker import DocChunk, DocMeta
from docling_core.types.doc import DocItemLabel, DoclingDocument

from libs.docling.schemas import DoclingConversion
from libs.document_intelligence.conversion import _chunk_document, convert_document
from libs.document_intelligence.schemas import (
    ApprovedDocument,
    DocumentChunk,
    DocumentSecurityScan,
    SecurityVerdict,
)
from libs.document_intelligence.security import DocumentRejectedError

APPROVED_SECURITY_SCAN = DocumentSecurityScan(
    scanner_name="doc_firewall",
    scanner_version="newman-test-v1",
    verdict=SecurityVerdict.ALLOW,
    risk_score=0.0,
)


async def test_convert_document_rejects_invalid_pdf_signature() -> None:
    """Parsing never starts with a malformed PDF signature."""
    source = ApprovedDocument(
        document_id=uuid4(),
        original_filename="newman-sample.pdf",
        media_type="application/pdf",
        content=b"not-pdf",
        security_scan=APPROVED_SECURITY_SCAN,
    )

    with pytest.raises(DocumentRejectedError, match="signature"):
        await convert_document(source=source)


async def test_convert_document_skips_retrieval_work_by_default() -> None:
    """Basic extraction returns Docling evidence without loading the chunker."""
    document = DoclingDocument(name="newman-basic-extraction")
    document.add_text(label=DocItemLabel.TEXT, text="Newman basic extraction")
    converted = DoclingConversion(
        document=document,
        markdown="Newman basic extraction",
        page_count=1,
        version="2.119.0",
    )
    source = ApprovedDocument(
        document_id=uuid4(),
        original_filename="newman-basic.pdf",
        media_type="application/pdf",
        content=b"%PDF-1.7\nbasic",
        security_scan=APPROVED_SECURITY_SCAN,
    )

    with (
        patch(
            "libs.document_intelligence.conversion.convert_pdf",
            return_value=converted,
        ),
        patch("libs.document_intelligence.conversion._chunk_document") as chunk,
    ):
        result = await convert_document(source=source)

    assert result.document_id == source.document_id
    assert result.markdown == converted.markdown
    assert result.chunks == []
    chunk.assert_not_called()


def test_chunk_document_persists_docling_chunks_without_resplitting() -> None:
    """Docling owns chunk size, structure, merging, and contextualization."""
    document = DoclingDocument(name="newman-chunking")
    item = document.add_text(label=DocItemLabel.TEXT, text="A" * 2_500)
    docling_chunk = DocChunk(text=item.text, meta=DocMeta(doc_items=[item]))
    chunker = MagicMock()
    chunker.chunk.return_value = iter([docling_chunk])
    chunker.contextualize.return_value = f"Document heading\n{item.text}"
    chunker.tokenizer.count_tokens.return_value = 500
    with patch(
        "libs.document_intelligence.conversion._get_document_chunker",
        return_value=chunker,
    ):
        result = _chunk_document(source=document.model_dump_json().encode())

    assert len(result) == 1
    assert result[0].text == item.text
    assert result[0].contextualized_text == f"Document heading\n{item.text}"
    assert result[0].token_count == 500
    assert result[0].chunker_name == "docling_hybrid"
    assert result[0].chunker_version.startswith("tokenizer=lightonai/DenseOn@")
    assert "max_tokens=507" in result[0].chunker_version
    chunker.chunk.assert_called_once_with(dl_doc=document)
    chunker.contextualize.assert_called_once_with(chunk=docling_chunk)


async def test_cancellation_keeps_chunking_slot_until_thread_exits() -> None:
    """Cancellation cannot release chunking capacity while its thread runs."""
    worker_started = threading.Event()
    release_worker = threading.Event()
    calls = 0
    document = DoclingDocument(name="newman-chunk-cancellation")
    document.add_text(label=DocItemLabel.TEXT, text="Newman chunk cancellation")
    converted = DoclingConversion(
        document=document,
        markdown="Newman chunk cancellation",
        page_count=1,
        version="2.119.0",
    )
    first_source = ApprovedDocument(
        document_id=uuid4(),
        original_filename="newman-first.pdf",
        media_type="application/pdf",
        content=b"%PDF-1.7\nfirst",
        security_scan=APPROVED_SECURITY_SCAN,
    )
    second_source = ApprovedDocument(
        document_id=uuid4(),
        original_filename="newman-second.pdf",
        media_type="application/pdf",
        content=b"%PDF-1.7\nsecond",
        security_scan=APPROVED_SECURITY_SCAN,
    )

    def blocking_chunking(
        *,
        source: bytes | DoclingDocument,
    ) -> list[DocumentChunk]:
        nonlocal calls
        calls += 1
        worker_started.set()
        release_worker.wait(timeout=2)
        assert isinstance(source, DoclingDocument)
        text = "Newman chunk cancellation"
        return [
            DocumentChunk(
                ordinal=0,
                text=text,
                contextualized_text=text,
                token_count=4,
                content_sha256="b" * 64,
                chunker_name="docling_hybrid",
                chunker_version="newman-test-v1",
            )
        ]

    with (
        patch(
            "libs.document_intelligence.conversion.convert_pdf",
            return_value=converted,
        ),
        patch(
            "libs.document_intelligence.conversion._chunk_document",
            side_effect=blocking_chunking,
        ),
    ):
        first = asyncio.create_task(convert_document(source=first_source, index_for_search=True))
        assert await asyncio.to_thread(worker_started.wait, 1)
        first.cancel()
        with suppress(asyncio.CancelledError):
            await first

        second = asyncio.create_task(convert_document(source=second_source, index_for_search=True))
        await asyncio.sleep(0.05)
        assert calls == 1
        assert not second.done()

        release_worker.set()
        assert (await second).document_id == second_source.document_id
        assert calls == 2
