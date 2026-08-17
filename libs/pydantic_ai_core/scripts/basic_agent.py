"""Run a basic agent with a model and a tool."""

import asyncio
import random
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[3]))

from pydantic_ai import Agent, RunContext
from pydantic_ai.capabilities import Thinking

from libs.core.logger import get_logger
from libs.pydantic_ai_core.functions import build_agent_model
from libs.pydantic_ai_core.schemas import PydanticAIModel, ThinkingLevel

logger = get_logger(__name__)


@dataclass
class DiceDeps:
    """Dependencies for the dice game."""

    player_name: str


def roll_die() -> int:
    """Roll a die."""
    return random.choice([1, 2, 3, 4, 5, 6])  # ruff: ignore[suspicious-non-cryptographic-random-usage]


def get_player_name(ctx: RunContext[DiceDeps]) -> str:
    """Get the player's name."""
    return ctx.deps.player_name


async def run_basic_agent() -> None:
    """Run a basic agent with a model and a tool."""
    model = await build_agent_model(model=PydanticAIModel.MINIMAX_M3)

    agent = Agent[DiceDeps, str](
        model=model,
        deps_type=DiceDeps,
        name="dice-roller",
        instructions="""You're a dice game, you should roll the die and see if the number
        you get back matches the user's guess. If so, tell them they're a winner.
        Use the player's name in the response.""",
        output_type=str,
        capabilities=[Thinking(effort=ThinkingLevel.LOW.value)],
    )
    agent.tool_plain(roll_die)
    agent.tool(get_player_name)

    response = await agent.run(
        "My guess is 3. What do you think?",
        deps=DiceDeps(player_name="John Doe"),
    )
    logger.info(response.all_messages())


if __name__ == "__main__":
    asyncio.run(run_basic_agent())
