"""Houston Emergency Center PostgreSQL lifecycle ingestion tests."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from labs.houston_signal.integrations.houston_emergency_center.functions import (
    prepare_houston_emergency_center_snapshot,
)
from labs.houston_signal.integrations.houston_emergency_center.schemas import (
    HoustonEmergencyCenterAgency,
    HoustonEmergencyCenterIncident,
)
from labs.houston_signal.integrations.houston_emergency_center.scripts.ingest import (
    load_houston_emergency_center_active_incidents,
)
from libs.database.functions import get_database_connection
from libs.database.schemas import SourceIngestionResult


def fixture_incidents() -> list[HoustonEmergencyCenterIncident]:
    """Return two synthetic incidents with stable identities."""
    return [
        HoustonEmergencyCenterIncident(
            source_incident_id=1,
            agency=HoustonEmergencyCenterAgency.FIRE,
            address="100 NEWMAN TEST ST",
            longitude=-95.36,
            latitude=29.76,
            key_map="500A",
            opened_at=datetime(2026, 8, 11, 1, 0, tzinfo=UTC),
            incident_type="ALARM TEST",
            reported_unit_count=1,
            units=["E001"],
            combined_response="F",
        ),
        HoustonEmergencyCenterIncident(
            source_incident_id=2,
            agency=HoustonEmergencyCenterAgency.POLICE,
            address="200 NEWMAN TEST ST",
            longitude=-95.37,
            latitude=29.77,
            key_map="500B",
            opened_at=datetime(2026, 8, 11, 1, 5, tzinfo=UTC),
            incident_type="POLICE TEST",
            reported_unit_count=1,
            units=["P001"],
            combined_response="P",
        ),
    ]


async def delete_fixture_rows(*, incident_ids: list[str]) -> None:
    """Remove rows owned by this integration test."""
    async with get_database_connection() as connection:
        await connection.execute(
            "DELETE FROM raw.houston_emergency_center_incident WHERE incident_id = ANY($1::text[])",
            incident_ids,
        )
        await connection.execute(
            "DELETE FROM orchestration.ingestion_run WHERE source_name = 'houston_emergency_center'",
        )


@pytest.mark.integration
async def test_load_reconciles_deactivation_and_reactivation() -> None:
    """Successive active snapshots preserve the observed incident lifecycle."""
    async with get_database_connection() as connection:
        existing_rows = await connection.fetchval("SELECT count(*) FROM raw.houston_emergency_center_incident")
    if existing_rows:
        pytest.skip("Houston Emergency Center lifecycle reconciliation requires an empty test database")

    incidents = fixture_incidents()
    incident_ids = [incident.incident_id for incident in incidents]
    started_at = datetime.now(UTC)

    async def load(
        records: list[HoustonEmergencyCenterIncident],
        *,
        observed_at: datetime,
    ) -> SourceIngestionResult:
        return await load_houston_emergency_center_active_incidents(
            dataframe=prepare_houston_emergency_center_snapshot(
                records=records,
                observed_at=observed_at,
            ),
            started_at=started_at,
            observed_at=observed_at,
            warnings=[],
            retention_days=365,
        )

    await delete_fixture_rows(incident_ids=incident_ids)
    try:
        initial_results = await asyncio.gather(
            load(incidents, observed_at=started_at),
            load(
                incidents,
                observed_at=started_at + timedelta(minutes=1),
            ),
        )
        third = await load(
            incidents[:1],
            observed_at=started_at + timedelta(minutes=2),
        )

        async with get_database_connection() as connection:
            deactivated = await connection.fetchrow(
                "SELECT is_active, ended_at FROM raw.houston_emergency_center_incident WHERE incident_id = $1",
                incidents[1].incident_id,
            )

        fourth = await load(
            incidents,
            observed_at=started_at + timedelta(minutes=3),
        )

        async with get_database_connection() as connection:
            reactivated = await connection.fetchrow(
                "SELECT is_active, ended_at FROM raw.houston_emergency_center_incident WHERE incident_id = $1",
                incidents[1].incident_id,
            )

        assert sorted((result.inserted_rows, result.unchanged_rows) for result in initial_results) == [(0, 2), (2, 0)]
        assert (third.unchanged_rows, third.deactivated_rows) == (1, 1)
        assert deactivated is not None
        assert (deactivated["is_active"], deactivated["ended_at"] is not None) == (
            False,
            True,
        )
        assert (fourth.unchanged_rows, fourth.updated_rows) == (1, 1)
        assert reactivated is not None
        assert (reactivated["is_active"], reactivated["ended_at"]) == (True, None)
    finally:
        await delete_fixture_rows(incident_ids=incident_ids)


@pytest.mark.integration
async def test_retention_deletes_only_inactive_incidents_older_than_365_days() -> None:
    """An old active incident remains until a later snapshot closes it."""
    async with get_database_connection() as connection:
        existing_rows = await connection.fetchval("SELECT count(*) FROM raw.houston_emergency_center_incident")
    if existing_rows:
        pytest.skip("Houston Emergency Center retention requires an empty test database")

    observed_at = datetime.now(UTC)
    old_incident, current_incident = fixture_incidents()
    old_incident = old_incident.model_copy(update={"opened_at": observed_at - timedelta(days=400)})
    incident_ids = [old_incident.incident_id, current_incident.incident_id]

    await delete_fixture_rows(incident_ids=incident_ids)
    try:
        initial = await load_houston_emergency_center_active_incidents(
            dataframe=prepare_houston_emergency_center_snapshot(
                records=[old_incident, current_incident],
                observed_at=observed_at,
            ),
            started_at=observed_at,
            observed_at=observed_at,
            warnings=[],
            retention_days=365,
        )
        following = await load_houston_emergency_center_active_incidents(
            dataframe=prepare_houston_emergency_center_snapshot(
                records=[current_incident],
                observed_at=observed_at + timedelta(minutes=1),
            ),
            started_at=observed_at + timedelta(minutes=1),
            observed_at=observed_at + timedelta(minutes=1),
            warnings=[],
            retention_days=365,
        )

        async with get_database_connection() as connection:
            old_row = await connection.fetchval(
                "SELECT count(*) FROM raw.houston_emergency_center_incident WHERE incident_id = $1",
                old_incident.incident_id,
            )

        assert initial.deleted_rows == 0
        assert (following.deactivated_rows, following.deleted_rows) == (1, 1)
        assert old_row == 0
    finally:
        await delete_fixture_rows(incident_ids=incident_ids)
