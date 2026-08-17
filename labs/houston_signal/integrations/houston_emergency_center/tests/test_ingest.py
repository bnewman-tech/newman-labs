"""Houston Emergency Center Prefect entrypoint tests."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import SecretStr

from labs.houston_signal.integrations.houston_emergency_center import functions
from labs.houston_signal.integrations.houston_emergency_center.schemas import (
    HoustonEmergencyCenterExtract,
)
from labs.houston_signal.integrations.houston_emergency_center.scripts import ingest
from libs.core.dependencies import EnvironmentMode
from libs.database.schemas import SourceIngestionResult

from .test_functions import source_payload


async def test_ingest_wrapper_loads_the_complete_active_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Prefect entrypoint coordinates extraction and lifecycle persistence."""
    database_url = SecretStr("postgresql://newman@dev/labs")
    extract = HoustonEmergencyCenterExtract(
        records=functions.parse_houston_emergency_center_active_incidents(source_payload())
    )
    completed_at = datetime.now(UTC)
    result = SourceIngestionResult(
        run_id=uuid4(),
        source_name="houston_emergency_center",
        started_at=completed_at,
        completed_at=completed_at,
        extracted_rows=2,
        inserted_rows=2,
        updated_rows=0,
        unchanged_rows=0,
    )
    load_snapshot = AsyncMock(return_value=result)
    monkeypatch.setattr(
        ingest,
        "get_houston_emergency_center_active_incidents",
        AsyncMock(return_value=extract),
    )
    monkeypatch.setattr(
        ingest,
        "get_managed_database_url",
        AsyncMock(return_value=database_url),
    )
    monkeypatch.setattr(
        ingest,
        "load_houston_emergency_center_active_incidents",
        load_snapshot,
    )

    actual = await ingest.run_houston_emergency_center_pipeline.fn(environment=EnvironmentMode.DEV)

    load_snapshot.assert_awaited_once()
    call = load_snapshot.await_args
    assert call is not None
    assert call.kwargs["retention_days"] == 365
    assert actual == result
