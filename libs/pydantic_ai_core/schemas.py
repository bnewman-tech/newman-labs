"""Pydantic AI model contracts."""

from enum import StrEnum
from typing import NamedTuple


class ThinkingLevel(StrEnum):
    """Thinking levels supported by every approved Newman Labs provider."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PydanticAIModel(StrEnum):
    """Provider-qualified models approved for Newman Labs agents."""

    DEEPSEEK_V4_FLASH = "ollama:deepseek-v4-flash:cloud"
    DEEPSEEK_V4_PRO = "ollama:deepseek-v4-pro:cloud"
    GEMMA4_31B_CLOUD = "ollama:gemma4:31b-cloud"
    GLM_5_2 = "ollama:glm-5.2:cloud"
    KIMI_K2_6 = "ollama:kimi-k2.6:cloud"
    KIMI_K2_7_CODE = "ollama:kimi-k2.7-code:cloud"
    KIMI_K3 = "ollama:kimi-k3:cloud"
    MINIMAX_M3 = "ollama:minimax-m3:cloud"
    QWEN_3_5 = "ollama:qwen3.5:cloud"
    GPT_5_6_LUNA = "gateway/openai:gpt-5.6-luna"
    GPT_5_6_TERRA = "gateway/openai:gpt-5.6-terra"
    GPT_5_6_SOL = "gateway/openai:gpt-5.6-sol"
    GEMINI_3_7_FLASH = "gateway/google-cloud:gemini-3.7-flash"


class PydanticAIEmbeddingModel(StrEnum):
    """Provider-qualified embedding models approved for Newman Labs retrieval."""

    DENSE_ON = "sentence-transformers:lightonai/DenseOn"
    TEXT_EMBEDDING_3_SMALL = "gateway/openai:text-embedding-3-small"

    @property
    def model_name(self) -> str:
        """Unqualified model id stored with embeddings and passed to providers."""
        return self.value.split(":", maxsplit=1)[1]


DEFAULT_EMBEDDING_MODEL = PydanticAIEmbeddingModel.DENSE_ON


class EmbeddingModelContract(NamedTuple):
    """Fixed vector width and revision for one approved embedding model."""

    dimensions: int
    revision: str


EMBEDDING_MODEL_CONTRACTS: dict[PydanticAIEmbeddingModel, EmbeddingModelContract] = {
    PydanticAIEmbeddingModel.DENSE_ON: EmbeddingModelContract(
        dimensions=768,
        # Hugging Face `main` as of 2026-07-06. Pin the commit so the local
        # embedder and tokenizer cannot drift when the branch moves.
        revision="cb9947ebccb33862d24e3c7ca2edb25e51acd887",
    ),
    PydanticAIEmbeddingModel.TEXT_EMBEDDING_3_SMALL: EmbeddingModelContract(
        dimensions=1_536,
        revision="latest",
    ),
}
