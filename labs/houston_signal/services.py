"""Database-backed Houston Signal view services."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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

MAP_CELL_LIMIT = 2_000
EXPECTED_SOURCE_COUNT = 2


async def get_houston_signal_overview(
    *,
    session: AsyncSession,
) -> HoustonSignalOverview:
    """Load dashboard measures from the Houston Signal fact."""
    summary_result = await session.execute(
        text(
            """
            WITH latest_source AS (
                SELECT max(activity_at) AS latest_activity_at
                FROM analytics_houston_signal.fact_houston_activity
                WHERE source_name = 'houston_311'
            )
            SELECT
                count(*) AS current_cases,
                count(*) FILTER (WHERE is_active) AS open_cases,
                count(*) FILTER (
                    WHERE activity_at >=
                        (SELECT latest_activity_at FROM latest_source)
                        - interval '29 days'
                ) AS visible_cases_last_30_days,
                coalesce(
                    round(
                        100.0 * count(*) FILTER (
                            WHERE activity_at >=
                                (SELECT latest_activity_at FROM latest_source)
                                - interval '29 days'
                              AND closed_at IS NOT NULL
                        ) / nullif(
                            count(*) FILTER (
                                WHERE activity_at >=
                                    (SELECT latest_activity_at FROM latest_source)
                                    - interval '29 days'
                            ),
                            0
                        ),
                        1
                    ),
                    0
                ) AS visible_closed_percent_last_30_days,
                percentile_cont(0.5) WITHIN GROUP (
                    ORDER BY extract(epoch FROM (closed_at - activity_at)) / 3600
                ) FILTER (
                    WHERE activity_at >=
                        (SELECT latest_activity_at FROM latest_source)
                        - interval '89 days'
                      AND closed_at >= activity_at
                ) AS visible_closure_median_hours_last_90_days,
                max(activity_at)::date AS latest_request_date,
                max(source_refreshed_at) AS source_refreshed_at
            FROM analytics_houston_signal.fact_houston_activity
            WHERE source_name = 'houston_311'
            """
        )
    )
    summary = dict(summary_result.mappings().one())

    daily_result = await session.execute(
        text(
            """
            SELECT
                activity_at::date AS request_date,
                count(*)::integer AS request_count,
                count(*) FILTER (WHERE closed_at IS NOT NULL)::integer
                    AS closed_request_count
            FROM analytics_houston_signal.fact_houston_activity
            WHERE source_name = 'houston_311'
              AND activity_at >= (
                  SELECT max(activity_at) - interval '364 days'
                  FROM analytics_houston_signal.fact_houston_activity
                  WHERE source_name = 'houston_311'
              )
            GROUP BY activity_at::date
            ORDER BY request_date
            """
        )
    )
    daily_activity = [DailyActivity.model_validate(dict(row)) for row in daily_result.mappings()]

    case_type_result = await session.execute(
        text(
            """
            SELECT
                coalesce(activity_type, 'Unclassified') AS label,
                count(*)::integer AS request_count
            FROM analytics_houston_signal.fact_houston_activity
            WHERE source_name = 'houston_311'
              AND activity_at >= (
                  SELECT max(activity_at) - interval '29 days'
                  FROM analytics_houston_signal.fact_houston_activity
                  WHERE source_name = 'houston_311'
              )
            GROUP BY coalesce(activity_type, 'Unclassified')
            ORDER BY request_count DESC, label
            LIMIT 8
            """
        )
    )
    top_case_types = [ActivityBreakdown.model_validate(dict(row)) for row in case_type_result.mappings()]

    district_result = await session.execute(
        text(
            """
            SELECT
                coalesce(council_district, 'Unknown') AS label,
                count(*)::integer AS request_count
            FROM analytics_houston_signal.fact_houston_activity
            WHERE source_name = 'houston_311'
              AND activity_at >= (
                  SELECT max(activity_at) - interval '29 days'
                  FROM analytics_houston_signal.fact_houston_activity
                  WHERE source_name = 'houston_311'
              )
            GROUP BY coalesce(council_district, 'Unknown')
            ORDER BY request_count DESC, label
            """
        )
    )
    district_activity = [ActivityBreakdown.model_validate(dict(row)) for row in district_result.mappings()]

    emergency_center_result = await session.execute(
        text(
            """
            SELECT
                count(*)::integer AS retained_incidents,
                count(*) FILTER (WHERE is_active)::integer AS active_incidents,
                count(*) FILTER (
                    WHERE is_active AND agency = 'F'
                )::integer AS active_fire_incidents,
                count(*) FILTER (
                    WHERE is_active AND agency = 'P'
                )::integer AS active_police_incidents,
                max(activity_at) FILTER (WHERE is_active) AS latest_incident_at,
                max(source_refreshed_at) AS refreshed_at
            FROM analytics_houston_signal.fact_houston_activity
            WHERE source_name = 'houston_emergency_center'
            """
        )
    )
    emergency_center = dict(emergency_center_result.mappings().one())
    emergency_types_result = await session.execute(
        text(
            """
            SELECT
                activity_type AS label,
                count(*)::integer AS request_count
            FROM analytics_houston_signal.fact_houston_activity
            WHERE source_name = 'houston_emergency_center'
              AND is_active
            GROUP BY activity_type
            ORDER BY request_count DESC, activity_type
            LIMIT 6
            """
        )
    )
    emergency_center.update(
        incident_types=[ActivityBreakdown.model_validate(dict(row)) for row in emergency_types_result.mappings()],
        coverage_warning=("Calls that open and close between source refreshes may not appear in the retained history."),
    )

    summary.update(
        daily_activity=daily_activity,
        top_case_types=top_case_types,
        district_activity=district_activity,
        houston_311_coverage_warning=(
            "Houston publishes all open 311 cases and only closed cases from the "
            "last two weeks. Older creation dates therefore show unresolved cases, "
            "not complete historical request volume."
        ),
        houston_emergency_center=HoustonEmergencyCenterOverview.model_validate(emergency_center),
    )
    return HoustonSignalOverview.model_validate(summary)


async def get_houston_signal_platform_status(
    *,
    session: AsyncSession,
) -> HoustonSignalPlatformStatus:
    """Load source-run status directly from the orchestration audit table."""
    history_result = await session.execute(
        text(
            """
            SELECT
                source_name,
                status,
                started_at,
                completed_at,
                extracted_rows,
                inserted_rows,
                updated_rows,
                unchanged_rows,
                deactivated_rows,
                deleted_rows,
                current_watermark
            FROM orchestration.ingestion_run
            ORDER BY completed_at DESC
            LIMIT 8
            """
        )
    )
    run_history = [IngestionRun.model_validate(dict(row)) for row in history_result.mappings()]

    sources_result = await session.execute(
        text(
            """
            SELECT DISTINCT ON (source_name)
                source_name,
                status,
                started_at,
                completed_at,
                extracted_rows,
                inserted_rows,
                updated_rows,
                unchanged_rows,
                deactivated_rows,
                deleted_rows,
                current_watermark
            FROM orchestration.ingestion_run
            ORDER BY source_name, completed_at DESC
            """
        )
    )
    sources = [IngestionRun.model_validate(dict(row)) for row in sources_result.mappings()]
    if not sources:
        status = "not_run"
    elif any(source.status == "failed" for source in sources):
        status = "failed"
    elif len(sources) < EXPECTED_SOURCE_COUNT:
        status = "partial"
    else:
        status = "succeeded"
    return HoustonSignalPlatformStatus(
        status=status,
        latest_run=run_history[0] if run_history else None,
        run_history=run_history,
        sources=sources,
    )


async def get_houston_signal_map_data(
    *,
    session: AsyncSession,
    days: int,
    status: str | None = None,
    district: str | None = None,
    case_type: str | None = None,
) -> HoustonSignalMapData:
    """Return bounded GeoJSON counts rounded to approximate 1 km map cells."""
    base_conditions = [
        "source_name = 'houston_311'",
        "latitude BETWEEN 28.5 AND 30.5",
        "longitude BETWEEN -96.2 AND -94.7",
    ]
    parameters: dict[str, object] = {
        "limit": MAP_CELL_LIMIT,
        "status": status,
        "district": district,
        "case_type": case_type,
    }
    base_conditions.append(
        "activity_at >= ("
        "SELECT max(activity_at) "
        "FROM analytics_houston_signal.fact_houston_activity "
        "WHERE source_name = 'houston_311'"
        ") - make_interval(days => :window_days)"
    )
    parameters["window_days"] = days - 1

    conditions = [
        *base_conditions,
        *(["status = :status"] if status else []),
        *(["council_district = :district"] if district else []),
        *(["activity_type = :case_type"] if case_type else []),
    ]

    where_clause = " AND ".join(conditions)
    status_conditions = [
        *base_conditions,
        *(["council_district = :district"] if district else []),
        *(["activity_type = :case_type"] if case_type else []),
    ]
    district_conditions = [
        *base_conditions,
        *(["status = :status"] if status else []),
        *(["activity_type = :case_type"] if case_type else []),
    ]
    request_type_conditions = [
        *base_conditions,
        *(["status = :status"] if status else []),
        *(["council_district = :district"] if district else []),
    ]

    totals_result = await session.execute(
        text(
            f"""
            SELECT
                count(*)::integer AS matching_request_count,
                count(*) FILTER (WHERE is_active)::integer AS open_request_count
            FROM analytics_houston_signal.fact_houston_activity
            WHERE {where_clause}
            """
        ),
        parameters,
    )
    totals = totals_result.mappings().one()

    filters_result = await session.execute(
        text(
            f"""
            SELECT
                ARRAY(
                    SELECT status
                    FROM analytics_houston_signal.fact_houston_activity
                    WHERE {" AND ".join(status_conditions)}
                      AND status IS NOT NULL
                    GROUP BY status
                    ORDER BY status
                ) AS statuses,
                ARRAY(
                    SELECT council_district
                    FROM analytics_houston_signal.fact_houston_activity
                    WHERE {" AND ".join(district_conditions)}
                      AND council_district IS NOT NULL
                    GROUP BY council_district
                    ORDER BY council_district
                ) AS districts,
                ARRAY(
                    SELECT activity_type
                    FROM analytics_houston_signal.fact_houston_activity
                    WHERE {" AND ".join(request_type_conditions)}
                      AND activity_type IS NOT NULL
                    GROUP BY activity_type
                    ORDER BY activity_type
                ) AS request_types
            """
        ),
        parameters,
    )
    filter_options = HoustonSignalMapFilterOptions.model_validate(dict(filters_result.mappings().one()))

    cells_result = await session.execute(
        text(
            f"""
            WITH filtered AS MATERIALIZED (
                SELECT
                    round(longitude::numeric, 2)::double precision
                        AS cell_longitude,
                    round(latitude::numeric, 2)::double precision
                        AS cell_latitude,
                    coalesce(activity_type, 'Unclassified') AS activity_type,
                    is_active,
                    activity_at
                FROM analytics_houston_signal.fact_houston_activity
                WHERE {where_clause}
            ),
            cell_totals AS (
                SELECT
                    cell_longitude,
                    cell_latitude,
                    count(*)::integer AS request_count,
                    count(*) FILTER (WHERE is_active)::integer
                        AS open_request_count,
                    max(activity_at) AS latest_request_at
                FROM filtered
                GROUP BY cell_longitude, cell_latitude
            ),
            ranked_types AS (
                SELECT
                    cell_longitude,
                    cell_latitude,
                    activity_type,
                    request_count,
                    row_number() OVER (
                        PARTITION BY cell_longitude, cell_latitude
                        ORDER BY request_count DESC, activity_type
                    ) AS type_rank
                FROM (
                    SELECT
                        cell_longitude,
                        cell_latitude,
                        activity_type,
                        count(*)::integer AS request_count
                    FROM filtered
                    GROUP BY cell_longitude, cell_latitude, activity_type
                ) AS counts
            ),
            grouped_types AS (
                SELECT
                    cell_longitude,
                    cell_latitude,
                    CASE
                        WHEN type_rank <= 4 THEN activity_type
                        ELSE 'Other'
                    END AS label,
                    sum(request_count)::integer AS request_count,
                    min(type_rank) AS sort_order
                FROM ranked_types
                GROUP BY
                    cell_longitude,
                    cell_latitude,
                    CASE
                        WHEN type_rank <= 4 THEN activity_type
                        ELSE 'Other'
                    END
            ),
            type_breakdowns AS (
                SELECT
                    cell_longitude,
                    cell_latitude,
                    jsonb_agg(
                        jsonb_build_object(
                            'label', label,
                            'request_count', request_count
                        )
                        ORDER BY sort_order
                    ) AS request_types
                FROM grouped_types
                GROUP BY cell_longitude, cell_latitude
            )
            SELECT
                cell_totals.cell_longitude AS longitude,
                cell_totals.cell_latitude AS latitude,
                cell_totals.request_count,
                cell_totals.open_request_count,
                cell_totals.latest_request_at,
                type_breakdowns.request_types
            FROM cell_totals
            JOIN type_breakdowns USING (cell_longitude, cell_latitude)
            ORDER BY
                cell_totals.latest_request_at DESC,
                cell_totals.cell_latitude,
                cell_totals.cell_longitude
            LIMIT :limit
            """
        ),
        parameters,
    )
    features = [
        MapCellFeature(
            geometry=MapCellGeometry(
                coordinates=(float(row["longitude"]), float(row["latitude"])),
            ),
            properties=MapCellProperties(
                request_count=row["request_count"],
                open_request_count=row["open_request_count"],
                latest_request_at=row["latest_request_at"],
                request_types=[ActivityBreakdown.model_validate(item) for item in row["request_types"]],
            ),
        )
        for row in cells_result.mappings()
    ]
    return HoustonSignalMapData(
        features=features,
        matching_request_count=totals["matching_request_count"],
        open_request_count=totals["open_request_count"],
        filters=filter_options,
        days=days,
        cell_limit=MAP_CELL_LIMIT,
    )
