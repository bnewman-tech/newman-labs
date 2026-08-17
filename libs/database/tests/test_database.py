"""Local PostgreSQL connectivity tests."""

import pytest
from sqlalchemy.engine import make_url

from libs.database.functions import get_database_connection, get_test_database_url


@pytest.mark.integration
async def test_local_database_connection() -> None:
    """The configured disposable database accepts a transactional query."""
    async with get_database_connection() as connection:
        database_name = await connection.fetchval("SELECT current_database()")

    configured_database = make_url(get_test_database_url().get_secret_value()).database
    assert configured_database is not None
    assert database_name == configured_database
