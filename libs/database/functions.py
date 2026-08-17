"""Async PostgreSQL access for the labs application and data jobs."""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from enum import StrEnum
from typing import cast

import asyncpg
from pydantic import SecretStr
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from libs.core.dependencies import EnvironmentMode
from libs.prefect_utils.secrets import PrefectSecret, get_secret

API_STATEMENT_TIMEOUT_MILLISECONDS = 10_000
DISPOSABLE_DATABASE_SUFFIXES = ("_test", "_verify")
TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/newman_labs_test"
MANAGED_DATABASE_NAME = "newman-labs"
DATABASE_MAX_OVERFLOW = 0
DATABASE_POOL_RECYCLE_SECONDS = 1_800
DATABASE_POOL_SIZE = 5
DATABASE_POOL_TIMEOUT_SECONDS = 5

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


class DatabaseRole(StrEnum):
    """Managed PostgreSQL roles with fixed routing policy."""

    OWNER = "neondb_owner"
    WEB = "newman_labs_web"


_DIRECT_DATABASE_HOSTS = {
    EnvironmentMode.DEV: "ep-sparkling-moon-ajowagbz.c-3.us-east-2.aws.neon.tech",
    EnvironmentMode.PROD: "ep-damp-snow-ajc6nlzp.c-3.us-east-2.aws.neon.tech",
}
_DATABASE_SECRETS = {
    (EnvironmentMode.DEV, DatabaseRole.OWNER): PrefectSecret.DATABASE_DEV_OWNER_URL,
    (EnvironmentMode.DEV, DatabaseRole.WEB): PrefectSecret.DATABASE_DEV_WEB_URL,
    (EnvironmentMode.PROD, DatabaseRole.OWNER): PrefectSecret.DATABASE_PROD_OWNER_URL,
    (EnvironmentMode.PROD, DatabaseRole.WEB): PrefectSecret.DATABASE_PROD_WEB_URL,
}


def get_test_database_url() -> SecretStr:
    """Return the explicit disposable test URL or the fixed test default."""
    database_url = SecretStr(os.environ.get("DATABASE_URL") or TEST_DATABASE_URL)
    require_disposable_database(database_name=make_url(database_url.get_secret_value()).database)
    return database_url


async def get_managed_database_url(
    *,
    environment: EnvironmentMode,
    role: DatabaseRole,
) -> SecretStr:
    """Load and attest the only managed URL allowed for one workload role."""
    database_url = await get_secret(name=_DATABASE_SECRETS[environment, role])
    url = make_url(database_url.get_secret_value())
    direct_host = _DIRECT_DATABASE_HOSTS[environment]
    endpoint, domain = direct_host.split(".", 1)
    runtime_host = f"{endpoint}-pooler.{domain}" if role is DatabaseRole.WEB else direct_host
    actual_target = (
        url.username,
        url.host,
        url.database,
        None if url.port in {None, 5432} else url.port,
        url.query.get("sslmode"),
    )
    expected_target = (
        role.value,
        direct_host,
        MANAGED_DATABASE_NAME,
        None,
        "require",
    )
    if not url.password or actual_target != expected_target:
        raise RuntimeError(
            f"Prefect database URL does not match the committed {environment.value} {role.name.lower()} database target"
        )
    return SecretStr(
        url.set(
            drivername="postgresql",
            host=runtime_host,
            port=None,
            query={"channel_binding": "require", "sslmode": "require"},
        ).render_as_string(hide_password=False)
    )


def async_database_url(*, database_url: SecretStr) -> URL:
    """Return a SQLAlchemy asyncpg URL for local or managed PostgreSQL."""
    url = make_url(database_url.get_secret_value())
    query = {key: value for key, value in url.query.items() if key != "channel_binding"}
    sslmode = query.pop("sslmode", None)
    if sslmode is not None:
        query["ssl"] = sslmode
    return url.set(drivername="postgresql+asyncpg", query=query)


def require_disposable_database(*, database_name: str | None) -> None:
    """Reject disposable-only work on retained databases."""
    if database_name is None or not database_name.endswith(DISPOSABLE_DATABASE_SUFFIXES):
        raise RuntimeError(
            "This operation is restricted to disposable databases whose names end with '_test' or '_verify'"
        )


@asynccontextmanager
async def get_database_connection(
    *,
    database_url: SecretStr | None = None,
) -> AsyncGenerator[asyncpg.Connection]:
    """Yield one transactional asyncpg connection and always close it."""
    url = async_database_url(database_url=database_url or get_test_database_url())
    connection = cast(
        "asyncpg.Connection",
        await asyncpg.connect(
            host=url.host,
            port=url.port or 5432,
            user=url.username,
            password=url.password,
            database=url.database,
            ssl=url.query.get("ssl") == "require",
        ),
    )
    try:
        async with connection.transaction():
            yield connection
    finally:
        await connection.close()


def get_api_db_engine(*, database_url: SecretStr | None = None) -> AsyncEngine:
    """Return the process-wide API engine with a bounded connection pool."""
    global _engine, _session_factory

    if _engine is not None and database_url is None:
        return _engine

    requested_url = async_database_url(database_url=database_url or get_test_database_url())
    if _engine is not None and _engine.url != requested_url:
        raise RuntimeError("API database engine is already initialized for another URL")

    if _engine is None:
        _engine = create_async_engine(
            requested_url,
            pool_size=DATABASE_POOL_SIZE,
            max_overflow=DATABASE_MAX_OVERFLOW,
            pool_timeout=DATABASE_POOL_TIMEOUT_SECONDS,
            pool_recycle=DATABASE_POOL_RECYCLE_SECONDS,
            pool_pre_ping=True,
            connect_args={"server_settings": {"statement_timeout": str(API_STATEMENT_TIMEOUT_MILLISECONDS)}},
        )
        _session_factory = async_sessionmaker(
            _engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _engine


def create_database_engine(*, database_url: SecretStr) -> AsyncEngine:
    """Create a short-lived unpooled engine for managed operational work."""
    return create_async_engine(
        async_database_url(database_url=database_url),
        poolclass=NullPool,
        pool_pre_ping=True,
    )


async def get_api_session() -> AsyncGenerator[AsyncSession]:
    """Yield one request-scoped session; route services own commits."""
    get_api_db_engine()
    if _session_factory is None:
        raise RuntimeError("API database session factory was not initialized")

    async with _session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def dispose_api_engine() -> None:
    """Dispose the API pool during shutdown and isolated tests."""
    global _engine, _session_factory

    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
