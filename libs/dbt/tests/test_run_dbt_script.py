"""Tests for the shared test and managed dbt command entrypoint."""

import sys
from unittest.mock import AsyncMock

import pytest
from pydantic import SecretStr

from libs.core.dependencies import EnvironmentMode
from libs.database.functions import DatabaseRole
from libs.dbt.schemas import DBTCommandResult
from libs.dbt.scripts import run_dbt


@pytest.mark.asyncio
async def test_test_dbt_command_uses_direct_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test dbt avoids the transaction-pooled application endpoint."""
    direct_url = SecretStr("postgresql://newman:newman@direct.example/newman")
    run_command = AsyncMock(
        return_value=DBTCommandResult(
            return_code=0,
            stdout="",
            stderr="",
        )
    )
    monkeypatch.setattr(sys, "argv", ["run_dbt", "build"])
    monkeypatch.setattr(run_dbt, "get_test_database_url", lambda: direct_url)
    monkeypatch.setattr(run_dbt, "run_dbt_command", run_command)

    assert await run_dbt.main() == 0

    run_command.assert_awaited_once_with(
        arguments=["build"],
        database_url=direct_url,
    )


@pytest.mark.asyncio
async def test_managed_dbt_command_loads_prefect_database_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Managed deploys use the attested owner URL."""
    database_url = SecretStr("postgresql://neondb_owner:newman@ep-prod.example/newman-labs?sslmode=require")
    get_database_url = AsyncMock(return_value=database_url)
    run_command = AsyncMock(
        return_value=DBTCommandResult(
            return_code=0,
            stdout="",
            stderr="",
        )
    )
    monkeypatch.setattr(sys, "argv", ["run_dbt", "--managed", "build"])
    monkeypatch.setattr(run_dbt.settings, "environment", EnvironmentMode.PROD)
    monkeypatch.setattr(run_dbt, "get_managed_database_url", get_database_url)
    monkeypatch.setattr(run_dbt, "run_dbt_command", run_command)

    assert await run_dbt.main() == 0

    get_database_url.assert_awaited_once_with(
        environment=EnvironmentMode.PROD,
        role=DatabaseRole.OWNER,
    )
    run_command.assert_awaited_once_with(
        arguments=["build"],
        database_url=database_url,
    )
