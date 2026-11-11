"""Houston 311 extraction and transformation tests."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from labs.houston_signal.integrations.houston_311 import functions
from labs.houston_signal.integrations.houston_311.functions import (
    get_houston_311_records,
    prepare_houston_311_snapshot,
)
from labs.houston_signal.integrations.houston_311.tests.fixtures import (
    fixture_records,
)


@respx.mock
async def test_get_all_records_paginates_and_ignores_additive_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ArcGIS pages validate records while tolerating added source fields."""
    source_url = "https://example.com/houston-311/3"
    monkeypatch.setattr(functions, "SOURCE_URL", source_url)
    records = fixture_records()
    first_record = records[0].model_dump(mode="json", by_alias=True)
    first_record["NewAdditiveField"] = "ignored"
    pages = [
        {
            "features": [{"attributes": first_record}],
            "exceededTransferLimit": True,
        },
        {
            "features": [
                {
                    "attributes": records[1].model_dump(
                        mode="json",
                        by_alias=True,
                    )
                }
            ],
            "exceededTransferLimit": False,
        },
    ]
    query_route = respx.get(f"{source_url}/query").mock(side_effect=[httpx.Response(200, json=page) for page in pages])

    result = await get_houston_311_records()

    assert result is not None
    assert [record.case_number for record in result] == [
        "2600000101",
        "2600000102",
    ]
    assert query_route.call_count == 2
    assert query_route.calls[0].request.url.params["where"] == "1=1"


@respx.mock
async def test_get_records_retries_a_transient_http_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The integration owns its bounded HTTP retry scope."""
    source_url = "https://example.com/houston-311/3"
    record = fixture_records()[0]
    monkeypatch.setattr(functions, "SOURCE_URL", source_url)
    monkeypatch.setattr(
        functions.WaitRetryAfterOrExponential,
        "__call__",
        lambda _self, _state: 0.0,
    )
    route = respx.get(f"{source_url}/query").mock(
        side_effect=[
            httpx.ReadError("connection reset"),
            httpx.Response(
                200,
                json={
                    "features": [{"attributes": record.model_dump(mode="json", by_alias=True)}],
                    "exceededTransferLimit": False,
                },
            ),
        ]
    )

    assert await get_houston_311_records() == [record]
    assert route.call_count == 2


@respx.mock
async def test_daily_snapshot_refreshes_changed_cases_after_object_ids_reset() -> None:
    """Rebuilt IDs must not skip changed old cases or new high-ID cases."""
    old_case, new_case = fixture_records()
    changed_case = old_case.model_copy(update={"source_object_id": 1, "status": "Closed"})
    new_case = new_case.model_copy(update={"source_object_id": 52_387})
    route = respx.get(f"{functions.SOURCE_URL}/query").mock(
        return_value=httpx.Response(
            200,
            json={
                "features": [
                    {"attributes": record.model_dump(mode="json", by_alias=True)} for record in (changed_case, new_case)
                ]
            },
        ),
    )

    assert await get_houston_311_records() == [changed_case, new_case]
    assert route.calls[0].request.url.params["where"] == "1=1"
    assert route.calls[0].request.url.params["orderByFields"] == "OBJECTID ASC"
    assert "CREATED_ON" in route.calls[0].request.url.params["outFields"]
    assert "CaseNumber365" not in route.calls[0].request.url.params["outFields"]


@respx.mock
async def test_get_records_rejects_a_source_record_flood(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pagination stops before source records can exceed the ingestion budget."""
    source_url = "https://example.com/houston-311/3"
    records = fixture_records()
    monkeypatch.setattr(functions, "SOURCE_URL", source_url)
    monkeypatch.setattr(functions, "MAX_RECORDS", 1)
    monkeypatch.setattr(functions.WaitRetryAfterOrExponential, "__call__", lambda _self, _state: 0.0)
    route = respx.get(f"{source_url}/query").mock(
        return_value=httpx.Response(
            200,
            json={
                "features": [{"attributes": record.model_dump(mode="json", by_alias=True)} for record in records],
                "exceededTransferLimit": False,
            },
        )
    )

    assert await get_houston_311_records() is None
    assert route.call_count == 1


def test_meaningful_hash_tracks_mutable_fields_not_arcgis_row_ids() -> None:
    """Mutable source data changes the hash while ArcGIS row churn does not."""
    record = fixture_records()[0]

    assert record.model_copy(update={"source_object_id": 999}).meaningful_hash() == record.meaningful_hash()
    assert record.model_copy(update={"status": "Service Completed"}).meaningful_hash() != record.meaningful_hash()


def test_prepare_snapshot_keeps_latest_object_id_per_case() -> None:
    """Repeated source snapshots collapse to the highest ArcGIS ObjectID."""
    original = fixture_records()[0]
    latest = original.model_copy(update={"source_object_id": original.source_object_id + 1, "status": "Closed"})

    dataframe = prepare_houston_311_snapshot(
        records=[latest, original],
        observed_at=datetime(2026, 7, 21, tzinfo=UTC),
    )

    assert dataframe.height == 1
    assert dataframe.row(0, named=True)["source_object_id"] == latest.source_object_id
    assert dataframe.row(0, named=True)["status"] == "Closed"


def test_prepare_snapshot_retains_all_observed_cases() -> None:
    """Bootstrap transformation does not discard older source records."""
    recent = fixture_records()[0]
    old = fixture_records()[1].model_copy(update={"created_at": recent.created_at - timedelta(days=365)})

    dataframe = prepare_houston_311_snapshot(
        records=[old, recent],
        observed_at=datetime(2026, 7, 21, tzinfo=UTC),
    )

    assert set(dataframe["case_number"].to_list()) == {
        old.case_number,
        recent.case_number,
    }


def test_prepare_snapshot_rejects_future_created_dates() -> None:
    """A malformed source timestamp cannot poison durable watermarks."""
    observed_at = datetime(2026, 7, 21, tzinfo=UTC)
    record = fixture_records()[0].model_copy(update={"created_at": observed_at + timedelta(minutes=6)})

    with pytest.raises(ValueError, match="future CREATED_ON"):
        prepare_houston_311_snapshot(records=[record], observed_at=observed_at)
