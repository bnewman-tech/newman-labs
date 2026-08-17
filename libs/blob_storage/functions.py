"""CRUD operations for private S3-compatible object storage."""

import asyncio
import hashlib
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from datetime import datetime
from typing import TYPE_CHECKING, cast
from urllib.parse import urlsplit

from aiobotocore.config import AioConfig
from aiobotocore.session import get_session

from libs.blob_storage.schemas import BlobContents, BlobUpload, StoredBlob
from libs.core.dependencies import EnvironmentMode, settings
from libs.prefect_utils.secrets import PrefectSecret, get_secret

if TYPE_CHECKING:
    from types_aiobotocore_s3.client import S3Client

AWS_REGION = "us-east-2"
DOWNLOAD_URL_TTL_SECONDS = 300
DEVELOPMENT_STORAGE_HOST = "br-soft-recipe-aj0awywr.storage.c-3.us-east-2.aws.neon.tech"
PRODUCTION_STORAGE_HOST = "br-morning-block-aj0edhtv.storage.c-3.us-east-2.aws.neon.tech"


@asynccontextmanager
async def get_blob_client() -> AsyncGenerator["S3Client"]:
    """Yield a configured client for the active private storage branch."""
    if settings.environment is EnvironmentMode.PROD:
        endpoint_name = PrefectSecret.NEON_OBJECT_STORAGE_PROD_ENDPOINT
        access_key_name = PrefectSecret.NEON_OBJECT_STORAGE_PROD_ACCESS_KEY_ID
        secret_key_name = PrefectSecret.NEON_OBJECT_STORAGE_PROD_SECRET_ACCESS_KEY
        expected_host = PRODUCTION_STORAGE_HOST
    else:
        endpoint_name = PrefectSecret.NEON_OBJECT_STORAGE_DEV_ENDPOINT
        access_key_name = PrefectSecret.NEON_OBJECT_STORAGE_DEV_ACCESS_KEY_ID
        secret_key_name = PrefectSecret.NEON_OBJECT_STORAGE_DEV_SECRET_ACCESS_KEY
        expected_host = DEVELOPMENT_STORAGE_HOST

    endpoint, access_key, secret_key = await asyncio.gather(
        get_secret(name=endpoint_name),
        get_secret(name=access_key_name),
        get_secret(name=secret_key_name),
    )
    endpoint_url = endpoint.get_secret_value()
    parsed_endpoint = urlsplit(endpoint_url)
    if parsed_endpoint.scheme != "https" or parsed_endpoint.hostname is None:
        raise RuntimeError("Object storage endpoint must be a valid HTTPS URL")
    if parsed_endpoint.hostname != expected_host:
        raise RuntimeError(
            f"{settings.environment.value.upper()} object storage does not target the approved Neon branch"
        )

    async with get_session().create_client(
        "s3",
        region_name=AWS_REGION,
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key.get_secret_value(),
        aws_secret_access_key=secret_key.get_secret_value(),
        config=AioConfig(
            retries={"max_attempts": 5, "mode": "standard"},
            s3={"addressing_style": "path"},
        ),
    ) as untyped_client:
        yield cast("S3Client", untyped_client)


async def create_blobs(*, blobs: Sequence[BlobUpload]) -> list[StoredBlob]:
    """Create objects with one client and remove partial writes on failure."""
    if not blobs:
        return []

    stored_blobs: list[StoredBlob] = []
    async with get_blob_client() as client:
        try:
            for blob in blobs:
                checksum = hashlib.sha256(blob.content).hexdigest()
                response = await client.put_object(
                    Bucket=blob.bucket,
                    Key=blob.key,
                    Body=blob.content,
                    ContentType=blob.content_type,
                    Metadata={"sha256": checksum},
                    IfNoneMatch="*",
                )
                stored_blobs.append(
                    StoredBlob(
                        bucket=blob.bucket,
                        key=blob.key,
                        content_type=blob.content_type,
                        content_sha256=checksum,
                        etag=response.get("ETag"),
                    )
                )
        except Exception:
            for stored_blob in reversed(stored_blobs):
                await client.delete_object(
                    Bucket=stored_blob.bucket,
                    Key=stored_blob.key,
                )
            raise
    return stored_blobs


async def read_blob(
    *,
    bucket: str,
    key: str,
) -> BlobContents:
    """Read one private object and verify its stored SHA-256 metadata."""
    async with get_blob_client() as client:
        response = await client.get_object(Bucket=bucket, Key=key)
        body = response["Body"]
        try:
            content = await body.read()
        finally:
            body.close()

    checksum = hashlib.sha256(content).hexdigest()
    stored_checksum = response.get("Metadata", {}).get("sha256")
    if stored_checksum is not None and stored_checksum != checksum:
        raise ValueError("Stored blob checksum does not match its content")
    return BlobContents(
        bucket=bucket,
        key=key,
        content=content,
        content_type=response.get("ContentType", "application/octet-stream"),
        content_sha256=checksum,
        etag=response.get("ETag"),
    )


async def create_download_url(*, bucket: str, key: str) -> str:
    """Create a five-minute URL for one private object."""
    async with get_blob_client() as client:
        return await client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=DOWNLOAD_URL_TTL_SECONDS,
        )


async def update_blob(
    *,
    stored: StoredBlob,
    content: bytes,
) -> StoredBlob:
    """Replace an object only when the caller's ETag is still current."""
    if stored.etag is None:
        raise ValueError("Stored blob ETag is required for update")
    checksum = hashlib.sha256(content).hexdigest()
    async with get_blob_client() as client:
        response = await client.put_object(
            Bucket=stored.bucket,
            Key=stored.key,
            Body=content,
            ContentType=stored.content_type,
            Metadata={"sha256": checksum},
            IfMatch=stored.etag,
        )
    return StoredBlob(
        bucket=stored.bucket,
        key=stored.key,
        content_type=stored.content_type,
        content_sha256=checksum,
        etag=response.get("ETag"),
    )


async def delete_blob(
    *,
    bucket: str,
    key: str,
) -> None:
    """Delete one private object; deleting a missing key remains idempotent."""
    async with get_blob_client() as client:
        await client.delete_object(Bucket=bucket, Key=key)


async def delete_blobs_before(
    *,
    bucket: str,
    prefix: str,
    before: datetime,
) -> int:
    """Delete every object under a prefix last modified before a cutoff."""
    deleted = 0
    continuation_token: str | None = None
    async with get_blob_client() as client:
        while True:
            if continuation_token is None:
                response = await client.list_objects_v2(
                    Bucket=bucket,
                    Prefix=prefix,
                )
            else:
                response = await client.list_objects_v2(
                    Bucket=bucket,
                    Prefix=prefix,
                    ContinuationToken=continuation_token,
                )
            for item in response.get("Contents", []):
                key = item.get("Key")
                last_modified = item.get("LastModified")
                if key is None or last_modified is None or last_modified > before:
                    continue
                await client.delete_object(Bucket=bucket, Key=key)
                deleted += 1
            continuation_token = response.get("NextContinuationToken")
            if continuation_token is None:
                return deleted
