"""Tests for S3-compatible blob CRUD operations."""

import hashlib
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from pydantic import SecretStr

from libs.blob_storage import functions
from libs.blob_storage.functions import (
    create_blobs,
    create_download_url,
    delete_blob,
    delete_blobs_before,
    read_blob,
    update_blob,
)
from libs.blob_storage.schemas import BlobUpload, StoredBlob
from libs.core.dependencies import EnvironmentMode, settings
from libs.prefect_utils.secrets import PrefectSecret


class BlobBody:
    """Minimal asynchronous response body used by the storage test double."""

    def __init__(self, content: bytes) -> None:
        """Set the response content."""
        self.content = content
        self.closed = False

    async def read(self) -> bytes:
        """Return the configured object content."""
        return self.content

    def close(self) -> None:
        """Record response-body cleanup."""
        self.closed = True


@pytest.fixture(autouse=True)
def configure_blob_storage(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Configure harmless storage credentials for every CRUD test."""
    secrets = {
        PrefectSecret.NEON_OBJECT_STORAGE_DEV_ENDPOINT: SecretStr(f"https://{functions.DEVELOPMENT_STORAGE_HOST}"),
        PrefectSecret.NEON_OBJECT_STORAGE_DEV_ACCESS_KEY_ID: SecretStr("newman-access-key"),
        PrefectSecret.NEON_OBJECT_STORAGE_DEV_SECRET_ACCESS_KEY: SecretStr("newman-secret-key"),
    }
    get_secret = AsyncMock(side_effect=lambda *, name: secrets[name])
    monkeypatch.setattr(functions, "get_secret", get_secret)
    return get_secret


def client_session(client: AsyncMock) -> MagicMock:
    """Return a mocked aiobotocore session for one client."""
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=None)
    session = MagicMock()
    session.create_client.return_value = context
    return session


async def test_create_blobs_reuses_one_authenticated_client(
    configure_blob_storage: AsyncMock,
) -> None:
    """A document's object writes load credentials and open storage once."""
    client = AsyncMock()
    client.put_object.side_effect = [
        {"ETag": '"newman-original-etag"'},
        {"ETag": '"newman-markdown-etag"'},
        {"ETag": '"newman-docling-etag"'},
    ]
    session = client_session(client)

    with patch("libs.blob_storage.functions.get_session", return_value=session):
        stored = await create_blobs(
            blobs=[
                BlobUpload(
                    bucket="newman-labs",
                    key=f"documents/newman/{name}",
                    content=content,
                    content_type=content_type,
                )
                for name, content, content_type in (
                    ("original.pdf", b"%PDF-1.7", "application/pdf"),
                    ("document.md", b"# Invoice", "text/markdown"),
                    ("docling.json", b"{}", "application/json"),
                )
            ]
        )

    assert len(stored) == 3
    assert session.create_client.call_count == 1
    assert configure_blob_storage.await_count == 3
    assert client.put_object.await_count == 3
    assert all(call.kwargs["IfNoneMatch"] == "*" for call in client.put_object.await_args_list)


async def test_create_blobs_removes_partial_writes() -> None:
    """A failed batch does not leave an incomplete document in storage."""
    client = AsyncMock()
    client.put_object.side_effect = [
        {"ETag": '"newman-original-etag"'},
        RuntimeError("newman storage failure"),
    ]
    session = client_session(client)

    with (
        patch("libs.blob_storage.functions.get_session", return_value=session),
        pytest.raises(RuntimeError, match="newman storage failure"),
    ):
        await create_blobs(
            blobs=[
                BlobUpload(
                    bucket="newman-labs",
                    key="documents/newman/original.pdf",
                    content=b"%PDF-1.7",
                    content_type="application/pdf",
                ),
                BlobUpload(
                    bucket="newman-labs",
                    key="documents/newman/document.md",
                    content=b"# Invoice",
                    content_type="text/markdown",
                ),
            ]
        )

    client.delete_object.assert_awaited_once_with(
        Bucket="newman-labs",
        Key="documents/newman/original.pdf",
    )


async def test_read_blob_verifies_checksum_and_closes_body() -> None:
    """Read returns typed content and always closes the streaming body."""
    content = b"newman stored content"
    body = BlobBody(content)
    client = AsyncMock()
    client.get_object.return_value = {
        "Body": body,
        "ContentType": "text/plain",
        "ETag": '"newman-etag"',
        "Metadata": {"sha256": hashlib.sha256(content).hexdigest()},
    }
    session = client_session(client)

    with patch("libs.blob_storage.functions.get_session", return_value=session):
        blob = await read_blob(
            bucket="newman-labs",
            key="documents/newman.txt",
        )

    assert blob.content == content
    assert body.closed is True


async def test_read_blob_rejects_checksum_mismatch() -> None:
    """Corrupt or inconsistent object metadata is not silently accepted."""
    client = AsyncMock()
    client.get_object.return_value = {
        "Body": BlobBody(b"newman stored content"),
        "Metadata": {"sha256": "0" * 64},
    }
    session = client_session(client)

    with (
        patch("libs.blob_storage.functions.get_session", return_value=session),
        pytest.raises(ValueError, match="checksum"),
    ):
        await read_blob(
            bucket="newman-labs",
            key="documents/newman.txt",
        )


async def test_create_download_url_is_short_lived() -> None:
    """Private downloads use a temporary URL for the requested object."""
    client = AsyncMock()
    client.generate_presigned_url.return_value = "https://storage.example/download"
    session = client_session(client)

    with patch("libs.blob_storage.functions.get_session", return_value=session):
        url = await create_download_url(
            bucket="newman-labs",
            key="documents/newman.txt",
        )

    assert url == "https://storage.example/download"
    client.generate_presigned_url.assert_awaited_once_with(
        "get_object",
        Params={
            "Bucket": "newman-labs",
            "Key": "documents/newman.txt",
        },
        ExpiresIn=300,
    )


async def test_update_blob_requires_current_etag() -> None:
    """Update uses optimistic concurrency instead of a blind overwrite."""
    client = AsyncMock()
    client.put_object.return_value = {"ETag": '"updated-etag"'}
    session = client_session(client)

    with patch("libs.blob_storage.functions.get_session", return_value=session):
        await update_blob(
            stored=StoredBlob(
                bucket="newman-labs",
                key="documents/newman.txt",
                content_type="text/plain",
                content_sha256="0" * 64,
                etag='"current-etag"',
            ),
            content=b"updated",
        )

    assert client.put_object.await_args.kwargs["IfMatch"] == '"current-etag"'


async def test_delete_blob_is_direct_and_idempotent() -> None:
    """Delete delegates to S3's idempotent object deletion contract."""
    client = AsyncMock()
    session = client_session(client)

    with patch("libs.blob_storage.functions.get_session", return_value=session):
        await delete_blob(
            bucket="newman-labs",
            key="documents/newman.txt",
        )

    client.delete_object.assert_awaited_once_with(
        Bucket="newman-labs",
        Key="documents/newman.txt",
    )


async def test_delete_blobs_before_pages_and_preserves_recent_objects() -> None:
    """Transient object cleanup follows pagination and the exact cutoff."""
    cutoff = datetime(2026, 8, 16, tzinfo=UTC)
    client = AsyncMock()
    client.list_objects_v2.side_effect = [
        {
            "Contents": [
                {
                    "Key": "document-processing/old-source.pdf",
                    "LastModified": cutoff - timedelta(seconds=1),
                },
                {
                    "Key": "document-processing/current-result.json",
                    "LastModified": cutoff + timedelta(seconds=1),
                },
            ],
            "NextContinuationToken": "newman-next-page",
        },
        {
            "Contents": [
                {
                    "Key": "document-processing/old-result.json",
                    "LastModified": cutoff,
                }
            ]
        },
    ]
    session = client_session(client)

    with patch("libs.blob_storage.functions.get_session", return_value=session):
        deleted = await delete_blobs_before(
            bucket="newman-labs",
            prefix="document-processing/",
            before=cutoff,
        )

    assert deleted == 2
    assert client.list_objects_v2.await_args_list == [
        call(Bucket="newman-labs", Prefix="document-processing/"),
        call(
            Bucket="newman-labs",
            Prefix="document-processing/",
            ContinuationToken="newman-next-page",
        ),
    ]
    assert client.delete_object.await_args_list == [
        call(Bucket="newman-labs", Key="document-processing/old-source.pdf"),
        call(Bucket="newman-labs", Key="document-processing/old-result.json"),
    ]


async def test_production_blob_client_uses_production_prefect_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production storage cannot reuse branch-scoped development credentials."""
    secrets = {
        PrefectSecret.NEON_OBJECT_STORAGE_PROD_ENDPOINT: SecretStr(f"https://{functions.PRODUCTION_STORAGE_HOST}"),
        PrefectSecret.NEON_OBJECT_STORAGE_PROD_ACCESS_KEY_ID: SecretStr("newman-access-key"),
        PrefectSecret.NEON_OBJECT_STORAGE_PROD_SECRET_ACCESS_KEY: SecretStr("newman-secret-key"),
    }
    get_secret = AsyncMock(side_effect=lambda *, name: secrets[name])
    session = client_session(AsyncMock())
    monkeypatch.setattr(settings, "environment", EnvironmentMode.PROD)
    monkeypatch.setattr(functions, "get_secret", get_secret)

    with patch("libs.blob_storage.functions.get_session", return_value=session):
        async with functions.get_blob_client():
            pass

    assert get_secret.await_args_list == [
        call(name=PrefectSecret.NEON_OBJECT_STORAGE_PROD_ENDPOINT),
        call(name=PrefectSecret.NEON_OBJECT_STORAGE_PROD_ACCESS_KEY_ID),
        call(name=PrefectSecret.NEON_OBJECT_STORAGE_PROD_SECRET_ACCESS_KEY),
    ]


async def test_development_blob_client_rejects_production_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A copied production credential cannot make development writes reach it."""
    secrets = {
        PrefectSecret.NEON_OBJECT_STORAGE_DEV_ENDPOINT: SecretStr(f"https://{functions.PRODUCTION_STORAGE_HOST}"),
        PrefectSecret.NEON_OBJECT_STORAGE_DEV_ACCESS_KEY_ID: SecretStr("newman-access-key"),
        PrefectSecret.NEON_OBJECT_STORAGE_DEV_SECRET_ACCESS_KEY: SecretStr("newman-secret-key"),
    }
    monkeypatch.setattr(
        functions,
        "get_secret",
        AsyncMock(side_effect=lambda *, name: secrets[name]),
    )

    with pytest.raises(RuntimeError, match="approved Neon branch"):
        async with functions.get_blob_client():
            pass


async def test_production_blob_client_rejects_unapproved_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production writes fail closed when the configured branch changes."""
    secrets = {
        PrefectSecret.NEON_OBJECT_STORAGE_PROD_ENDPOINT: SecretStr("https://unapproved.storage.example"),
        PrefectSecret.NEON_OBJECT_STORAGE_PROD_ACCESS_KEY_ID: SecretStr("newman-access-key"),
        PrefectSecret.NEON_OBJECT_STORAGE_PROD_SECRET_ACCESS_KEY: SecretStr("newman-secret-key"),
    }
    monkeypatch.setattr(settings, "environment", EnvironmentMode.PROD)
    monkeypatch.setattr(
        functions,
        "get_secret",
        AsyncMock(side_effect=lambda *, name: secrets[name]),
    )

    with pytest.raises(RuntimeError, match="approved Neon branch"):
        async with functions.get_blob_client():
            pass


async def test_blob_client_requires_https_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Storage credentials are never sent to a plaintext endpoint."""
    secrets = {
        PrefectSecret.NEON_OBJECT_STORAGE_DEV_ENDPOINT: SecretStr("http://local.storage.example"),
        PrefectSecret.NEON_OBJECT_STORAGE_DEV_ACCESS_KEY_ID: SecretStr("newman-access-key"),
        PrefectSecret.NEON_OBJECT_STORAGE_DEV_SECRET_ACCESS_KEY: SecretStr("newman-secret-key"),
    }
    monkeypatch.setattr(
        functions,
        "get_secret",
        AsyncMock(side_effect=lambda *, name: secrets[name]),
    )

    with pytest.raises(RuntimeError, match="valid HTTPS URL"):
        async with functions.get_blob_client():
            pass


async def test_blob_client_requires_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing branch credentials fail before an object-storage request."""
    monkeypatch.setattr(
        functions,
        "get_secret",
        AsyncMock(side_effect=RuntimeError("missing storage secret")),
    )
    with pytest.raises(RuntimeError, match="missing storage secret"):
        await create_blobs(
            blobs=[
                BlobUpload(
                    bucket="newman-labs",
                    key="documents/newman.txt",
                    content=b"newman",
                    content_type="text/plain",
                )
            ]
        )
