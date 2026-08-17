"""Typed blob-storage contracts."""

from pydantic import Field

from libs.core.pydantic_base import NewmanLabsModel


class BlobUpload(NewmanLabsModel):
    """Content and metadata required to create one private object."""

    bucket: str = Field(min_length=1)
    key: str = Field(min_length=1)
    content: bytes = Field(repr=False)
    content_type: str = Field(min_length=1)


class StoredBlob(NewmanLabsModel):
    """Metadata for one private stored object."""

    bucket: str = Field(min_length=1)
    key: str = Field(min_length=1)
    content_type: str = Field(min_length=1)
    content_sha256: str = Field(min_length=64, max_length=64)
    etag: str | None = Field(default=None, min_length=1)


class BlobContents(StoredBlob):
    """A stored object and its downloaded content."""

    content: bytes = Field(repr=False)
