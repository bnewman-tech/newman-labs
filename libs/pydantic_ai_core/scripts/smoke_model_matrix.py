"""Run each approved chat model through one realistic live agent contract."""

import asyncio
from decimal import Decimal
from typing import Literal

from pydantic import Field
from pydantic_ai import Agent
from pydantic_ai.capabilities import Thinking
from pydantic_ai.settings import ModelSettings

from libs.core.pydantic_base import NewmanLabsModel
from libs.pydantic_ai_core.functions import build_agent_model
from libs.pydantic_ai_core.schemas import PydanticAIModel, ThinkingLevel

MODEL_SMOKE_TIMEOUT_SECONDS = 180


class InvoiceSmokeOutput(NewmanLabsModel):
    """Validated invoice review returned by every approved model."""

    invoice_number: Literal["INV-1042"]
    vendor_name: Literal["Newman Office Supply"]
    payment_terms: Literal["Net 30"]
    total: Decimal = Field(gt=0)
    requires_review: Literal[False]


class ModelSmokeResult(NewmanLabsModel):
    """Verified identity, usage, and tool behavior from one live request."""

    configured_model: PydanticAIModel
    actual_model: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    tool_calls: int = Field(ge=1)


async def run_model_smoke_matrix(
    *,
    models: tuple[PydanticAIModel, ...] = tuple(PydanticAIModel),
) -> list[ModelSmokeResult]:
    """Verify low reasoning, tool calling, and structured output for each model."""
    results: list[ModelSmokeResult] = []
    failures: list[str] = []

    for configured_model in models:
        tool_calls = 0

        try:  # ruff: ignore[too-many-statements-in-try-clause] - One provider contract must fail and report as one unit.
            model = await build_agent_model(model=configured_model)
            agent: Agent[None, InvoiceSmokeOutput] = Agent(
                model,
                name="model_smoke_agent",
                instructions=(
                    "Review the supplied invoice. Call lookup_payment_terms before "
                    "returning the required structured result."
                ),
                output_type=InvoiceSmokeOutput,
                capabilities=[Thinking(effort=ThinkingLevel.LOW.value)],
                model_settings=ModelSettings(max_tokens=256),
            )

            @agent.tool_plain
            def lookup_payment_terms(
                *,
                vendor_name: Literal["Newman Office Supply"],
            ) -> Literal["Net 30"]:
                """Return the approved payment terms for the supplied vendor."""
                nonlocal tool_calls
                if vendor_name != "Newman Office Supply":
                    raise ValueError(  # ruff: ignore[raise-within-try] - Tool validation belongs to this provider run.
                        "Unknown smoke-test vendor"
                    )
                tool_calls += 1
                return "Net 30"

            async with asyncio.timeout(MODEL_SMOKE_TIMEOUT_SECONDS):
                result = await agent.run(
                    "Review invoice INV-1042 from Newman Office Supply for $125.00. "
                    "The invoice does not require manual review."
                )
            if tool_calls == 0:
                raise RuntimeError(  # ruff: ignore[raise-within-try] - Include contract failures in the provider report.
                    "Model returned without calling the required tool"
                )
        except Exception as exception:  # ruff: ignore[blind-except] - Report every provider before failing the matrix.
            failure = f"{configured_model.value}: {type(exception).__name__}: {exception}"
            failures.append(failure)
            print(f"FAIL {failure}")
            continue

        smoke_result = ModelSmokeResult(
            configured_model=configured_model,
            actual_model=result.response.model_name or configured_model.value,
            provider=result.response.provider_name or "unknown",
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            tool_calls=tool_calls,
        )
        results.append(smoke_result)
        print(
            f"PASS {configured_model.value} "
            f"actual={smoke_result.actual_model} "
            f"provider={smoke_result.provider} "
            f"tools={smoke_result.tool_calls} "
            f"tokens={smoke_result.input_tokens}/{smoke_result.output_tokens}"
        )

    if failures:
        raise RuntimeError(f"Model smoke matrix failed {len(failures)} of {len(models)} requests")
    return results


if __name__ == "__main__":
    asyncio.run(run_model_smoke_matrix())
