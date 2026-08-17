"""Houston Emergency Center extraction and transformation tests."""

from datetime import UTC, datetime

import httpx
import pytest
import respx

from labs.houston_signal.integrations.houston_emergency_center import functions
from labs.houston_signal.integrations.houston_emergency_center.functions import (
    SOURCE_FIELDS,
    get_houston_emergency_center_active_incidents,
    parse_houston_emergency_center_active_incidents,
    prepare_houston_emergency_center_snapshot,
)


def source_payload() -> dict[str, object]:
    """Return a representative Houston Emergency Center ArcGIS response."""
    return {
        "fields": [{"name": field} for field in SOURCE_FIELDS],
        "features": [
            {
                "attributes": {
                    "UID": 29_603_408,
                    "Agency": "F",
                    "Address": "100 NEWMAN TEST RD",
                    "CrossStreet": "BLK NEWMAN PARK DR",
                    "CALL_TIME": 1_784_647_260_000,
                    "IncidentType": "APARTMENT FIRE",
                    "ALARM_LEVEL": 1,
                    "NO_UNITS": 2,
                    "Units": "E015,L015",
                    "LONGITUDE": -95.36,
                    "LATITUDE": 29.76,
                    "KeyMap": "452T",
                    "CombinedResponse": "F",
                }
            },
            {
                "attributes": {
                    "UID": 29_603_409,
                    "Agency": "P",
                    "Address": "200 NEWMAN TEST RD",
                    "CrossStreet": None,
                    "CALL_TIME": 1_784_647_320_000,
                    "IncidentType": "POLICE EVENT",
                    "ALARM_LEVEL": 0,
                    "NO_UNITS": 1,
                    "Units": "A010",
                    "LONGITUDE": -95.37,
                    "LATITUDE": 29.77,
                    "KeyMap": "493Z",
                    "CombinedResponse": "P",
                }
            },
        ],
        "exceededTransferLimit": False,
    }


def test_active_incident_parser_builds_stable_typed_records() -> None:
    """ArcGIS features become UTC records with source-issued identities."""
    incidents = parse_houston_emergency_center_active_incidents(source_payload())

    assert len(incidents) == 2
    assert incidents[0].opened_at == datetime(2026, 7, 21, 15, 21, tzinfo=UTC)
    assert incidents[0].units == ["E015", "L015"]
    assert incidents[1].cross_street is None
    assert incidents[0].agency.value == "F"
    assert incidents[1].agency.value == "P"
    assert incidents[1].combined_response == "P"
    assert incidents[0].incident_id == "F:29603408:2026-07-21T15:21:00+00:00"
    assert incidents[0].model_copy(update={"units": ["E015"]}).meaningful_hash() != incidents[0].meaningful_hash()


def test_parse_houston_emergency_center_active_incidents_rejects_schema_drift() -> None:
    """A removed ArcGIS field fails before records reach persistence."""
    payload = source_payload()
    payload["fields"] = [{"name": field} for field in SOURCE_FIELDS if field != "NO_UNITS"]

    with pytest.raises(ValueError, match="missing required fields: NO_UNITS"):
        parse_houston_emergency_center_active_incidents(payload)


def test_parse_houston_emergency_center_active_incidents_rejects_unit_mismatch() -> None:
    """Conflicting source unit totals fail closed before lifecycle reconciliation."""
    payload = source_payload()
    features = payload["features"]
    assert isinstance(features, list)
    first_feature = features[0]
    assert isinstance(first_feature, dict)
    attributes = first_feature["attributes"]
    assert isinstance(attributes, dict)
    attributes["NO_UNITS"] = 3

    with pytest.raises(ValueError, match="reports 3 units but lists 2"):
        parse_houston_emergency_center_active_incidents(payload)


@respx.mock
async def test_get_houston_emergency_center_active_incidents_queries_all_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The integration requests every agency and preserves the coverage warning."""
    source_url = "https://example.com/houston_emergency_center"
    monkeypatch.setattr(functions, "SOURCE_URL", source_url)
    route = respx.get(f"{source_url}/query").mock(return_value=httpx.Response(200, json=source_payload()))

    extract = await get_houston_emergency_center_active_incidents()

    assert extract is not None
    assert len(extract.records) == 2
    assert "incomplete active snapshot" in extract.warnings[0]
    assert route.called
    request = route.calls.last.request
    assert request.url.params["where"] == "1=1"
    assert request.url.params["returnGeometry"] == "false"
    assert request.url.params["outFields"] == ",".join(SOURCE_FIELDS)


@respx.mock
async def test_get_houston_emergency_center_retries_a_transient_http_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The integration owns its bounded HTTP retry scope."""
    source_url = "https://example.com/houston_emergency_center"
    monkeypatch.setattr(functions, "SOURCE_URL", source_url)
    monkeypatch.setattr(
        functions.WaitRetryAfterOrExponential,
        "__call__",
        lambda _self, _state: 0.0,
    )
    route = respx.get(f"{source_url}/query").mock(
        side_effect=[
            httpx.ReadError("connection reset"),
            httpx.Response(200, json=source_payload()),
        ]
    )

    extract = await get_houston_emergency_center_active_incidents()

    assert extract is not None
    assert len(extract.records) == 2
    assert route.call_count == 2


def test_prepare_houston_emergency_center_snapshot_deduplicates_source_rows() -> None:
    """One active incident is loaded once when ArcGIS repeats a feature."""
    incident = parse_houston_emergency_center_active_incidents(source_payload())[0]
    observed_at = datetime(2026, 7, 21, 16, 0, tzinfo=UTC)

    dataframe = prepare_houston_emergency_center_snapshot(
        records=[incident, incident],
        observed_at=observed_at,
    )

    assert dataframe.height == 1
    assert dataframe.row(0, named=True)["incident_id"] == incident.incident_id


def test_prepare_houston_emergency_center_snapshot_scopes_identity_by_agency() -> None:
    """Equal source identifiers from different agencies remain distinct incidents."""
    fire_incident, police_incident = parse_houston_emergency_center_active_incidents(source_payload())
    police_incident = police_incident.model_copy(
        update={
            "source_incident_id": fire_incident.source_incident_id,
            "opened_at": fire_incident.opened_at,
        }
    )

    dataframe = prepare_houston_emergency_center_snapshot(
        records=[fire_incident, police_incident],
        observed_at=datetime(2026, 7, 21, 16, 0, tzinfo=UTC),
    )

    assert set(dataframe["incident_id"]) == {
        "F:29603408:2026-07-21T15:21:00+00:00",
        "P:29603408:2026-07-21T15:21:00+00:00",
    }
