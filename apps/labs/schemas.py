"""Public Newman Labs API contracts."""

from datetime import date
from uuid import UUID

from pydantic import AnyHttpUrl, Field

from libs.core.pydantic_base import NewmanLabsModel


class PublicLab(NewmanLabsModel):
    """One released Lab available to external consumers."""

    slug: str
    name: str
    summary: str
    url: AnyHttpUrl
    source_url: AnyHttpUrl | None = None
    published_at: date


class PublicLabIndex(NewmanLabsModel):
    """Newest-first collection of released Labs."""

    items: list[PublicLab] = Field(default_factory=list)


class InvoiceExtractionJobResponse(NewmanLabsModel):
    """Managed extraction identifiers plus an unguessable polling capability."""

    document_id: UUID
    flow_run_id: UUID
    access_token: str = Field(min_length=64, max_length=64)
