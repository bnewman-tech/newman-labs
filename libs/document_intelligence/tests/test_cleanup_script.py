"""Tests for the managed document-retention flow."""

from unittest.mock import ANY, AsyncMock, Mock

import pytest
from pydantic import SecretStr

from libs.core.dependencies import EnvironmentMode, settings
from libs.database.functions import DatabaseRole
from libs.document_intelligence.scripts import cleanup


@pytest.mark.parametrize("environment", list(EnvironmentMode))
async def test_retention_flow_uses_the_selected_managed_database(
    monkeypatch: pytest.MonkeyPatch,
    environment: EnvironmentMode,
) -> None:
    """The flow uses one short-lived owner engine for its selected environment."""
    previous_environment = settings.environment
    database_url = SecretStr("postgresql://neondb_owner:newman@ep-dev.example/newman-labs?sslmode=require")
    get_managed_database_url = AsyncMock(return_value=database_url)
    engine = Mock()
    engine.dispose = AsyncMock()
    create_database_engine = Mock(return_value=engine)
    delete_expired_documents = AsyncMock(return_value=3)
    delete_blobs_before = AsyncMock(return_value=2)
    monkeypatch.setattr(
        cleanup,
        "get_managed_database_url",
        get_managed_database_url,
    )
    monkeypatch.setattr(cleanup, "create_database_engine", create_database_engine)
    monkeypatch.setattr(cleanup, "delete_expired_documents", delete_expired_documents)
    monkeypatch.setattr(cleanup, "delete_blobs_before", delete_blobs_before)

    result = await cleanup.run_document_retention_cleanup.fn(environment=environment)

    assert result == 3
    get_managed_database_url.assert_awaited_once_with(
        environment=environment,
        role=DatabaseRole.OWNER,
    )
    create_database_engine.assert_called_once_with(database_url=database_url)
    delete_expired_documents.assert_awaited_once_with(engine=engine)
    delete_blobs_before.assert_awaited_once_with(
        bucket=cleanup.DOCUMENT_STORAGE_BUCKET,
        prefix=f"{cleanup.DOCUMENT_STAGING_PREFIX}/",
        before=ANY,
    )
    engine.dispose.assert_awaited_once_with()
    assert settings.environment is previous_environment
