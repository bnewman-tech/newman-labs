"""Houston Emergency Center extraction and source transformation."""

import logging
import ssl
from datetime import UTC, datetime

import httpx
import polars as pl
from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
)

from labs.houston_signal.integrations.houston_emergency_center.schemas import (
    HoustonEmergencyCenterArcGISResponse,
    HoustonEmergencyCenterExtract,
    HoustonEmergencyCenterIncident,
)
from libs.core.http import WaitRetryAfterOrExponential, read_bounded_json_response
from libs.core.logger import get_logger

logger = get_logger(__name__)

SOURCE_NAME = "houston_emergency_center"
SOURCE_URL = "https://mycity2.houstontx.gov/pubgis01/rest/services/HEC/HEC_Active_Incidents/MapServer/0"
SOURCE_FIELDS = (
    "UID",
    "Agency",
    "Address",
    "CrossStreet",
    "CALL_TIME",
    "IncidentType",
    "ALARM_LEVEL",
    "NO_UNITS",
    "Units",
    "LONGITUDE",
    "LATITUDE",
    "KeyMap",
    "CombinedResponse",
)
MAX_RESPONSE_BYTES = 8 * 1024 * 1024


def parse_houston_emergency_center_active_incidents(
    payload: object,
) -> list[HoustonEmergencyCenterIncident]:
    """Validate and normalize the complete active-incident response."""
    if not isinstance(payload, dict):
        raise TypeError("ArcGIS returned a non-object JSON payload")
    if "error" in payload:
        raise RuntimeError(f"ArcGIS returned an error: {payload['error']!r}")

    response = HoustonEmergencyCenterArcGISResponse.model_validate(payload)
    observed_fields = {field.name for field in response.fields}
    missing_fields = set(SOURCE_FIELDS) - observed_fields
    if missing_fields:
        missing = ", ".join(sorted(missing_fields))
        raise ValueError(f"Houston Emergency Center source is missing required fields: {missing}")
    if response.exceeded_transfer_limit:
        raise ValueError("Houston Emergency Center source exceeded its transfer limit")

    incidents: list[HoustonEmergencyCenterIncident] = []
    for feature in response.features:
        record = feature.attributes
        units = [unit.strip() for unit in record.units.split(",") if unit.strip()] if record.units is not None else []
        if len(units) != record.reported_unit_count:
            raise ValueError(
                "Houston Emergency Center incident "
                f"{record.source_incident_id} reports "
                f"{record.reported_unit_count} units but lists {len(units)}"
            )
        incidents.append(
            HoustonEmergencyCenterIncident(
                source_incident_id=record.source_incident_id,
                agency=record.agency,
                address=record.address,
                cross_street=record.cross_street,
                longitude=record.longitude,
                latitude=record.latitude,
                key_map=record.key_map,
                opened_at=record.opened_at.astimezone(UTC),
                incident_type=record.incident_type,
                alarm_level=(str(record.alarm_level) if record.alarm_level is not None else None),
                reported_unit_count=record.reported_unit_count,
                units=units,
                combined_response=record.combined_response,
            )
        )
    if not incidents:
        raise ValueError("Houston Emergency Center returned no active incidents")
    return incidents


async def get_houston_emergency_center_active_incidents() -> HoustonEmergencyCenterExtract | None:
    """Fetch and validate the current Houston Emergency Center active set."""
    try:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(5),
            wait=WaitRetryAfterOrExponential(max_wait_time=60),
            retry=retry_if_exception_type((httpx.HTTPError, ssl.SSLError)),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        ):
            with attempt:
                async with httpx.AsyncClient(timeout=30) as client:
                    async with client.stream(
                        "GET",
                        f"{SOURCE_URL}/query",
                        params={
                            "where": "1=1",
                            "outFields": ",".join(SOURCE_FIELDS),
                            "orderByFields": "UID ASC",
                            "resultRecordCount": 2_000,
                            "returnGeometry": False,
                            "f": "json",
                        },
                    ) as response:
                        response.raise_for_status()
                        payload, _ = await read_bounded_json_response(
                            response=response,
                            max_bytes=MAX_RESPONSE_BYTES,
                        )
                    return HoustonEmergencyCenterExtract(
                        records=parse_houston_emergency_center_active_incidents(payload),
                        warnings=[
                            (
                                "Houston Emergency Center publishes an incomplete "
                                "active snapshot; some incidents between polls may not "
                                "be observed"
                            )
                        ],
                    )
    except httpx.HTTPStatusError as exception:
        logger.exception(
            "get_houston_emergency_center_active_incidents Error: "
            f"{exception.response.status_code} "
            f"{exception.request.url.copy_with(query=None)}"
        )
    except Exception as exception:
        logger.exception(f"get_houston_emergency_center_active_incidents Error: {type(exception).__name__}")
    return None


def prepare_houston_emergency_center_snapshot(
    *,
    records: list[HoustonEmergencyCenterIncident],
    observed_at: datetime,
) -> pl.DataFrame:
    """Create one load row for every active incident in the observation."""
    if not records:
        raise ValueError("Houston Emergency Center returned no active incidents")
    return pl.DataFrame([
        {
            **record.model_dump(),
            "incident_id": record.incident_id,
            "meaningful_hash": record.meaningful_hash(),
            "last_seen_at": observed_at,
            "ingested_at": observed_at,
        }
        for record in records
    ]).unique(subset=["incident_id"], keep="last", maintain_order=True)
