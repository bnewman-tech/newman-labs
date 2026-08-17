"""Pydantic contracts for Houston Signal web views."""

from datetime import date, datetime
from typing import Literal

from pydantic import Field, field_validator

from libs.core.pydantic_base import NewmanLabsModel


class DailyActivity(NewmanLabsModel):
    """One day of Houston 311 request activity."""

    request_date: date
    request_count: int = Field(ge=0)
    closed_request_count: int = Field(ge=0)


class ActivityBreakdown(NewmanLabsModel):
    """Ranked activity for one product dimension."""

    label: str
    request_count: int = Field(ge=0)


class HoustonEmergencyCenterOverview(NewmanLabsModel):
    """Retained Houston Emergency Center incident summary."""

    retained_incidents: int = Field(ge=0)
    active_incidents: int = Field(ge=0)
    active_fire_incidents: int = Field(ge=0)
    active_police_incidents: int = Field(ge=0)
    latest_incident_at: datetime | None = None
    refreshed_at: datetime | None = None
    incident_types: list[ActivityBreakdown] = Field(default_factory=list)
    coverage_warning: str


class HoustonSignalOverview(NewmanLabsModel):
    """Current summary of the governed Houston 311 data product."""

    current_cases: int = Field(ge=0)
    open_cases: int = Field(ge=0)
    visible_cases_last_30_days: int = Field(ge=0)
    visible_closed_percent_last_30_days: float = Field(ge=0, le=100)
    visible_closure_median_hours_last_90_days: float | None = Field(
        default=None,
        ge=0,
    )
    latest_request_date: date | None = None
    source_refreshed_at: datetime | None = None
    houston_311_coverage_warning: str
    daily_activity: list[DailyActivity] = Field(default_factory=list)
    top_case_types: list[ActivityBreakdown] = Field(default_factory=list)
    district_activity: list[ActivityBreakdown] = Field(default_factory=list)
    houston_emergency_center: HoustonEmergencyCenterOverview


class IngestionRun(NewmanLabsModel):
    """Public operational fields from one source-ingestion audit row."""

    source_name: str
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    extracted_rows: int = Field(default=0, ge=0)
    inserted_rows: int = Field(default=0, ge=0)
    updated_rows: int = Field(default=0, ge=0)
    unchanged_rows: int = Field(default=0, ge=0)
    deactivated_rows: int = Field(default=0, ge=0)
    deleted_rows: int = Field(default=0, ge=0)
    current_watermark: datetime | None = None

    @property
    def source_label(self) -> str:
        """Return the public label for a known Houston Signal source."""
        if self.source_name == "houston_311":
            return "Houston 311"
        if self.source_name == "houston_emergency_center":
            return "Houston Emergency Center"
        return self.source_name.replace("_", " ").title()

    @property
    def loaded_rows(self) -> int:
        """Return retained case rows represented by this load batch."""
        return self.inserted_rows + self.updated_rows + self.unchanged_rows

    @property
    def changed_rows(self) -> int:
        """Return rows whose durable source state changed."""
        return sum((
            self.inserted_rows,
            self.updated_rows,
            self.deactivated_rows,
            self.deleted_rows,
        ))


class HoustonSignalPlatformStatus(NewmanLabsModel):
    """Latest committed ingestion state for the Houston Signal sources."""

    status: str
    latest_run: IngestionRun | None = None
    run_history: list[IngestionRun] = Field(default_factory=list)
    sources: list[IngestionRun] = Field(default_factory=list)


class MapCellGeometry(NewmanLabsModel):
    """GeoJSON centroid for one approximate map cell."""

    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float]


class MapCellProperties(NewmanLabsModel):
    """Public request counts for one approximate map cell."""

    request_count: int = Field(ge=1)
    open_request_count: int = Field(ge=0)
    latest_request_at: datetime
    request_types: list[ActivityBreakdown] = Field(default_factory=list)


class MapCellFeature(NewmanLabsModel):
    """GeoJSON feature for one privacy-reduced Houston 311 map cell."""

    type: Literal["Feature"] = "Feature"
    geometry: MapCellGeometry
    properties: MapCellProperties


class HoustonSignalMapFilters(NewmanLabsModel):
    """Validated filters for the public map-data endpoint."""

    days: int = 30
    status: str | None = Field(default=None, max_length=100)
    district: str | None = Field(default=None, max_length=40)
    case_type: str | None = Field(default=None, max_length=200)

    @field_validator("days")
    @classmethod
    def validate_days(cls, value: int) -> int:
        """Accept only the time windows exposed by the product."""
        if value not in {7, 30, 90, 365}:
            raise ValueError("days must be 7, 30, 90, or 365")
        return value


class HoustonSignalMapFilterOptions(NewmanLabsModel):
    """Filter values available for the current map result."""

    statuses: list[str] = Field(default_factory=list)
    districts: list[str] = Field(default_factory=list)
    request_types: list[str] = Field(default_factory=list)


class HoustonSignalMapData(NewmanLabsModel):
    """Bounded GeoJSON response for the interactive request map."""

    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[MapCellFeature] = Field(default_factory=list)
    matching_request_count: int = Field(ge=0)
    open_request_count: int = Field(ge=0)
    filters: HoustonSignalMapFilterOptions
    days: int = Field(ge=1, le=365)
    cell_limit: int = Field(ge=1)
