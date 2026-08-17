"""Houston 311 extraction and PostgreSQL ingestion entrypoint."""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import polars as pl
from prefect import flow
from pydantic import SecretStr

from labs.houston_signal.integrations.houston_311.functions import (
    SOURCE_NAME,
    get_houston_311_records,
    prepare_houston_311_snapshot,
)
from libs.core.dependencies import EnvironmentMode, settings
from libs.core.logger import get_logger
from libs.database.crud.ingestion_runs import (
    insert_successful_ingestion_run,
    record_failed_ingestion_run,
)
from libs.database.functions import (
    DatabaseRole,
    get_database_connection,
    get_managed_database_url,
)
from libs.database.schemas import SourceIngestionResult

logger = get_logger(__name__)

HOUSTON_311_COPY_COLUMNS = [
    "case_number",
    "source_object_id",
    "case_number_365",
    "incident_address",
    "latitude",
    "longitude",
    "status",
    "created_at",
    "due_at",
    "closed_at",
    "title",
    "case_type",
    "sla_time",
    "service_area",
    "council_district",
    "key_map",
    "department",
    "division",
    "state_code",
    "state_code_name",
    "swm_quadrant",
    "recycling_quadrant",
    "heavy_trash_quadrant",
    "resolution_notes",
    "meaningful_hash",
    "last_seen_at",
    "ingested_at",
]
INGESTION_LOCK_NAME = "newman-labs:houston-311"


async def get_houston_311_source_object_id_watermark(
    *,
    database_url: SecretStr | None = None,
) -> int | None:
    """Return the last successfully extracted ArcGIS ObjectID."""
    async with get_database_connection(database_url=database_url) as connection:
        watermark = await connection.fetchval(
            """
            SELECT coalesce(
                (
                    SELECT source_cursor::bigint
                    FROM orchestration.ingestion_run
                    WHERE status = 'succeeded'
                      AND source_name = 'houston_311'
                      AND source_cursor IS NOT NULL
                    ORDER BY completed_at DESC
                    LIMIT 1
                ),
                (SELECT max(source_object_id) FROM raw.houston_311_request)
            )
            """
        )
    return int(watermark) if watermark is not None else None


