"""Registered Newman Labs projects."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class LabPublicationStatus(StrEnum):
    """Publication states shown by the Labs application."""

    IN_DEVELOPMENT = "in_development"
    PUBLIC = "public"


@dataclass(frozen=True, slots=True)
class LabCatalogItem:
    """Application and release metadata for one Lab."""

    slug: str
    name: str
    summary: str
    route_name: str
    status: LabPublicationStatus
    published_at: date | None = None
    source_url: str | None = None


LABS = (
    LabCatalogItem(
        slug="houston-signal",
        name="Houston Signal",
        summary=("Houston public-service activity across 311 requests and active emergency incidents."),
        route_name="houston_signal_overview",
        status=LabPublicationStatus.PUBLIC,
        published_at=date(2026, 8, 11),
        source_url="https://github.com/bnewman-tech/newman-labs",
    ),
    LabCatalogItem(
        slug="invoice-parser",
        name="Invoice Parser",
        summary=("Secure PDF intake and typed invoice extraction with one Pydantic AI agent."),
        route_name="invoice_parser",
        status=LabPublicationStatus.IN_DEVELOPMENT,
        published_at=date(2026, 8, 16),
        source_url="https://github.com/bnewman-tech/newman-labs",
    ),
)
