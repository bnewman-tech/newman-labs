"""Tests for document embedding contracts."""

import math
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from pydantic_ai import Embedder
from pydantic_ai.embeddings import TestEmbeddingModel

from libs.document_intelligence.embeddings import embed_document_chunks
from libs.document_intelligence.schemas import (
    DocumentChunk,
    EmbeddedDocumentChunk,
    EmbeddingProvider,
)
from libs.pydantic_ai_core.schemas import (
    EMBEDDING_MODEL_CONTRACTS,
    PydanticAIEmbeddingModel,
)


async def test_embed_document_chunks_preserves_evidence_order() -> None:
    """A deterministic provider result remains aligned with each chunk."""
    chunks = [
        DocumentChunk(
            ordinal=0,
            text="newman first evidence",
            contextualized_text="First section\nnewman first evidence",
            token_count=8,
            content_sha256="a" * 64,
            page_numbers=[1],
            chunker_name="docling_hybrid",
            chunker_version="newman-test-v1",
        ),
        DocumentChunk(
            ordinal=1,
            text="newman second evidence",
            contextualized_text="Second section\nnewman second evidence",
            token_count=8,
            content_sha256="b" * 64,
            page_numbers=[2],
            chunker_name="docling_hybrid",
            chunker_version="newman-test-v1",
        ),
    ]

    with patch(
        "libs.document_intelligence.embeddings.build_embedder",
        return_value=Embedder(
            TestEmbeddingModel(dimensions=EMBEDDING_MODEL_CONTRACTS[PydanticAIEmbeddingModel.DENSE_ON].dimensions)
        ),
    ):
        embedded = await embed_document_chunks(chunks=chunks)

    assert [chunk.ordinal for chunk in embedded] == [0, 1]
    assert all(chunk.embedding_provider is EmbeddingProvider.SENTENCE_TRANSFORMERS for chunk in embedded)
    assert all(
        chunk.embedding_model_revision == EMBEDDING_MODEL_CONTRACTS[PydanticAIEmbeddingModel.DENSE_ON].revision
        for chunk in embedded
    )
    assert all(chunk.embedding_model == "lightonai/DenseOn" for chunk in embedded)
    assert all(chunk.embedding_dimensions == 768 for chunk in embedded)
    assert all(len(chunk.embedding) == 768 for chunk in embedded)


async def test_embed_document_chunks_supports_gateway_openai() -> None:
    """The managed model records a distinct provider and vector contract."""
    chunk = DocumentChunk(
        ordinal=0,
        text="newman managed evidence",
        contextualized_text="Managed section\nnewman managed evidence",
        token_count=6,
        content_sha256="a" * 64,
        chunker_name="docling_hybrid",
        chunker_version="newman-test-v1",
    )
    model = PydanticAIEmbeddingModel.TEXT_EMBEDDING_3_SMALL
    with patch(
        "libs.document_intelligence.embeddings.build_embedder",
        return_value=Embedder(TestEmbeddingModel(dimensions=1_536)),
    ) as build_embedder:
        embedded = await embed_document_chunks(chunks=[chunk], model=model)

    build_embedder.assert_awaited_once_with(model=model)
    assert len(embedded) == 1
    assert embedded[0].embedding_provider is EmbeddingProvider.PYDANTIC_AI_GATEWAY
    assert embedded[0].embedding_model == "text-embedding-3-small"
    assert embedded[0].embedding_model_revision == "latest"
    assert embedded[0].embedding_dimensions == 1_536


async def test_embed_document_chunks_rejects_wrong_vector_width() -> None:
    """Provider drift cannot write an incompatible vector to PostgreSQL."""
    chunk = DocumentChunk(
        ordinal=0,
        text="newman evidence",
        contextualized_text="Newman section\nnewman evidence",
        token_count=6,
        content_sha256="a" * 64,
        chunker_name="docling_hybrid",
        chunker_version="newman-test-v1",
    )

    with (
        patch(
            "libs.document_intelligence.embeddings.build_embedder",
            return_value=Embedder(TestEmbeddingModel(dimensions=8)),
        ),
        pytest.raises(RuntimeError, match="dimension"),
    ):
        await embed_document_chunks(chunks=[chunk])


@pytest.mark.parametrize(
    ("embedding", "match"),
    [
        ([math.nan], "finite number"),
        ([math.inf], "finite number"),
        ([0.0], "zero vector"),
        ([1.0, 2.0], "declared dimensions"),
    ],
)
def test_embedded_chunk_rejects_invalid_vectors(
    embedding: list[float],
    match: str,
) -> None:
    """Invalid vectors cannot cross the persistence boundary."""
    chunk = DocumentChunk(
        ordinal=0,
        text="newman evidence",
        contextualized_text="Newman section\nnewman evidence",
        token_count=6,
        content_sha256="a" * 64,
        chunker_name="docling_hybrid",
        chunker_version="newman-test-v1",
    )

    with pytest.raises(ValidationError, match=match):
        EmbeddedDocumentChunk(
            **chunk.model_dump(),
            embedding=embedding,
            embedding_provider=EmbeddingProvider.SENTENCE_TRANSFORMERS,
            embedding_model="newman-test-model",
            embedding_model_revision="newman-test-revision",
            embedding_dimensions=1,
        )
