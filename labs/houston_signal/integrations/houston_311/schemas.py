"""Houston 311 source contracts."""

import hashlib
import json
from datetime import datetime

from pydantic import Field

from libs.core.pydantic_base import ExternalSourceModel


class Houston311Record(ExternalSourceModel):
    """One normalized Houston 311 service request."""

    source_object_id: int = Field(alias="ObjectID")
    case_number: str = Field(alias="CaseNumber", min_length=1)
    case_number_365: str | None = Field(default=None, alias="CaseNumber365")
    incident_address: str | None = Field(default=None, alias="IncidentAddress")
    latitude: float | None = Field(default=None, alias="Latitude")
    longitude: float | None = Field(default=None, alias="Longitude")
    status: str | None = Field(default=None, alias="Status")
    created_at: datetime = Field(alias="CreatedDate")
    due_at: datetime | None = Field(default=None, alias="DueDate")
    closed_at: datetime | None = Field(default=None, alias="ClosedDate")
    title: str | None = Field(default=None, alias="Title")
    case_type: str | None = Field(default=None, alias="CaseType")
    sla_time: str | None = Field(default=None, alias="SLATime")
    service_area: str | None = Field(default=None, alias="ServiceArea")
    council_district: str | None = Field(default=None, alias="CouncilDistrict")
    key_map: str | None = Field(default=None, alias="KeyMap")
    department: str | None = Field(default=None, alias="Department")
    division: str | None = Field(default=None, alias="Division")
    state_code: str | None = Field(default=None, alias="StateCode")
    state_code_name: str | None = Field(default=None, alias="StateCodeName")
    swm_quadrant: str | None = Field(default=None, alias="SWMQuadrant")
    recycling_quadrant: str | None = Field(default=None, alias="RecyclingQuadrant")
    heavy_trash_quadrant: str | None = Field(
        default=None,
        alias="HeavyTrashQuadrant",
    )
    resolution_notes: str | None = Field(default=None, alias="ResolutionNotes")

    def meaningful_hash(self) -> str:
        """Hash source-owned fields while excluding unstable ArcGIS row IDs."""
        payload = self.model_dump(
            mode="json",
            exclude={"source_object_id"},
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
