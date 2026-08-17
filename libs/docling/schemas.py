"""Typed output from local Docling conversion."""

from docling_core.types.doc import DoclingDocument
from pydantic import Field

from libs.core.pydantic_base import NewmanLabsModel


class DoclingConversion(NewmanLabsModel):
    """One successful local Docling conversion."""

    document: DoclingDocument
    markdown: str = Field(min_length=1)
    page_count: int = Field(ge=1)
    version: str = Field(min_length=1)
