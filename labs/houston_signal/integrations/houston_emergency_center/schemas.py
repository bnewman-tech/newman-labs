"""Typed contracts for Houston Emergency Center active incidents."""

import hashlib
import json
from datetime import datetime
from enum import StrEnum

from pydantic import Field

from libs.core.pydantic_base import ExternalSourceModel, NewmanLabsModel


class HoustonEmergencyCenterAgency(StrEnum):
    """Dispatch agencies currently published by the active-incident layer."""

    FIRE = "F"
    POLICE = "P"


class HoustonEmergencyCenterArcGISRecord(ExternalSourceModel):
    """One incident returned by the Houston Emergency Center ArcGIS layer."""

    source_incident_id: int = Field(alias="UID", gt=0)
    agency: HoustonEmergencyCenterAgency = Field(alias="Agency")
    address: str = Field(alias="Address", min_length=1)
    cross_street: str | None = Field(default=None, alias="CrossStreet")
    opened_at: datetime = Field(alias="CALL_TIME")
    incident_type: str = Field(alias="IncidentType", min_length=1)
    alarm_level: int | None = Field(default=None, alias="ALARM_LEVEL")
    reported_unit_count: int = Field(alias="NO_UNITS", ge=0)
    units: str | None = Field(default=None, alias="Units")
    longitude: float = Field(alias="LONGITUDE", ge=-180, le=180)
    latitude: float = Field(alias="LATITUDE", ge=-90, le=90)
    key_map: str | None = Field(default=None, alias="KeyMap")
    combined_response: str = Field(alias="CombinedResponse", min_length=1)


class HoustonEmergencyCenterArcGISFeature(ExternalSourceModel):
    """ArcGIS feature containing one active incident."""

    attributes: HoustonEmergencyCenterArcGISRecord


class ArcGISField(ExternalSourceModel):
    """ArcGIS field metadata used to detect source schema drift."""

    name: str


class HoustonEmergencyCenterArcGISResponse(ExternalSourceModel):
    """Complete response from the all-agency active-incidents query."""

    fields: list[ArcGISField] = Field(max_length=100)
    features: list[HoustonEmergencyCenterArcGISFeature] = Field(max_length=2_000)
    exceeded_transfer_limit: bool = Field(
        default=False,
        alias="exceededTransferLimit",
    )


class HoustonEmergencyCenterIncident(NewmanLabsModel):
    """Normalized Houston Emergency Center incident used by ingestion."""

    source_incident_id: int = Field(gt=0)
    agency: HoustonEmergencyCenterAgency
    address: str = Field(min_length=1)
    cross_street: str | None = None
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    key_map: str | None = None
    opened_at: datetime
    incident_type: str = Field(min_length=1)
    alarm_level: str | None = None
    reported_unit_count: int = Field(ge=0)
    units: list[str] = Field(default_factory=list)
    combined_response: str = Field(min_length=1)

    @property
    def incident_id(self) -> str:
        """Identify an incident despite source ID reuse across agencies or time."""
        opened_at = self.opened_at.isoformat(timespec="seconds")
        return f"{self.agency.value}:{self.source_incident_id}:{opened_at}"

    def meaningful_hash(self) -> str:
        """Hash fields that may change while an incident remains active."""
        payload = self.model_dump(mode="json", exclude={"source_incident_id"})
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()


class HoustonEmergencyCenterExtract(NewmanLabsModel):
    """Validated active incidents and non-fatal source warnings."""

    records: list[HoustonEmergencyCenterIncident]
    warnings: list[str] = Field(default_factory=list)