async def load_houston_311_snapshot(
    *,
    dataframe: pl.DataFrame,
    started_at: datetime,
    extracted_rows: int,
    warnings: list[str],
    source_object_id_watermark: int | None = None,
    database_url: SecretStr | None = None,
) -> SourceIngestionResult:
    """COPY and upsert all observed Houston 311 cases in one transaction."""
    missing_columns = set(HOUSTON_311_COPY_COLUMNS).difference(dataframe.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Houston 311 snapshot is missing columns: {missing}")
    if dataframe.is_empty():
        raise ValueError("Houston 311 snapshot cannot be empty")
    dataframe = dataframe.select(HOUSTON_311_COPY_COLUMNS)
    max_source_object_id = dataframe["source_object_id"].max()
    if not isinstance(max_source_object_id, int):
        raise TypeError("Houston 311 snapshot has no valid ObjectID")
    if source_object_id_watermark is None:
        source_object_id_watermark = max_source_object_id
    async with get_database_connection(database_url=database_url) as connection:
        await connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
            INGESTION_LOCK_NAME,
        )
        previous_watermark = await connection.fetchval("SELECT max(created_at) FROM raw.houston_311_request")
        await connection.execute(
            """
            CREATE TEMPORARY TABLE houston_311_request_stage
            (LIKE raw.houston_311_request INCLUDING DEFAULTS)
            ON COMMIT DROP
            """
        )
        await connection.copy_records_to_table(
            "houston_311_request_stage",
            schema_name="pg_temp",
            columns=HOUSTON_311_COPY_COLUMNS,
            records=dataframe.iter_rows(),
            timeout=300,
        )
        counts = await connection.fetchrow(
            """
            SELECT
                count(*) FILTER (WHERE target.case_number IS NULL) AS inserted_rows,
                count(*) FILTER (
                    WHERE target.case_number IS NOT NULL
                      AND stage.last_seen_at >= target.last_seen_at
                      AND target.meaningful_hash <> stage.meaningful_hash
                ) AS updated_rows,
                count(*) FILTER (
                    WHERE target.case_number IS NOT NULL
                      AND (
                          stage.last_seen_at < target.last_seen_at
                          OR target.meaningful_hash = stage.meaningful_hash
                      )
                ) AS unchanged_rows
            FROM pg_temp.houston_311_request_stage AS stage
            LEFT JOIN raw.houston_311_request AS target USING (case_number)
            """
        )
        if counts is None:
            raise RuntimeError("PostgreSQL did not return Houston 311 load counts")

        update_columns = [
            column
            for column in HOUSTON_311_COPY_COLUMNS
            if column not in {"case_number", "last_seen_at", "ingested_at"}
        ]
        assignments = ",\n".join(
            f'                "{column}" = CASE\n'
            "                    WHEN EXCLUDED.last_seen_at >= "
            "raw.houston_311_request.last_seen_at\n"
            f'                    THEN EXCLUDED."{column}"\n'
            f'                    ELSE raw.houston_311_request."{column}"\n'
            "                END"
            for column in update_columns
        )
        quoted_columns = ", ".join(f'"{column}"' for column in HOUSTON_311_COPY_COLUMNS)
        await connection.execute(
            f"""
            INSERT INTO raw.houston_311_request ({quoted_columns}, first_seen_at)
            SELECT {quoted_columns}, last_seen_at
            FROM pg_temp.houston_311_request_stage
            ON CONFLICT (case_number) DO UPDATE SET
{assignments},
                first_seen_at = LEAST(
                    raw.houston_311_request.first_seen_at,
                    EXCLUDED.last_seen_at
                ),
                last_seen_at = GREATEST(
                    raw.houston_311_request.last_seen_at,
                    EXCLUDED.last_seen_at
                ),
                ingested_at = GREATEST(
                    raw.houston_311_request.ingested_at,
                    EXCLUDED.ingested_at
                )
            """
        )
        current_watermark = await connection.fetchval("SELECT max(created_at) FROM raw.houston_311_request")
        if current_watermark is None:
            raise RuntimeError("Houston 311 load produced no source watermark")
        completed_at = datetime.now(UTC)
        result = SourceIngestionResult(
            run_id=uuid4(),
            source_name=SOURCE_NAME,
            started_at=started_at,
            completed_at=completed_at,
            extracted_rows=extracted_rows,
            inserted_rows=int(counts["inserted_rows"]),
            updated_rows=int(counts["updated_rows"]),
            unchanged_rows=int(counts["unchanged_rows"]),
            previous_watermark=previous_watermark,
            current_watermark=current_watermark,
            warnings=warnings,
        )
        await insert_successful_ingestion_run(
            connection=connection,
            result=result,
            source_cursor=str(source_object_id_watermark),
        )
    return result


@flow(
    name="houston-signal-311-pipeline",
    flow_run_name="houston-311-{environment}",
    timeout_seconds=3_600,
    retries=2,
    retry_delay_seconds=60,
)
async def run_houston_311_pipeline(
    environment: EnvironmentMode = settings.environment,
) -> SourceIngestionResult:
    """Extract Houston 311 and commit its typed source state."""
    started_at = datetime.now(UTC)
    database_url = await get_managed_database_url(
        environment=environment,
        role=DatabaseRole.OWNER,
    )
    try:
        previous_object_id = await get_houston_311_source_object_id_watermark(database_url=database_url)
        records = await get_houston_311_records(source_object_id_watermark=previous_object_id)
        if records is None:
            raise RuntimeError(  # ruff: ignore[raise-within-try]
                "Houston 311 extraction failed"
            )
        if not records:
            raise RuntimeError(  # ruff: ignore[raise-within-try]
                "Houston 311 returned no service requests"
            )

        warnings = []
        collapsed_snapshots = len(records) - len({record.case_number for record in records})
        if collapsed_snapshots:
            warnings.append(f"Collapsed {collapsed_snapshots} repeated case snapshots to the latest ObjectID")
        result = await load_houston_311_snapshot(
            dataframe=prepare_houston_311_snapshot(
                records=records,
                observed_at=started_at,
            ),
            started_at=started_at,
            extracted_rows=len(records),
            warnings=warnings,
            source_object_id_watermark=max(record.source_object_id for record in records),
            database_url=database_url,
        )
    except Exception as exception:
        try:
            await record_failed_ingestion_run(
                source_name=SOURCE_NAME,
                started_at=started_at,
                error_type=type(exception).__name__,
                database_url=database_url,
            )
        except Exception:
            logger.exception("Houston 311 failure audit could not be persisted")
        raise

    logger.info(
        f"Houston 311 ingestion completed: extracted={result.extracted_rows} "
        f"inserted={result.inserted_rows} updated={result.updated_rows} "
        f"unchanged={result.unchanged_rows}"
    )
    return result


if __name__ == "__main__":
    asyncio.run(run_houston_311_pipeline())
