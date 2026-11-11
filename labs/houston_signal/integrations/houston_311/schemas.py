"""Houston 311 source contracts."""

import hashlib
import json
from datetime import datetime

from pydantic import Field

from libs.core.pydantic_base import ExternalSourceModel


class Houston311Record(ExternalSourceModel):
    """One ServiceNow 311 request mapped to retained database columns."""

    source_object_id: int = Field(alias="OBJECTID")
    case_number: str = Field(alias="CASE_NUMBER", min_length=1)
    case_number_365: str | None = None
    incident_address: str | None = Field(default=None, alias="ADDRESS")
    latitude: float | None = Field(default=None, alias="LATITUDE")
    longitude: float | None = Field(default=None, alias="LONGITUDE")
    status: str | None = Field(default=None, alias="STATUS")
    created_at: datetime = Field(alias="CREATED_ON")
    due_at: datetime | None = Field(default=None, alias="RESOLVE_BY")
    closed_at: datetime | None = Field(default=None, alias="CLOSED_ON")
    title: str | None = Field(default=None, alias="TITLE")
    case_type: str | None = Field(default=None, alias="CASE_TYPE")
    sla_time: str | None = Field(default=None, alias="SLA")
    service_area: str | None = None
    council_district: str | None = Field(default=None, alias="COUNCIL_DISTRICT")
    key_map: str | None = None
    department: str | None = Field(default=None, alias="DEPARTMENT")
    division: str | None = Field(default=None, alias="DIVISION")
    state_code: str | None = Field(default=None, alias="STATE_CODE")
    state_code_name: str | None = None
    swm_quadrant: str | None = Field(default=None, alias="SWM_QUADRANT")
    recycling_quadrant: str | None = Field(default=None, alias="RECYCLING_QUADRANT")
    heavy_trash_quadrant: str | None = Field(
        default=None,
        alias="HEAVY_TRASH_QUADRANT",
    )
    resolution_notes: str | None = Field(default=None, alias="NOTES")

    def meaningful_hash(self) -> str:
        """Hash current source fields, excluding row IDs and retained legacy columns."""
        payload = self.model_dump(
            mode="json",
            exclude={"source_object_id", "case_number_365", "service_area", "key_map", "state_code_name"},
        )
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()


class Houston311ArcGISFeature(ExternalSourceModel):
    """ArcGIS feature wrapper."""

    attributes: Houston311Record


class Houston311ArcGISQueryResponse(ExternalSourceModel):
    """One ArcGIS query page."""

    features: list[Houston311ArcGISFeature] = Field(max_length=2_000)
    exceeded_transfer_limit: bool = Field(
        default=False,
        alias="exceededTransferLimit",
    )
