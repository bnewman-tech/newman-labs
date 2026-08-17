"""Tests for the process-wide asynchronous API database pool."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import SecretStr

from libs.database import functions
from libs.database.functions import dispose_api_engine, get_api_db_engine, get_api_session


@pytest.mark.asyncio
async def test_api_engine_normalizes_managed_postgres_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A standard Neon URL must still select SQLAlchemy's asyncpg driver."""
    database_url = SecretStr(
        "postgresql://newman:newman-password@ep-newman-pooler.example/newman?sslmode=require&channel_binding=require"
    )

    engine = get_api_db_engine(database_url=database_url)

    assert engine.url.drivername == "postgresql+asyncpg"
    assert engine.url.query == {"ssl": "require"}
    await dispose_api_engine()


async def test_api_engine_reuses_the_initialized_pool_and_rejects_a_new_url() -> None:
    """Services can reuse the pool, but no caller can silently retarget it."""
    database_url = SecretStr("postgresql+asyncpg://postgres:postgres@localhost/newman_labs_test")
    other_url = SecretStr("postgresql+asyncpg://postgres:postgres@localhost/newman_labs_verify")

    engine = get_api_db_engine(database_url=database_url)

    assert get_api_db_engine() is engine
    with pytest.raises(RuntimeError, match="already initialized for another URL"):
        get_api_db_engine(database_url=other_url)
    await dispose_api_engine()


async def test_api_session_defers_database_io_until_the_route_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid request parameters fail without opening a database connection."""
    session = AsyncMock()
    session.__aenter__.return_value = session
    monkeypatch.setattr(functions, "get_api_db_engine", MagicMock())
    monkeypatch.setattr(functions, "_session_factory", MagicMock(return_value=session))

    yielded_sessions = [item async for item in get_api_session()]

    assert yielded_sessions == [session]
    session.execute.assert_not_awaited()
    session.__aexit__.assert_awaited_once_with(None, None, None)


async def test_api_session_rolls_back_and_releases_after_a_route_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed request cannot leave its transaction or connection checked out."""
    session = AsyncMock()
    session.__aenter__.return_value = session
    monkeypatch.setattr(functions, "get_api_db_engine", MagicMock())
    monkeypatch.setattr(functions, "_session_factory", MagicMock(return_value=session))
    session_generator = get_api_session()

    await anext(session_generator)
    with pytest.raises(RuntimeError, match="request failed"):
        await session_generator.athrow(RuntimeError("request failed"))

    session.rollback.assert_awaited_once_with()
    session.__aexit__.assert_awaited_once()
