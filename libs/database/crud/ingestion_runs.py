"""Persistence for the shared source-ingestion audit trail."""

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from asyncpg import Connection
from pydantic import SecretStr

from libs.database.functions import get_database_connection
from libs.database.schemas import SourceIngestionResult


async def insert_successful_ingestion_run(
    *,
    connection: Connection,
    result: SourceIngestionResult,
    source_cursor: str | None = None,
) -> None:
    """Insert a successful audit row in the source-write transaction."""
    await connection.execute(
        """
        INSERT INTO orchestration.ingestion_run (
            run_id,
            source_name,
            status,
            started_at,
            completed_at,
            source_cursor,
            extracted_rows,
            inserted_rows,
            updated_rows,
            unchanged_rows,
            deactivated_rows,
            deleted_rows,
            previous_watermark,
            current_watermark,
            warnings
        ) VALUES (
            $1, $2, 'succeeded', $3, $4, $5,
            $6, $7, $8, $9, $10, $11, $12, $13, $14::jsonb
        )
        """,
        result.run_id,
        result.source_name,
        result.started_at,
        result.completed_at,
        source_cursor,
        result.extracted_rows,
        result.inserted_rows,
        result.updated_rows,
        result.unchanged_rows,
        result.deactivated_rows,
        result.deleted_rows,
        result.previous_watermark,
        result.current_watermark,
        json.dumps(result.warnings),
    )


async def record_failed_ingestion_run(
    *,
    source_name: str,
    started_at: datetime,
    error_type: str,
    database_url: SecretStr | None = None,
) -> UUID:
    """Record a failed source attempt without persisting sensitive error text."""
    run_id = uuid4()
    async with get_database_connection(database_url=database_url) as connection:
        await connection.execute(
            """
            INSERT INTO orchestration.ingestion_run (
                run_id,
                source_name,
                status,
                started_at,
                completed_at,
                error_type
            ) VALUES ($1, $2, 'failed', $3, $4, $5)
            """,
            run_id,
            source_name,
            started_at,
            datetime.now(UTC),
            error_type,
        )
    return run_id
