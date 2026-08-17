"""Database test lifecycle fixtures."""

from collections.abc import AsyncGenerator

import pytest

from libs.database.functions import dispose_api_engine


@pytest.fixture(autouse=True)
async def dispose_database_pool() -> AsyncGenerator[None]:
    """Prevent pooled asyncpg connections from crossing pytest event loops."""
    yield
    await dispose_api_engine()
