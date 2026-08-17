"""Source-ingestion audit contracts."""

from datetime import datetime
from uuid import UUID

from pydantic import Field

from libs.core.pydantic_base import NewmanLabsModel


class SourceIngestionResult(NewmanLabsModel):
    """Outcome of one transactional source ingestion."""

    run_id: UUID
    source_name: str
    started_at: datetime
    completed_at: datetime
    extracted_rows: int = Field(ge=0)
    inserted_rows: int = Field(ge=0)
    updated_rows: int = Field(ge=0)
    unchanged_rows: int = Field(ge=0)
    deactivated_rows: int = Field(default=0, ge=0)
    deleted_rows: int = Field(default=0, ge=0)
    previous_watermark: datetime | None = None
    current_watermark: datetime | None = None
    warnings: list[str] = Field(default_factory=list)
