"""Repository-wide pytest safety policy."""

from collections.abc import AsyncGenerator

import pytest
from pydantic_ai import models
from sqlalchemy.engine import make_url

from libs.database.functions import dispose_api_engine, get_test_database_url

models.ALLOW_MODEL_REQUESTS = False


@pytest.fixture(autouse=True)
async def dispose_database_pool() -> AsyncGenerator[None]:
    """Prevent the cached API engine from leaking across tests or event loops."""
    yield
    await dispose_api_engine()


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Refuse infrastructure tests unless PostgreSQL is explicitly disposable."""
    if item.get_closest_marker("integration") is None:
        return

    database_name = make_url(get_test_database_url().get_secret_value()).database
    if database_name is None or not database_name.endswith(("_test", "_verify")):
        pytest.fail(
            "Integration tests require a disposable database whose name ends with "
            "'_test' or '_verify'; refusing to modify "
            f"{database_name or 'an unnamed database'}.",
            pytrace=False,
        )
