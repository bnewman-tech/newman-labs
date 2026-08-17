"""Houston 311 PostgreSQL ingestion tests."""

import asyncio
from datetime import UTC, datetime, timedelta

import asyncpg
import polars as pl
import pytest

from labs.houston_signal.integrations.houston_311.functions import (
    prepare_houston_311_snapshot,
)
from labs.houston_signal.integrations.houston_311.schemas import Houston311Record
from labs.houston_signal.integrations.houston_311.scripts.ingest import (
    get_houston_311_source_object_id_watermark,
    load_houston_311_snapshot,
)
from labs.houston_signal.integrations.houston_311.tests.fixtures import (
    fixture_records,
)
from libs.database.functions import get_database_connection
from libs.database.schemas import SourceIngestionResult

FIXTURE_CASE_NUMBERS = ("2600000101", "2600000102")


@pytest.mark.integration
async def test_source_object_id_watermark_has_one_numeric_type() -> None:
    """The cursor and raw-table fallback can be queried on a clean database."""
    watermark = await get_houston_311_source_object_id_watermark()

    assert watermark is None or isinstance(watermark, int)


async def delete_fixture_rows() -> None:
    """Remove rows owned by this integration test."""
    async with get_database_connection() as connection:
        await connection.execute(
            "DELETE FROM raw.houston_311_request WHERE case_number = ANY($1::text[])",
            FIXTURE_CASE_NUMBERS,
        )
        await connection.execute(
            "DELETE FROM orchestration.ingestion_run WHERE source_name = 'houston_311'",
        )


@pytest.mark.integration
async def test_load_is_idempotent_and_counts_material_updates() -> None:
    """An identical rerun is unchanged and a mutable-field edit is one update."""
    records = fixture_records()
    started_at = datetime.now(UTC)

    async def load(records: list[Houston311Record]) -> SourceIngestionResult:
        return await load_houston_311_snapshot(
            dataframe=prepare_houston_311_snapshot(
                records=records,
                observed_at=started_at,
            ),
            started_at=started_at,
            extracted_rows=len(records),
            warnings=[],
        )

    await delete_fixture_rows()
    try:
        first = await load(records)
        second = await load(records)
        changed_records = [
            records[0].model_copy(update={"status": "Service Completed"}),
            records[1],
        ]
        third = await load(changed_records)

        assert (first.inserted_rows, first.updated_rows, first.unchanged_rows) == (
            2,
            0,
            0,
        )
        assert (second.inserted_rows, second.updated_rows, second.unchanged_rows) == (
            0,
            0,
            2,
        )
        assert (
            second.inserted_rows,
            second.updated_rows,
            second.deactivated_rows,
            second.deleted_rows,
        ) == (0, 0, 0, 0)
        assert (third.inserted_rows, third.updated_rows, third.unchanged_rows) == (
            0,
            1,
            1,
        )
        async with get_database_connection() as connection:
            row_count = await connection.fetchval(
                "SELECT count(*) FROM raw.houston_311_request WHERE case_number = ANY($1::text[])",
                FIXTURE_CASE_NUMBERS,
            )
            run_count = await connection.fetchval(
                "SELECT count(*) FROM orchestration.ingestion_run WHERE source_name = 'houston_311'",
            )
        assert row_count == 2
        assert run_count == 3
    finally:
        await delete_fixture_rows()


@pytest.mark.integration
async def test_load_preserves_an_old_case_after_a_newer_case_arrives() -> None:
    """Storage retains the full observed baseline instead of a rolling year."""
    records = fixture_records()
    records[1] = records[1].model_copy(update={"created_at": datetime(2020, 1, 1, tzinfo=UTC)})
    started_at = datetime.now(UTC)

    await delete_fixture_rows()
    try:
        await load_houston_311_snapshot(
            dataframe=prepare_houston_311_snapshot(
                records=records,
                observed_at=started_at,
            ),
            started_at=started_at,
            extracted_rows=len(records),
            warnings=[],
        )

        async with get_database_connection() as connection:
            stored_cases = await connection.fetchval(
                "SELECT count(*) FROM raw.houston_311_request WHERE case_number = ANY($1::text[])",
                FIXTURE_CASE_NUMBERS,
            )

        assert stored_cases == 2
    finally:
        await delete_fixture_rows()


@pytest.mark.integration
async def test_concurrent_loads_are_serialized_for_accurate_audits() -> None:
    """Concurrent snapshots report one insert and one unchanged observation."""
    records = fixture_records()
    observed_at = datetime.now(UTC)
    dataframe = prepare_houston_311_snapshot(
        records=records,
        observed_at=observed_at,
    )

    async def load() -> SourceIngestionResult:
        return await load_houston_311_snapshot(
            dataframe=dataframe,
            started_at=observed_at,
            extracted_rows=len(records),
            warnings=[],
        )

    await delete_fixture_rows()
    try:
        results = await asyncio.gather(load(), load())

        assert sorted((result.inserted_rows, result.unchanged_rows) for result in results) == [(0, 2), (2, 0)]
    finally:
        await delete_fixture_rows()


@pytest.mark.integration
async def test_older_observation_cannot_regress_current_state() -> None:
    """A late-arriving older observation preserves newer fields and timestamps."""
    records = fixture_records()
    newer_observed_at = datetime.now(UTC)
    older_observed_at = newer_observed_at - timedelta(minutes=1)
    newer_records = [
        records[0].model_copy(update={"status": "Service Completed"}),
        records[1],
    ]

    async def load(
        records: list[Houston311Record],
        *,
        observed_at: datetime,
    ) -> SourceIngestionResult:
        return await load_houston_311_snapshot(
            dataframe=prepare_houston_311_snapshot(
                records=records,
                observed_at=observed_at,
            ),
            started_at=observed_at,
            extracted_rows=len(records),
            warnings=[],
        )

    await delete_fixture_rows()
    try:
        await load(newer_records, observed_at=newer_observed_at)
        older = await load(records, observed_at=older_observed_at)

        async with get_database_connection() as connection:
            row = await connection.fetchrow(
                """
                SELECT status, first_seen_at, last_seen_at
                FROM raw.houston_311_request
                WHERE case_number = $1
                """,
                FIXTURE_CASE_NUMBERS[0],
            )

        assert older.unchanged_rows == 2
        assert row is not None
        assert row["status"] == "Service Completed"
        assert row["first_seen_at"] == older_observed_at
        assert row["last_seen_at"] == newer_observed_at
    finally:
        await delete_fixture_rows()


@pytest.mark.integration
async def test_failed_upsert_rolls_back_rows_and_audit_history() -> None:
    """A database error leaves neither source rows nor a success audit record."""
    records = fixture_records()
    observed_at = datetime.now(UTC)
    dataframe = prepare_houston_311_snapshot(
        records=records,
        observed_at=observed_at,
    )
    duplicate_dataframe = pl.concat([dataframe, dataframe.head(1)])

    await delete_fixture_rows()
    try:
        with pytest.raises(asyncpg.CardinalityViolationError):
            await load_houston_311_snapshot(
                dataframe=duplicate_dataframe,
                started_at=observed_at,
                extracted_rows=len(records) + 1,
                warnings=[],
            )

        async with get_database_connection() as connection:
            row_count = await connection.fetchval(
                "SELECT count(*) FROM raw.houston_311_request WHERE case_number = ANY($1::text[])",
                FIXTURE_CASE_NUMBERS,
            )
            run_count = await connection.fetchval(
                "SELECT count(*) FROM orchestration.ingestion_run WHERE source_name = 'houston_311'",
            )
        assert row_count == 0
        assert run_count == 0
    finally:
        await delete_fixture_rows()
