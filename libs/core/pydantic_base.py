"""Shared Pydantic model defaults."""

from pydantic import BaseModel, ConfigDict


class NewmanLabsModel(BaseModel):
    """Base model for internal and cross-layer contracts."""

    model_config = ConfigDict(
        extra="forbid",
        validate_by_alias=True,
        validate_by_name=True,
        str_strip_whitespace=True,
    )


class ExternalSourceModel(NewmanLabsModel):
    """Base model for third-party payloads that may add fields over time."""

    model_config = ConfigDict(extra="ignore")
