"""Houston Emergency Center extraction and PostgreSQL ingestion entrypoint."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import polars as pl
from prefect import flow
from pydantic import SecretStr

from labs.houston_signal.integrations.houston_emergency_center.functions import (
    SOURCE_NAME,
    get_houston_emergency_center_active_incidents,
    prepare_houston_emergency_center_snapshot,
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

RETENTION_DAYS = 365
HOUSTON_EMERGENCY_CENTER_COPY_COLUMNS = [
    "incident_id",
    "source_incident_id",
    "agency",
    "address",
    "cross_street",
    "longitude",
    "latitude",
    "key_map",
    "opened_at",
    "incident_type",
    "alarm_level",
    "reported_unit_count",
    "units",
    "combined_response",
    "meaningful_hash",
    "last_seen_at",
    "ingested_at",
]
INGESTION_LOCK_NAME = "newman-labs:houston-emergency-center-active-incidents"


async def load_houston_emergency_center_active_incidents(
    *,
    dataframe: pl.DataFrame,
    started_at: datetime,
    observed_at: datetime,
    warnings: list[str],
    retention_days: int,
    database_url: SecretStr | None = None,
) -> SourceIngestionResult:
    """Reconcile one active set and its lifecycle in one transaction."""
    missing_columns = set(HOUSTON_EMERGENCY_CENTER_COPY_COLUMNS).difference(dataframe.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Houston Emergency Center snapshot is missing columns: {missing}")
    if dataframe.is_empty():
        raise ValueError("Houston Emergency Center active snapshot cannot be empty")
    if retention_days < 1:
        raise ValueError("Houston Emergency Center retention must be at least one day")

    dataframe = dataframe.select(HOUSTON_EMERGENCY_CENTER_COPY_COLUMNS)
    async with get_database_connection(database_url=database_url) as connection:
        await connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
            INGESTION_LOCK_NAME,
        )
        previous_watermark = await connection.fetchval(
            "SELECT max(opened_at) FROM raw.houston_emergency_center_incident"
        )
        latest_observed_at = await connection.fetchval(
            "SELECT max(last_seen_at) FROM raw.houston_emergency_center_incident"
        )
        is_stale_snapshot = latest_observed_at is not None and observed_at < latest_observed_at
        audit_warnings = [*warnings]
        if is_stale_snapshot:
            audit_warnings.append(f"Ignored an out-of-order active snapshot observed at {observed_at.isoformat()}")
        await connection.execute(
            """
            CREATE TEMPORARY TABLE houston_emergency_center_incident_stage
            (LIKE raw.houston_emergency_center_incident INCLUDING DEFAULTS)
            ON COMMIT DROP
            """
        )
        await connection.copy_records_to_table(
            "houston_emergency_center_incident_stage",
            schema_name="pg_temp",
            columns=HOUSTON_EMERGENCY_CENTER_COPY_COLUMNS,
            records=dataframe.iter_rows(),
            timeout=60,
        )
        counts = await connection.fetchrow(
            """
            SELECT
                count(*) FILTER (
                    WHERE NOT $1 AND target.incident_id IS NULL
                ) AS inserted_rows,
                count(*) FILTER (
                    WHERE NOT $1
                      AND target.incident_id IS NOT NULL
                      AND (
                          target.meaningful_hash <> stage.meaningful_hash
                          OR NOT target.is_active
                      )
                ) AS updated_rows,
                count(*) FILTER (
                    WHERE $1
                       OR (
                           target.is_active
                           AND target.meaningful_hash = stage.meaningful_hash
                       )
                ) AS unchanged_rows
            FROM pg_temp.houston_emergency_center_incident_stage AS stage
            LEFT JOIN raw.houston_emergency_center_incident AS target
                USING (incident_id)
            """,
            is_stale_snapshot,
        )
        if counts is None:
            raise RuntimeError("PostgreSQL did not return Houston Emergency Center load counts")

        if not is_stale_snapshot:
            await connection.execute(
                """
                INSERT INTO raw.houston_emergency_center_incident (
                    incident_id,
                    source_incident_id,
                    agency,
                    address,
                    cross_street,
                    longitude,
                    latitude,
                    key_map,
                    opened_at,
                    incident_type,
                    alarm_level,
                    reported_unit_count,
                    units,
                    combined_response,
                    meaningful_hash,
                    last_seen_at,
                    ingested_at,
                    first_seen_at
                )
                SELECT
                    incident_id,
                    source_incident_id,
                    agency,
                    address,
                    cross_street,
                    longitude,
                    latitude,
                    key_map,
                    opened_at,
                    incident_type,
                    alarm_level,
                    reported_unit_count,
                    units,
                    combined_response,
                    meaningful_hash,
                    last_seen_at,
                    ingested_at,
                    last_seen_at
                FROM pg_temp.houston_emergency_center_incident_stage
                ON CONFLICT (incident_id) DO UPDATE SET
                    source_incident_id = EXCLUDED.source_incident_id,
                    agency = EXCLUDED.agency,
                    address = EXCLUDED.address,
                    cross_street = EXCLUDED.cross_street,
                    longitude = EXCLUDED.longitude,
                    latitude = EXCLUDED.latitude,
                    key_map = EXCLUDED.key_map,
                    incident_type = EXCLUDED.incident_type,
                    alarm_level = EXCLUDED.alarm_level,
                    reported_unit_count = EXCLUDED.reported_unit_count,
                    units = EXCLUDED.units,
                    combined_response = EXCLUDED.combined_response,
                    meaningful_hash = EXCLUDED.meaningful_hash,
                    is_active = true,
                    ended_at = NULL,
                    last_seen_at = EXCLUDED.last_seen_at,
                    ingested_at = EXCLUDED.ingested_at
                """
            )
            deactivated_rows = await connection.fetchval(
                """
                WITH deactivated AS (
                    UPDATE raw.houston_emergency_center_incident AS target
                    SET is_active = false,
                        ended_at = $1,
                        ingested_at = $1
                    WHERE target.is_active
                      AND NOT EXISTS (
                          SELECT 1
                          FROM pg_temp.houston_emergency_center_incident_stage
                              AS stage
                          WHERE stage.incident_id = target.incident_id
                      )
                    RETURNING 1
                )
                SELECT count(*) FROM deactivated
                """,
                observed_at,
            )
        else:
            deactivated_rows = 0
        current_watermark = await connection.fetchval(
            "SELECT max(opened_at) FROM raw.houston_emergency_center_incident"
        )
        if current_watermark is None:
            raise RuntimeError("Houston Emergency Center load produced no source watermark")
        if not is_stale_snapshot:
            deleted_rows = await connection.fetchval(
                """
                WITH expired AS (
                    DELETE FROM raw.houston_emergency_center_incident
                    WHERE NOT is_active
                      AND opened_at < $1
                    RETURNING 1
                )
                SELECT count(*) FROM expired
                """,
                observed_at - timedelta(days=retention_days),
            )
        else:
            deleted_rows = 0
        completed_at = datetime.now(UTC)
        result = SourceIngestionResult(
            run_id=uuid4(),
            source_name=SOURCE_NAME,
            started_at=started_at,
            completed_at=completed_at,
            extracted_rows=dataframe.height,
            inserted_rows=int(counts["inserted_rows"]),
            updated_rows=int(counts["updated_rows"]),
            unchanged_rows=int(counts["unchanged_rows"]),
            deactivated_rows=int(deactivated_rows),
            deleted_rows=int(deleted_rows),
            previous_watermark=previous_watermark,
            current_watermark=current_watermark,
            warnings=audit_warnings,
        )
        await insert_successful_ingestion_run(
            connection=connection,
            result=result,
        )
    return result


@flow(
    name="houston-signal-houston-emergency-center-pipeline",
    flow_run_name="houston-emergency-center-active-incidents-{environment}",
    timeout_seconds=600,
    retries=2,
    retry_delay_seconds=30,
)
async def run_houston_emergency_center_pipeline(
    environment: EnvironmentMode = settings.environment,
) -> SourceIngestionResult:
    """Observe the active set and retain its 365-day incident history."""
    started_at = datetime.now(UTC)
    database_url = await get_managed_database_url(
        environment=environment,
        role=DatabaseRole.OWNER,
    )
    try:
        extract = await get_houston_emergency_center_active_incidents()
        if extract is None:
            raise RuntimeError(  # ruff: ignore[raise-within-try]
                "Houston Emergency Center active-incident extraction failed"
            )
        result = await load_houston_emergency_center_active_incidents(
            dataframe=prepare_houston_emergency_center_snapshot(
                records=extract.records,
                observed_at=started_at,
            ),
            started_at=started_at,
            observed_at=started_at,
            warnings=extract.warnings,
            retention_days=RETENTION_DAYS,
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
            logger.exception("Houston Emergency Center failure audit could not be persisted")
        raise

    logger.info(
        f"Houston Emergency Center ingestion completed: "
        f"extracted={result.extracted_rows} inserted={result.inserted_rows} "
        f"updated={result.updated_rows} unchanged={result.unchanged_rows} "
        f"deactivated={result.deactivated_rows}"
    )
    return result


if __name__ == "__main__":
    asyncio.run(run_houston_emergency_center_pipeline())
