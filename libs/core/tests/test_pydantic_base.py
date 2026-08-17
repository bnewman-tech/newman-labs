"""Shared Pydantic contract tests."""

import pytest
from pydantic import ValidationError

from libs.core.pydantic_base import ExternalSourceModel, NewmanLabsModel


class InternalContract(NewmanLabsModel):
    """Internal contract used by this test module."""

    name: str


class SourceContract(ExternalSourceModel):
    """External source contract used by this test module."""

    source_id: int


def test_internal_contract_rejects_unknown_fields() -> None:
    """Internal contracts fail when their shape drifts."""
    with pytest.raises(ValidationError):
        InternalContract.model_validate({"name": "newman", "unexpected": True})


def test_external_contract_ignores_additive_source_fields() -> None:
    """External contracts accept additive fields from upstream APIs."""
    contract = SourceContract.model_validate({"source_id": 1, "new_field": "value"})

    assert contract == SourceContract(source_id=1)
