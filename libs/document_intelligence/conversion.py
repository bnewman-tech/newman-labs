"""Bounded Docling conversion for approved PDF documents."""

from __future__ import annotations

import asyncio
import hashlib
from functools import cache
from typing import TYPE_CHECKING

from libs.docling.functions import convert_pdf
from libs.document_intelligence.schemas import (
    ApprovedDocument,
    ConvertedDocument,
    DocumentChunk,
)
from libs.document_intelligence.security import (
    DocumentRejectedError,
    validate_document,
)
from libs.document_intelligence.settings import (
    DOCUMENT_CHUNK_MAX_TOKENS,
    DOCUMENT_CHUNKER_NAME,
    DOCUMENT_CHUNKER_VERSION,
)
from libs.pydantic_ai_core.schemas import (
    DEFAULT_EMBEDDING_MODEL,
    EMBEDDING_MODEL_CONTRACTS,
)

if TYPE_CHECKING:
    from docling.chunking import HybridChunker
    from docling_core.types.doc import DoclingDocument

_chunking_slots = asyncio.Semaphore(1)
_chunking_tasks: set[asyncio.Task[list[DocumentChunk]]] = set()


@cache
def _get_document_chunker() -> HybridChunker:
    """Build Docling's native chunker with its fixed local tokenizer."""
    from docling.chunking import (  # ruff: ignore[import-outside-top-level] - Indexed research alone pays the tokenizer startup cost.
        HybridChunker,
    )
    from docling_core.transforms.chunker.tokenizer.huggingface import (  # ruff: ignore[import-outside-top-level] - Indexed research alone pays the tokenizer startup cost.
        HuggingFaceTokenizer,
    )
    from transformers.models.auto.tokenization_auto import (  # ruff: ignore[import-outside-top-level] - Indexed research alone pays the tokenizer startup cost.
        AutoTokenizer,
    )

    tokenizer = AutoTokenizer.from_pretrained(
        DEFAULT_EMBEDDING_MODEL.model_name,
        revision=EMBEDDING_MODEL_CONTRACTS[DEFAULT_EMBEDDING_MODEL].revision,
    )
    return HybridChunker(
        tokenizer=HuggingFaceTokenizer(
            tokenizer=tokenizer,
            # The embedder adds its document prompt and special tokens later.
            max_tokens=DOCUMENT_CHUNK_MAX_TOKENS,
        ),
    )


async def convert_document(
    *,
    source: ApprovedDocument,
    index_for_search: bool = False,
) -> ConvertedDocument:
    """Validate and convert one PDF, optionally preparing retrieval chunks."""
    validate_document(source=source)
    converted = await convert_pdf(
        source=source.content,
        filename=f"{source.document_id}.pdf",
    )
    chunks = await chunk_document(source=converted.document) if index_for_search else []
    return ConvertedDocument(
        document_id=source.document_id,
        content_sha256=hashlib.sha256(source.content).hexdigest(),
        page_count=converted.page_count,
        parser_name="docling_pdf_accurate",
        parser_version=converted.version,
        markdown=converted.markdown,
        docling_document=converted.document.export_to_dict(),
        chunks=chunks,
    )


async def chunk_document(
    *,
    source: bytes | DoclingDocument,
) -> list[DocumentChunk]:
    """Create retrieval chunks from a live or previously stored Docling document."""
    await _chunking_slots.acquire()
    task = asyncio.create_task(
        asyncio.to_thread(
            _chunk_document,
            source=source,
        )
    )
    _chunking_tasks.add(task)

    def chunking_finished(
        completed_task: asyncio.Task[list[DocumentChunk]],
    ) -> None:
        _chunking_slots.release()
        _chunking_tasks.discard(completed_task)
        if not completed_task.cancelled():
            completed_task.exception()

    task.add_done_callback(chunking_finished)
    return await asyncio.shield(task)


def _chunk_document(
    *,
    source: bytes | DoclingDocument,
) -> list[DocumentChunk]:
    from docling_core.transforms.chunker.hierarchical_chunker import (  # ruff: ignore[import-outside-top-level] - Imported with the cached chunker on first use.
        DocChunk,
    )
    from docling_core.types.doc import (  # ruff: ignore[import-outside-top-level] - Imported with the cached chunker on first use.
        DoclingDocument,
    )

    document = DoclingDocument.model_validate_json(source) if isinstance(source, bytes) else source
    chunker = _get_document_chunker()
    chunks: list[DocumentChunk] = []
    for base_chunk in chunker.chunk(dl_doc=document):
        docling_chunk = DocChunk.model_validate(base_chunk)
        text = docling_chunk.text.strip()
        contextualized_text = chunker.contextualize(chunk=docling_chunk).strip()
        if not text or not contextualized_text:
            continue
        page_numbers = sorted({provenance.page_no for item in docling_chunk.meta.doc_items for provenance in item.prov})
        chunks.append(
            DocumentChunk(
                ordinal=len(chunks),
                text=text,
                contextualized_text=contextualized_text,
                token_count=chunker.tokenizer.count_tokens(contextualized_text),
                content_sha256=hashlib.sha256(text.encode()).hexdigest(),
                page_numbers=page_numbers,
                chunker_name=DOCUMENT_CHUNKER_NAME,
                chunker_version=DOCUMENT_CHUNKER_VERSION,
            )
        )

    if not chunks:
        raise DocumentRejectedError("Docling produced no retrieval chunks")
    return chunks
