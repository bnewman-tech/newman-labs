"""Alembic migration environment."""

import asyncio
from logging.config import fileConfig
from typing import cast

from alembic import context
from alembic.runtime.environment import NameFilterParentNames, NameFilterType
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from libs.database.functions import (
    async_database_url,
    get_test_database_url,
    require_disposable_database,
)
from libs.database.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
database_url = config.attributes.get("database_url", get_test_database_url())


def include_name(
    name: str | None,
    type_: NameFilterType,
    parent_names: NameFilterParentNames,
) -> bool:
    """Exclude dbt-owned analytics relations from Alembic drift checks."""
    schema_name = name if type_ == "schema" else parent_names.get("schema_name")
    if schema_name is None:
        return True
    return schema_name != "analytics" and not schema_name.startswith("analytics_")


def configure_context(*, connection: Connection | None = None) -> None:
    """Configure Alembic for online or offline execution."""
    context.configure(
        connection=connection,
        url=None if connection else async_database_url(database_url=database_url),
        target_metadata=target_metadata,
        compare_type=True,
        include_name=include_name,
        include_schemas=True,
        literal_binds=connection is None,
        dialect_opts={"paramstyle": "named"} if connection is None else None,
    )


def protect_migration_history(*, connection: Connection | None = None) -> None:
    """Allow history rewrites only on explicitly disposable databases."""
    migration_function = context.get_context().opts.get("fn")
    operation_name = getattr(migration_function, "__name__", None)
    if operation_name not in {"downgrade", "do_stamp"}:
        return

    require_disposable_database(database_name=None if connection is None else connection.engine.url.database)


def run_migrations_offline() -> None:
    """Run migrations without creating a database connection."""
    configure_context()
    protect_migration_history()
    with context.begin_transaction():
        context.run_migrations()


def run_sync_migrations(connection: Connection) -> None:
    """Run migrations on an async engine's synchronous connection."""
    configure_context(connection=connection)
    protect_migration_history(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Open one unpooled connection for local Alembic commands."""
    engine = create_async_engine(
        async_database_url(database_url=database_url),
        poolclass=pool.NullPool,
    )
    async with engine.connect() as connection:
        await connection.run_sync(run_sync_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    """Reuse a managed connection or open one for local Alembic commands."""
    connection = config.attributes.get("connection")
    if connection is not None:
        run_sync_migrations(cast("Connection", connection))
        return
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
