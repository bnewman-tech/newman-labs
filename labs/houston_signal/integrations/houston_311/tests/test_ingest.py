"""Houston 311 ingest wrapper tests."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import SecretStr

from labs.houston_signal.integrations.houston_311.scripts import ingest
from labs.houston_signal.integrations.houston_311.tests.fixtures import (
    fixture_records,
)
from libs.core.dependencies import EnvironmentMode
from libs.database.schemas import SourceIngestionResult


async def test_ingest_wrapper_loads_validated_source_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Prefect entrypoint coordinates extraction and database commit."""
    records = fixture_records()
    completed_at = datetime.now(UTC)
    database_url = SecretStr("postgresql://newman@dev/labs")
    get_records = AsyncMock(return_value=records)
    load_snapshot = AsyncMock(
        return_value=SourceIngestionResult(
            run_id=uuid4(),
            source_name="houston_311",
            started_at=completed_at,
            completed_at=completed_at,
            extracted_rows=2,
            inserted_rows=2,
            updated_rows=0,
            unchanged_rows=0,
            current_watermark=completed_at,
        )
    )
    monkeypatch.setattr(ingest, "get_houston_311_records", get_records)
    monkeypatch.setattr(
        ingest,
        "get_houston_311_source_object_id_watermark",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(ingest, "load_houston_311_snapshot", load_snapshot)
    monkeypatch.setattr(
        ingest,
        "get_managed_database_url",
        AsyncMock(return_value=database_url),
    )

    result = await ingest.run_houston_311_pipeline.fn(environment=EnvironmentMode.DEV)

    get_records.assert_awaited_once_with(source_object_id_watermark=None)
    load_snapshot.assert_awaited_once()
    load_call = load_snapshot.await_args
    assert load_call is not None
    assert load_call.kwargs["source_object_id_watermark"] == max(record.source_object_id for record in records)
    assert result.inserted_rows == 2


async def test_ingest_wrapper_audits_extraction_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed Prefect attempt records its safe exception type and still fails."""
    database_url = SecretStr("postgresql://newman@localhost/labs")
    record_failure = AsyncMock()
    monkeypatch.setattr(
        ingest,
        "get_managed_database_url",
        AsyncMock(return_value=database_url),
    )
    monkeypatch.setattr(
        ingest,
        "get_houston_311_source_object_id_watermark",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        ingest,
        "get_houston_311_records",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(ingest, "record_failed_ingestion_run", record_failure)

    with pytest.raises(RuntimeError, match="Houston 311 extraction failed"):
        await ingest.run_houston_311_pipeline.fn(environment=EnvironmentMode.DEV)

    record_failure.assert_awaited_once()
    call = record_failure.await_args
    assert call is not None
    assert call.kwargs["source_name"] == "houston_311"
    assert call.kwargs["error_type"] == "RuntimeError"
    assert call.kwargs["database_url"] == database_url
