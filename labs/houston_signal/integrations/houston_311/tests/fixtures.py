"""Reusable Houston 311 test fixtures."""

import json
from pathlib import Path

from labs.houston_signal.integrations.houston_311.schemas import (
    Houston311ArcGISQueryResponse,
    Houston311Record,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "houston_311_page.json"


def fixture_records() -> list[Houston311Record]:
    """Return the validated two-record fixture."""
    page = Houston311ArcGISQueryResponse.model_validate(json.loads(FIXTURE_PATH.read_text()))
    return [feature.attributes for feature in page.features]
