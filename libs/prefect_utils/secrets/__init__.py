"""Prefect Secret runtime loading."""

from libs.prefect_utils.secrets.functions import (
    PrefectSecret,
    get_secret,
)

__all__ = [
    "PrefectSecret",
    "get_secret",
]
