"""Tests for the manually invoked live model matrix."""

from unittest.mock import AsyncMock

import pytest
from pydantic_ai.models.test import TestModel

from libs.pydantic_ai_core.schemas import PydanticAIModel, ThinkingLevel
from libs.pydantic_ai_core.scripts import smoke_model_matrix


async def test_model_smoke_matrix_validates_output_and_calls_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The live contract uses low reasoning, typed output, and a function tool."""
    model = TestModel(profile={"supports_thinking": True})
    build_agent_model = AsyncMock(return_value=model)
    monkeypatch.setattr(
        smoke_model_matrix,
        "build_agent_model",
        build_agent_model,
    )

    results = await smoke_model_matrix.run_model_smoke_matrix(
        models=(PydanticAIModel.GPT_5_6_TERRA,),
    )

    assert len(results) == 1
    assert results[0].tool_calls == 1
    assert results[0].actual_model == "test"
    assert model.last_model_request_parameters is not None
    assert model.last_model_request_parameters.thinking == ThinkingLevel.LOW.value
    assert [tool.name for tool in model.last_model_request_parameters.function_tools] == ["lookup_payment_terms"]
    build_agent_model.assert_awaited_once_with(model=PydanticAIModel.GPT_5_6_TERRA)
