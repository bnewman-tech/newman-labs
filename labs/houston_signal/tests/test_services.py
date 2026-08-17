"""Houston Signal service integration tests."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from labs.houston_signal.integrations.houston_311.functions import (
    prepare_houston_311_snapshot,
)
from labs.houston_signal.integrations.houston_311.scripts.ingest import (
    load_houston_311_snapshot,
)
from labs.houston_signal.integrations.houston_311.tests.fixtures import fixture_records
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
from labs.houston_signal.services import (
    get_houston_signal_map_data,
    get_houston_signal_overview,
    get_houston_signal_platform_status,
)
from libs.database.functions import get_api_session, get_database_connection

CASE_NUMBERS = ("2600000101", "2600000102")


async def delete_fixture_rows(
    *,
    incident_id: str,
    run_ids: list[UUID] | None = None,
) -> None:
    """Remove source and audit rows owned by this integration test."""
    async with get_database_connection() as connection:
        await connection.execute(
            "DELETE FROM raw.houston_311_request WHERE case_number = ANY($1::text[])",
            CASE_NUMBERS,
        )
        await connection.execute(
            "DELETE FROM raw.houston_emergency_center_incident WHERE incident_id = $1",
            incident_id,
        )
        if run_ids:
            await connection.execute(
                "DELETE FROM orchestration.ingestion_run WHERE run_id = ANY($1::uuid[])",
                run_ids,
            )


@pytest.mark.integration
async def test_services_read_two_ingests_through_one_dbt_fact() -> None:
    """Committed source rows flow through dbt into dashboard contracts."""
    observed_at = datetime(2026, 8, 11, 12, tzinfo=UTC)
    records = fixture_records()
    incident = HoustonEmergencyCenterIncident(
        source_incident_id=29_603_410,
        agency=HoustonEmergencyCenterAgency.FIRE,
        address="300 NEWMAN TEST ST",
        longitude=-95.35,
        latitude=29.75,
        key_map="493Z",
        opened_at=observed_at,
        incident_type="FIRE EVENT",
        reported_unit_count=1,
        units=["E010"],
        combined_response="F",
    )

    run_ids: list[UUID] = []
    await delete_fixture_rows(incident_id=incident.incident_id)
    try:
        houston_311_result = await load_houston_311_snapshot(
            dataframe=prepare_houston_311_snapshot(
                records=records,
                observed_at=observed_at,
            ),
            started_at=observed_at,
            extracted_rows=len(records),
            warnings=[],
        )
        run_ids.append(houston_311_result.run_id)
        emergency_center_result = await load_houston_emergency_center_active_incidents(
            dataframe=prepare_houston_emergency_center_snapshot(
                records=[incident],
                observed_at=observed_at,
            ),
            started_at=observed_at,
            observed_at=observed_at,
            warnings=[],
            retention_days=365,
        )
        run_ids.append(emergency_center_result.run_id)

        session_generator = get_api_session()
        session = await anext(session_generator)
        try:
            overview = await get_houston_signal_overview(session=session)
            platform = await get_houston_signal_platform_status(session=session)
            map_data = await get_houston_signal_map_data(
                session=session,
                days=365,
            )
        finally:
            await session_generator.aclose()

        assert overview.current_cases == 2
        assert overview.houston_emergency_center.retained_incidents == 1
        assert overview.houston_emergency_center.active_incidents == 1
        assert {source.source_name for source in platform.sources} == {
            "houston_311",
            "houston_emergency_center",
        }
        assert platform.status == "succeeded"
        assert map_data.matching_request_count == 2
        assert map_data.open_request_count == 1
    finally:
        await delete_fixture_rows(
            incident_id=incident.incident_id,
            run_ids=run_ids,
        )
