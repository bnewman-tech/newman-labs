"""Prefect Variable utility tests."""

from unittest.mock import AsyncMock

import pytest
from prefect.variables import Variable

from libs.prefect_utils.variables import (
    SERVERLESS_WORK_POOL_NAME,
    SERVERLESS_WORK_POOL_VARIABLE,
    sync_prefect_variables,
)


async def test_sync_prefect_variables_sets_serverless_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provisioning keeps the deployment work-pool variable current."""
    set_variable = AsyncMock()
    monkeypatch.setattr(Variable, "aset", set_variable)

    await sync_prefect_variables()

    set_variable.assert_awaited_once_with(
        name=SERVERLESS_WORK_POOL_VARIABLE,
        value=SERVERLESS_WORK_POOL_NAME,
        tags=["newman-labs", "deployment"],
        overwrite=True,
    )
