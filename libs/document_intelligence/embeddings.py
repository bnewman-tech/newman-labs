"""Local embeddings for deterministic document chunks."""

from libs.document_intelligence.schemas import (
    DocumentChunk,
    EmbeddedDocumentChunk,
    EmbeddingProvider,
)
from libs.pydantic_ai_core.functions import build_embedder
from libs.pydantic_ai_core.schemas import (
    DEFAULT_EMBEDDING_MODEL,
    EMBEDDING_MODEL_CONTRACTS,
    PydanticAIEmbeddingModel,
)


async def embed_document_chunks(
    *,
    chunks: list[DocumentChunk],
    model: PydanticAIEmbeddingModel = DEFAULT_EMBEDDING_MODEL,
) -> list[EmbeddedDocumentChunk]:
    """Embed a non-empty chunk batch and enforce the database vector width."""
    if not chunks:
        return []
    embedder = await build_embedder(model=model)
    result = await embedder.embed_documents([chunk.contextualized_text for chunk in chunks])
    if len(result.embeddings) != len(chunks):
        raise RuntimeError("The embedding provider returned an incomplete batch")

    contract = EMBEDDING_MODEL_CONTRACTS[model]
    embedded: list[EmbeddedDocumentChunk] = []
    for chunk, vector in zip(chunks, result.embeddings, strict=True):
        if len(vector) != contract.dimensions:
            raise RuntimeError("The embedding dimension does not match the database contract")
        embedded.append(
            EmbeddedDocumentChunk(
                **chunk.model_dump(),
                embedding=vector,
                embedding_provider=(
                    EmbeddingProvider.SENTENCE_TRANSFORMERS
                    if model is PydanticAIEmbeddingModel.DENSE_ON
                    else EmbeddingProvider.PYDANTIC_AI_GATEWAY
                ),
                embedding_model=model.model_name,
                embedding_model_revision=contract.revision,
                embedding_dimensions=len(vector),
            )
        )
    return embedded
