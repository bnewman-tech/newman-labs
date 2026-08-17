"""Shared Pydantic AI model construction."""

import asyncio
from functools import cache

from pydantic_ai import Embedder
from pydantic_ai.embeddings import EmbeddingSettings
from pydantic_ai.embeddings.openai import OpenAIEmbeddingModel
from pydantic_ai.models import Model, infer_model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.gateway import gateway_provider
from pydantic_ai.providers.ollama import OllamaProvider

from libs.prefect_utils.secrets import PrefectSecret, get_secret
from libs.pydantic_ai_core.observability import configure_logfire
from libs.pydantic_ai_core.schemas import (
    DEFAULT_EMBEDDING_MODEL,
    EMBEDDING_MODEL_CONTRACTS,
    PydanticAIEmbeddingModel,
    PydanticAIModel,
)

OLLAMA_BASE_URL = "https://ollama.com/v1"


async def build_agent_model(*, model: PydanticAIModel) -> Model:
    """Load the managed credential, then configure Logfire and build the model."""
    if not isinstance(model, PydanticAIModel):
        raise TypeError("model must be an approved Pydantic AI model")

    provider_name, model_name = model.value.split(":", maxsplit=1)
    if provider_name == "ollama":
        api_key = await get_secret(name=PrefectSecret.OLLAMA_API_KEY)
        await configure_logfire()
        return OpenAIChatModel(
            model_name=model_name,
            provider=OllamaProvider(
                base_url=OLLAMA_BASE_URL,
                api_key=api_key.get_secret_value(),
            ),
            profile={
                # All approved Ollama Cloud models advertise thinking support.
                "supports_thinking": True,
            },
        )

    api_key = await get_secret(name=PrefectSecret.PYDANTIC_AI_GATEWAY_API_KEY)
    await configure_logfire()
    return infer_model(
        model.value,
        provider_factory=lambda provider: gateway_provider(
            provider.removeprefix("gateway/"),
            api_key=api_key.get_secret_value(),
        ),
    )


@cache
def _create_local_embedder() -> Embedder:
    """Load the in-process SentenceTransformer model once and reuse it."""
    from pydantic_ai.embeddings.sentence_transformers import (  # ruff: ignore[import-outside-top-level] - Delay optional embedding imports until use.
        SentenceTransformerEmbeddingModel,
        SentenceTransformersEmbeddingSettings,
    )
    from sentence_transformers import (  # ruff: ignore[import-outside-top-level] - Delay optional embedding imports until use.
        SentenceTransformer,
    )

    contract = EMBEDDING_MODEL_CONTRACTS[PydanticAIEmbeddingModel.DENSE_ON]
    embedding_settings = SentenceTransformersEmbeddingSettings(
        sentence_transformers_device="cpu",
        sentence_transformers_normalize_embeddings=True,
    )
    model = SentenceTransformerEmbeddingModel(
        SentenceTransformer(
            PydanticAIEmbeddingModel.DENSE_ON.model_name,
            device="cpu",
            revision=contract.revision,
        ),
        settings=embedding_settings,
    )
    return Embedder(model, settings=embedding_settings)


async def build_embedder(
    *,
    model: PydanticAIEmbeddingModel = DEFAULT_EMBEDDING_MODEL,
) -> Embedder:
    """Configure Logfire, then build the selected local or managed embedder."""
    if not isinstance(model, PydanticAIEmbeddingModel):
        raise TypeError("model must be an approved Pydantic AI embedding model")

    if model is PydanticAIEmbeddingModel.DENSE_ON:
        await configure_logfire()
        return await asyncio.to_thread(_create_local_embedder)

    api_key = await get_secret(name=PrefectSecret.PYDANTIC_AI_GATEWAY_API_KEY)
    await configure_logfire()
    return Embedder(
        OpenAIEmbeddingModel(
            model.model_name,
            provider=gateway_provider(
                "openai",
                api_key=api_key.get_secret_value(),
            ),
        ),
        settings=EmbeddingSettings(dimensions=EMBEDDING_MODEL_CONTRACTS[model].dimensions),
    )
