"""Houston Signal web route tests."""

from collections.abc import AsyncGenerator
from datetime import date, datetime
from typing import cast

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.labs.main import app
from apps.labs.routes import houston_signal
from labs.houston_signal.schemas import (
    ActivityBreakdown,
    DailyActivity,
    HoustonEmergencyCenterOverview,
    HoustonSignalMapData,
    HoustonSignalMapFilterOptions,
    HoustonSignalOverview,
    HoustonSignalPlatformStatus,
    IngestionRun,
    MapCellFeature,
    MapCellGeometry,
    MapCellProperties,
)
from libs.database.functions import get_api_session


async def test_houston_signal_product_renders_database_backed_views(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The product page and map API render typed service results."""

    async def override_session() -> AsyncGenerator[AsyncSession]:
        yield cast("AsyncSession", object())

    async def overview_service(*, session: AsyncSession) -> HoustonSignalOverview:
        del session
        return HoustonSignalOverview(
            current_cases=49_248,
            open_cases=12_100,
            visible_cases_last_30_days=8_340,
            visible_closed_percent_last_30_days=68.4,
            visible_closure_median_hours_last_90_days=51.6,
            latest_request_date=date(2026, 7, 21),
            source_refreshed_at=datetime.fromisoformat("2026-07-21T12:00:00+00:00"),
            houston_311_coverage_warning=(
                "Houston publishes all open 311 cases and only closed cases from the last two weeks."
            ),
            daily_activity=[
                DailyActivity(
                    request_date=date(2026, 7, 21),
                    request_count=280,
                    closed_request_count=190,
                )
            ],
            top_case_types=[
                ActivityBreakdown(
                    label="Missed garbage pickup",
                    request_count=820,
                )
            ],
            district_activity=[
                ActivityBreakdown(
                    label="B",
                    request_count=940,
                ),
                ActivityBreakdown(
                    label="Unknown",
                    request_count=44,
                ),
            ],
            houston_emergency_center=HoustonEmergencyCenterOverview(
                retained_incidents=1_420,
                active_incidents=42,
                active_fire_incidents=30,
                active_police_incidents=12,
                latest_incident_at=datetime.fromisoformat("2026-07-21T11:55:00+00:00"),
                refreshed_at=datetime.fromisoformat("2026-07-21T12:00:00+00:00"),
                incident_types=[ActivityBreakdown(label="FIRE EVENT", request_count=7)],
                coverage_warning=(
                    "The Houston Emergency Center publishes only the active incident "
                    "snapshot; completed calls "
                    "leave the feed."
                ),
            ),
        )

    async def platform_service(*, session: AsyncSession) -> HoustonSignalPlatformStatus:
        del session
        completed_at = datetime.fromisoformat("2026-07-21T12:05:00+00:00")
        run = IngestionRun(
            source_name="houston_311",
            status="succeeded",
            completed_at=completed_at,
            extracted_rows=118_227,
            inserted_rows=0,
            updated_rows=0,
            unchanged_rows=49_248,
        )
        return HoustonSignalPlatformStatus(
            status="succeeded",
            latest_run=run,
            run_history=[run],
            sources=[
                IngestionRun(
                    source_name="houston_emergency_center",
                    status="succeeded",
                    completed_at=completed_at,
                    extracted_rows=42,
                    inserted_rows=42,
                )
            ],
        )

    async def map_service(
        *,
        session: AsyncSession,
        days: int,
        status: str | None = None,
        district: str | None = None,
        case_type: str | None = None,
    ) -> HoustonSignalMapData:
        del session, status, district, case_type
        return HoustonSignalMapData(
            features=[
                MapCellFeature(
                    geometry=MapCellGeometry(coordinates=(-95.36, 29.76)),
                    properties=MapCellProperties(
                        request_count=4,
                        open_request_count=1,
                        latest_request_at=datetime.fromisoformat("2026-07-21T10:00:00+00:00"),
                        request_types=[
                            ActivityBreakdown(
                                label="Missed garbage pickup",
                                request_count=4,
                            )
                        ],
                    ),
                )
            ],
            matching_request_count=4,
            open_request_count=1,
            filters=HoustonSignalMapFilterOptions(
                statuses=["Closed", "Open"],
                districts=["B"],
                request_types=["Missed garbage pickup"],
            ),
            days=days,
            cell_limit=2_000,
        )

    monkeypatch.setattr(
        houston_signal,
        "get_houston_signal_overview",
        overview_service,
    )
    monkeypatch.setattr(
        houston_signal,
        "get_houston_signal_platform_status",
        platform_service,
    )
    monkeypatch.setattr(houston_signal, "get_houston_signal_map_data", map_service)
    app.dependency_overrides[get_api_session] = override_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            product_response = await client.get("/houston-signal/")
            map_response = await client.get(
                "/houston-signal/data/map",
                params={"days": 30, "district": "B"},
            )
    finally:
        app.dependency_overrides.clear()

    assert product_response.status_code == 200
    for expected_text in (
        "A daily public-data view of Houston service requests",
        'aria-selected="true" aria-controls="overview-panel"',
        "What Houston is publishing now",
        "current source snapshot, not a complete historical count",
        "Cases in the current feed",
        "Visible cases by creation date",
        "only closed cases from the last two weeks",
        "42 active incidents",
        "1,420",
        "Retained by Houston Signal",
        "Active Fire calls",
        "Active Police calls",
        "Unknown district",
        "Houston Emergency Center",
        'aria-current="page"',
        "Brian Newman portfolio",
        "Overview",
        "Map",
        "Pipeline",
        "Request concentration",
        "Selected cell",
        "Two sources, one reporting model",
        "Houston 311 and Houston Emergency Center data are ingested",
        "Schedules and observes both typed source ingests",
    ):
        assert expected_text in product_response.text

    assert map_response.status_code == 200
    assert map_response.headers["cache-control"] == ("public, max-age=300, stale-while-revalidate=60")
    payload = map_response.json()
    assert payload["type"] == "FeatureCollection"
    assert payload["matching_request_count"] == 4
    assert payload["open_request_count"] == 1
    assert payload["features"][0]["properties"]["request_count"] == 4
    assert payload["features"][0]["properties"]["request_types"] == [
        {"label": "Missed garbage pickup", "request_count": 4}
    ]
    assert payload["filters"]["districts"] == ["B"]
    assert "case_number" not in map_response.text
    assert "incident_address" not in map_response.text
    assert product_response.headers["content-encoding"] == "gzip"


async def test_map_rejects_unsupported_time_windows() -> None:
    """Only the documented map windows reach PostgreSQL."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/houston-signal/data/map",
            params={"days": 999_999_999_999},
        )
        all_history = await client.get(
            "/houston-signal/data/map",
            params={"days": "all"},
        )

    assert response.status_code == 422
    assert all_history.status_code == 422


def test_ingestion_run_reports_loaded_and_changed_rows() -> None:
    """Row accounting distinguishes loaded rows from durable changes."""
    run = IngestionRun(
        source_name="houston_311",
        status="succeeded",
        extracted_rows=118_227,
        unchanged_rows=49_248,
    )

    assert run.loaded_rows == 49_248
    assert run.changed_rows == 0
