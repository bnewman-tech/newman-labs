"""Tests for shared Pydantic AI provider construction."""

from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import SecretStr
from pydantic_ai.embeddings.openai import OpenAIEmbeddingModel
from pydantic_ai.embeddings.sentence_transformers import (
    SentenceTransformerEmbeddingModel,
)
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

from libs.prefect_utils.secrets import PrefectSecret
from libs.pydantic_ai_core import functions
from libs.pydantic_ai_core.functions import build_embedder
from libs.pydantic_ai_core.schemas import (
    EMBEDDING_MODEL_CONTRACTS,
    EmbeddingModelContract,
    PydanticAIEmbeddingModel,
    PydanticAIModel,
)


async def test_build_agent_model_builds_ollama_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chat construction loads its credential directly from Prefect."""
    get_secret = AsyncMock(return_value=SecretStr("newman-test-key"))
    configure_logfire = AsyncMock()
    monkeypatch.setattr(functions, "get_secret", get_secret)
    monkeypatch.setattr(
        functions,
        "configure_logfire",
        configure_logfire,
    )

    model = await functions.build_agent_model(model=PydanticAIModel.KIMI_K2_7_CODE)

    assert model.model_name == "kimi-k2.7-code:cloud"
    assert model.base_url == "https://ollama.com/v1/"
    assert model.profile["supports_thinking"] is True
    configure_logfire.assert_awaited_once_with()
    get_secret.assert_awaited_once_with(name=PrefectSecret.OLLAMA_API_KEY)


async def test_build_agent_model_builds_gateway_openai_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Gateway construction uses the approved route and managed credential."""
    managed_value = "newman-test-key"
    get_secret = AsyncMock(return_value=SecretStr(managed_value))
    configure_logfire = AsyncMock()
    create_provider = MagicMock(
        return_value=OpenAIProvider(
            base_url="https://gateway-us.pydantic.dev/proxy/openai/",
            api_key=managed_value,
        )
    )
    monkeypatch.setattr(functions, "get_secret", get_secret)
    monkeypatch.setattr(functions, "gateway_provider", create_provider)
    monkeypatch.setattr(
        functions,
        "configure_logfire",
        configure_logfire,
    )

    model = await functions.build_agent_model(model=PydanticAIModel.GPT_5_6_TERRA)

    assert isinstance(model, OpenAIResponsesModel)
    assert model.model_name == "gpt-5.6-terra"
    assert model.base_url == "https://gateway-us.pydantic.dev/proxy/openai/"
    create_provider.assert_called_once_with(
        "openai",
        api_key=managed_value,
    )
    configure_logfire.assert_awaited_once_with()
    get_secret.assert_awaited_once_with(name=PrefectSecret.PYDANTIC_AI_GATEWAY_API_KEY)


async def test_build_agent_model_builds_gateway_google_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Google Gateway construction uses its current route and credential."""
    managed_value = "newman-test-key"
    get_secret = AsyncMock(return_value=SecretStr(managed_value))
    configure_logfire = AsyncMock()
    create_provider = MagicMock(
        return_value=functions.gateway_provider(
            "google-cloud",
            api_key=managed_value,
            base_url="https://gateway-us.pydantic.dev/proxy",
        )
    )
    monkeypatch.setattr(functions, "get_secret", get_secret)
    monkeypatch.setattr(functions, "gateway_provider", create_provider)
    monkeypatch.setattr(
        functions,
        "configure_logfire",
        configure_logfire,
    )

    model = await functions.build_agent_model(model=PydanticAIModel.GEMINI_3_7_FLASH)

    assert isinstance(model, GoogleModel)
    assert model.model_name == "gemini-3.7-flash"
    create_provider.assert_called_once_with(
        "google-cloud",
        api_key=managed_value,
    )
    configure_logfire.assert_awaited_once_with()
    get_secret.assert_awaited_once_with(name=PrefectSecret.PYDANTIC_AI_GATEWAY_API_KEY)


def test_models_match_the_current_approved_catalog() -> None:
    """The model enum carries approved provider-qualified identifiers."""
    assert {model.value for model in PydanticAIModel} == {
        "ollama:deepseek-v4-flash:cloud",
        "ollama:deepseek-v4-pro:cloud",
        "ollama:gemma4:31b-cloud",
        "ollama:glm-5.2:cloud",
        "ollama:kimi-k2.6:cloud",
        "ollama:kimi-k2.7-code:cloud",
        "ollama:kimi-k3:cloud",
        "ollama:minimax-m3:cloud",
        "ollama:qwen3.5:cloud",
        "gateway/openai:gpt-5.6-luna",
        "gateway/openai:gpt-5.6-terra",
        "gateway/openai:gpt-5.6-sol",
        "gateway/google-cloud:gemini-3.7-flash",
    }
    assert {model.value for model in PydanticAIEmbeddingModel} == {
        "sentence-transformers:lightonai/DenseOn",
        "gateway/openai:text-embedding-3-small",
    }
    assert PydanticAIEmbeddingModel.DENSE_ON.model_name == "lightonai/DenseOn"
    assert PydanticAIEmbeddingModel.TEXT_EMBEDDING_3_SMALL.model_name == "text-embedding-3-small"
    assert set(EMBEDDING_MODEL_CONTRACTS) == set(PydanticAIEmbeddingModel)
    dense_on = EMBEDDING_MODEL_CONTRACTS[PydanticAIEmbeddingModel.DENSE_ON]
    assert dense_on.dimensions == 768
    assert len(dense_on.revision) == 40
    assert set(dense_on.revision) <= set("0123456789abcdef")
    assert EMBEDDING_MODEL_CONTRACTS[PydanticAIEmbeddingModel.TEXT_EMBEDDING_3_SMALL] == EmbeddingModelContract(
        dimensions=1_536, revision="latest"
    )


async def test_build_embedder_uses_approved_local_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Embedding construction fixes the local model contract."""
    configure_logfire = AsyncMock()
    monkeypatch.setattr(functions, "configure_logfire", configure_logfire)

    embedder = await build_embedder(model=PydanticAIEmbeddingModel.DENSE_ON)

    model = embedder.model
    assert isinstance(model, SentenceTransformerEmbeddingModel)
    assert model.model_name == "lightonai/DenseOn"
    assert embedder is await build_embedder(model=PydanticAIEmbeddingModel.DENSE_ON)
    assert configure_logfire.await_count == 2


