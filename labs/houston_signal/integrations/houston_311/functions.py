"""Houston 311 extraction and source-specific transformation."""

from __future__ import annotations

import logging
import ssl
from typing import TYPE_CHECKING

import httpx
import polars as pl
from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
)

from labs.houston_signal.integrations.houston_311.schemas import (
    Houston311ArcGISQueryResponse,
    Houston311Record,
)
from libs.core.http import WaitRetryAfterOrExponential, read_bounded_json_response
from libs.core.logger import get_logger

if TYPE_CHECKING:
    from datetime import datetime

logger = get_logger(__name__)

SOURCE_NAME = "houston_311"
SOURCE_URL = "https://mycity2.houstontx.gov/pubgis01/rest/services/311/Houston311_RecentServiceRequests/FeatureServer/3"
PAGE_SIZE = 2_000
OBJECT_ID_OVERLAP = 2_000
MAX_RECORDS = 50_000
MAX_RESPONSE_BYTES = 64 * 1024 * 1024


async def get_houston_311_records(
    *,
    source_object_id_watermark: int | None = None,
) -> list[Houston311Record] | None:
    """Fetch a bootstrap snapshot or an overlapping incremental ObjectID window."""
    where_clauses = ["1=1"]
    if source_object_id_watermark is not None:
        where_clauses = [
            f"ObjectID > {max(source_object_id_watermark - OBJECT_ID_OVERLAP, 0)}",
            "1=1",
        ]

    try:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(5),
            wait=WaitRetryAfterOrExponential(max_wait_time=60),
            retry=retry_if_exception_type((httpx.HTTPError, ssl.SSLError)),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        ):
            with attempt:
                async with httpx.AsyncClient(timeout=60) as client:
                    records: list[Houston311Record] = []
                    for where in where_clauses:
                        records = []
                        offset = 0
                        downloaded_bytes = 0
                        while True:
                            async with client.stream(
                                "GET",
                                f"{SOURCE_URL}/query",
                                params={
                                    "where": where,
                                    "outFields": "*",
                                    "orderByFields": "ObjectID ASC",
                                    "resultOffset": offset,
                                    "resultRecordCount": PAGE_SIZE,
                                    "returnGeometry": False,
                                    "f": "json",
                                },
                            ) as response:
                                response.raise_for_status()
                                payload, page_bytes = await read_bounded_json_response(
                                    response=response,
                                    max_bytes=MAX_RESPONSE_BYTES - downloaded_bytes,
                                )
                            downloaded_bytes += page_bytes
                            if not isinstance(payload, dict):
                                raise TypeError("ArcGIS returned a non-object query response")
                            if "error" in payload:
                                raise RuntimeError(f"ArcGIS returned an error: {payload['error']!r}")
                            page = Houston311ArcGISQueryResponse.model_validate(payload)
                            if len(records) + len(page.features) > MAX_RECORDS:
                                raise ValueError("ArcGIS response exceeds the configured record limit")
                            records.extend(feature.attributes for feature in page.features)
                            if not page.exceeded_transfer_limit:
                                break
                            if not page.features:
                                raise RuntimeError("ArcGIS pagination stopped making progress")
                            offset += len(page.features)

                        if records:
                            break
                    return records
    except httpx.HTTPStatusError as exception:
        logger.exception(
            f"get_houston_311_records Error: {exception.response.status_code} "
            f"{exception.request.url.copy_with(query=None)}"
        )
    except Exception as exception:
        logger.exception(f"get_houston_311_records Error: {type(exception).__name__}")
    return None


def prepare_houston_311_snapshot(
    *,
    records: list[Houston311Record],
    observed_at: datetime,
) -> pl.DataFrame:
    """Create one latest observed row for every case returned by the source."""
    if not records:
        raise ValueError("Houston 311 returned no service requests")

    return (
        pl
        .DataFrame([
            {
                **record.model_dump(),
                "meaningful_hash": record.meaningful_hash(),
                "last_seen_at": observed_at,
                "ingested_at": observed_at,
            }
            for record in records
        ])
        .sort("source_object_id")
        .unique(
            subset=["case_number"],
            keep="last",
            maintain_order=True,
        )
    )
