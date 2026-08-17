"""Apply Alembic migrations using the managed database Prefect block."""

import asyncio

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import Connection

from libs.core.dependencies import settings
from libs.database.functions import (
    DatabaseRole,
    create_database_engine,
    get_managed_database_url,
)

MIGRATION_LOCK_ID = 6_247_589_374_667_387_592


def upgrade_to_head(connection: Connection, *, configuration: Config) -> None:
    """Run Alembic on the already-attested, locked connection."""
    configuration.attributes["connection"] = connection
    command.upgrade(configuration, "head")


async def migrate_managed_database() -> None:
    """Validate the selected retained target and history, then upgrade to head."""
    database_url = await get_managed_database_url(
        environment=settings.environment,
        role=DatabaseRole.OWNER,
    )

    alembic_config = Config("alembic.ini")
    alembic_config.attributes["database_url"] = database_url
    script_directory = ScriptDirectory.from_config(alembic_config)
    known_revisions = {revision.revision for revision in script_directory.walk_revisions()}
    head_revision = script_directory.get_current_head()
    if head_revision is None:
        raise RuntimeError("Alembic must have exactly one committed head")

    engine = create_database_engine(database_url=database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(:lock_id)"),
                {"lock_id": MIGRATION_LOCK_ID},
            )
            state = await connection.exec_driver_sql(
                """
                SELECT
                    to_regclass('public.alembic_version') IS NOT NULL
                        AS has_alembic_version,
                    to_regclass('orchestration.ingestion_run') IS NOT NULL
                        AS has_ingestion_run,
                    to_regclass('document_intelligence.document') IS NOT NULL
                        AS has_document,
                    (
                        SELECT count(*)
                        FROM pg_catalog.pg_tables
                        WHERE schemaname IN (
                            'document_intelligence',
                            'invoice_parser',
                            'orchestration',
                            'raw'
                        )
                    ) AS application_table_count
                """
            )
            (
                has_version,
                has_ingestion_run,
                has_document,
                application_table_count,
            ) = state.one()
            if has_version:
                revisions = await connection.exec_driver_sql("SELECT version_num FROM public.alembic_version")
                current_revisions = revisions.scalars().all()
                current_schema = has_ingestion_run and has_document
                if len(current_revisions) != 1 or current_revisions[0] not in known_revisions or not current_schema:
                    raise RuntimeError(
                        "Managed database migration history or required schema is "
                        "inconsistent; retained database recovery requires operator "
                        "review"
                    )
            elif application_table_count:
                raise RuntimeError(
                    "Managed database has application tables without Alembic history; recovery requires operator review"
                )

            await connection.run_sync(
                upgrade_to_head,
                configuration=alembic_config,
            )
            revisions = await connection.exec_driver_sql("SELECT version_num FROM public.alembic_version")
            if revisions.scalars().all() != [head_revision]:
                raise RuntimeError("Managed database did not reach the committed Alembic head")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(migrate_managed_database())
