"""Application health endpoint tests."""

from collections.abc import AsyncGenerator
from typing import cast

import httpx
import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.labs.main import app
from libs.database.functions import get_api_session


async def test_live_health() -> None:
    """The live endpoint reports the development application state."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "environment": "dev"}


@pytest.mark.integration
async def test_ready_health() -> None:
    """The ready endpoint verifies the pooled API database path."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}


async def test_ready_health_when_database_is_unavailable() -> None:
    """The ready endpoint maps database failures to service unavailable."""

    class UnavailableSession:
        async def execute(self, _statement: object) -> None:
            raise SQLAlchemyError("newman database unavailable")

    async def override_session() -> AsyncGenerator[AsyncSession]:
        yield cast("AsyncSession", UnavailableSession())

    app.dependency_overrides[get_api_session] = override_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.get("/health/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {"detail": "Database is unavailable"}