def test_create_local_embedder_pins_dense_on_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The local loader requests the pinned Hugging Face commit, not `main`."""

    class FakeSentenceTransformer:
        def __init__(self, name: str, *, device: str, revision: str) -> None:
            self.model_name = name
            self.device = device
            self.revision = revision
            self.model_card_data = MagicMock(
                model_id=name,
                base_model=None,
            )

        def __deepcopy__(self, _memo: object) -> object:
            return self

    constructor = MagicMock(side_effect=FakeSentenceTransformer)
    monkeypatch.setattr("sentence_transformers.SentenceTransformer", constructor)
    functions._create_local_embedder.cache_clear()
    try:
        embedder = functions._create_local_embedder()
    finally:
        functions._create_local_embedder.cache_clear()

    contract = EMBEDDING_MODEL_CONTRACTS[PydanticAIEmbeddingModel.DENSE_ON]
    constructor.assert_called_once_with(
        PydanticAIEmbeddingModel.DENSE_ON.model_name,
        device="cpu",
        revision=contract.revision,
    )
    assert isinstance(embedder.model, SentenceTransformerEmbeddingModel)
    assert embedder.model.model_name == "lightonai/DenseOn"


async def test_build_embedder_loads_local_model_off_the_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first local model load runs in a worker thread."""
    embedder = MagicMock()
    to_thread = AsyncMock(return_value=embedder)
    monkeypatch.setattr(functions, "configure_logfire", AsyncMock())
    monkeypatch.setattr(functions.asyncio, "to_thread", to_thread)

    assert await build_embedder(model=PydanticAIEmbeddingModel.DENSE_ON) is embedder
    to_thread.assert_awaited_once_with(functions._create_local_embedder)


async def test_build_embedder_builds_gateway_openai_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Managed embeddings use the Gateway credential without mutating environment."""
    managed_value = "newman-test-key"
    get_secret = AsyncMock(return_value=SecretStr(managed_value))
    create_provider = MagicMock(
        return_value=OpenAIProvider(
            base_url="https://gateway-us.pydantic.dev/proxy/openai/",
            api_key=managed_value,
        )
    )
    monkeypatch.setattr(functions, "get_secret", get_secret)
    monkeypatch.setattr(functions, "gateway_provider", create_provider)
    monkeypatch.setattr(functions, "configure_logfire", AsyncMock())

    embedder = await build_embedder(model=PydanticAIEmbeddingModel.TEXT_EMBEDDING_3_SMALL)

    assert isinstance(embedder.model, OpenAIEmbeddingModel)
    assert embedder.model.model_name == "text-embedding-3-small"
    assert embedder.model.base_url == "https://gateway-us.pydantic.dev/proxy/openai/"
    create_provider.assert_called_once_with("openai", api_key=managed_value)
    get_secret.assert_awaited_once_with(name=PrefectSecret.PYDANTIC_AI_GATEWAY_API_KEY)


async def test_build_embedder_rejects_an_unapproved_model() -> None:
    """Embedding construction rejects values outside the approved enum."""
    with pytest.raises(TypeError, match="approved Pydantic AI embedding model"):
        await build_embedder(model=cast("PydanticAIEmbeddingModel", "unapproved"))


async def test_build_agent_model_propagates_secret_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chat construction fails when its required Prefect block is unavailable."""
    get_secret = AsyncMock(side_effect=RuntimeError("missing Ollama secret"))
    monkeypatch.setattr(functions, "get_secret", get_secret)
    monkeypatch.setattr(
        functions,
        "configure_logfire",
        AsyncMock(),
    )

    with pytest.raises(RuntimeError, match="missing Ollama secret"):
        await functions.build_agent_model(model=PydanticAIModel.KIMI_K2_7_CODE)


async def test_build_agent_model_rejects_an_unapproved_model() -> None:
    """Model construction rejects values outside the approved enums."""
    with pytest.raises(TypeError, match="approved Pydantic AI model"):
        await functions.build_agent_model(model=cast("PydanticAIModel", "unapproved"))
