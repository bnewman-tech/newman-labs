"""Database safety policy tests."""

from unittest.mock import AsyncMock

import pytest
from pydantic import SecretStr
from sqlalchemy.engine import make_url

from libs.core.dependencies import EnvironmentMode
from libs.database import functions
from libs.database.functions import (
    MANAGED_DATABASE_NAME,
    DatabaseRole,
    async_database_url,
    get_managed_database_url,
    get_test_database_url,
    require_disposable_database,
)
from libs.prefect_utils.secrets import PrefectSecret


async def test_managed_database_urls_attest_direct_and_pooled_roles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each managed workload receives only its committed endpoint and role."""
    direct_host = "ep-sparkling-moon-ajowagbz.c-3.us-east-2.aws.neon.tech"
    pooled_host = "ep-sparkling-moon-ajowagbz-pooler.c-3.us-east-2.aws.neon.tech"
    secrets = {
        PrefectSecret.DATABASE_DEV_OWNER_URL: SecretStr(
            f"postgresql://neondb_owner:newman@{direct_host}/newman-labs?sslmode=require"
        ),
        PrefectSecret.DATABASE_DEV_WEB_URL: SecretStr(
            f"postgresql://newman_labs_web:newman@{direct_host}/newman-labs?sslmode=require"
        ),
    }
    monkeypatch.setattr(functions, "get_secret", AsyncMock(side_effect=lambda *, name: secrets[name]))
    direct = await get_managed_database_url(
        environment=EnvironmentMode.DEV,
        role=DatabaseRole.OWNER,
    )
    pooled = await get_managed_database_url(
        environment=EnvironmentMode.DEV,
        role=DatabaseRole.WEB,
    )

    direct_url = make_url(direct.get_secret_value())
    pooled_url = make_url(pooled.get_secret_value())
    assert direct_url.host == direct_host
    assert direct_url.username == DatabaseRole.OWNER
    assert direct_url.database == MANAGED_DATABASE_NAME
    assert direct_url.query == {
        "channel_binding": "require",
        "sslmode": "require",
    }
    assert pooled_url.host == pooled_host
    assert pooled_url.username == DatabaseRole.WEB


async def test_managed_database_url_rejects_an_uncommitted_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A valid credential cannot redirect a managed workload to another host."""
    monkeypatch.setattr(
        functions,
        "get_secret",
        AsyncMock(
            return_value=SecretStr("postgresql://neondb_owner:newman@unexpected.example/newman-labs?sslmode=require")
        ),
    )

    with pytest.raises(RuntimeError, match="committed dev owner database target"):
        await get_managed_database_url(
            environment=EnvironmentMode.DEV,
            role=DatabaseRole.OWNER,
        )


def test_test_database_url_rejects_a_retained_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local tools cannot treat an arbitrary DATABASE_URL as disposable."""
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost/newman_labs",
    )

    with pytest.raises(RuntimeError, match="restricted to disposable databases"):
        get_test_database_url()


@pytest.mark.parametrize("database_name", ["newman_labs_test", "newman_labs_verify"])
def test_disposable_database_names_allow_history_changes(database_name: str) -> None:
    """Only explicit test databases support downgrade and stamp."""
    require_disposable_database(database_name=database_name)


@pytest.mark.parametrize("database_name", [None, "newman_labs", "newman-labs"])
def test_retained_database_names_reject_history_changes(
    database_name: str | None,
) -> None:
    """Retained local and managed databases fail closed."""
    with pytest.raises(RuntimeError, match="restricted to disposable databases"):
        require_disposable_database(database_name=database_name)


def test_async_database_url_adapts_driver_and_ssl_options() -> None:
    """SQLAlchemy gets asyncpg's driver and SSL option; local URLs stay plain."""
    managed = async_database_url(
        database_url=SecretStr(
            "postgresql://newman:newman-password@"
            "ep-newman.us-east-2.aws.neon.tech/newman"
            "?sslmode=require&channel_binding=require"
        )
    )
    local = async_database_url(database_url=SecretStr("postgresql+asyncpg://postgres:postgres@localhost/newman_labs"))

    assert managed.host == "ep-newman.us-east-2.aws.neon.tech"
    assert managed.drivername == "postgresql+asyncpg"
    assert managed.query == {"ssl": "require"}
    assert local.drivername == "postgresql+asyncpg"
    assert local.query == {}
    assert local.render_as_string(hide_password=False) == (
        "postgresql+asyncpg://postgres:postgres@localhost/newman_labs"
    )
