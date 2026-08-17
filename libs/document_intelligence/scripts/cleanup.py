"""Expired document-retention cleanup entrypoint."""

import asyncio
from datetime import UTC, datetime

from prefect import flow

from libs.blob_storage.functions import delete_blobs_before
from libs.core.dependencies import EnvironmentMode, settings
from libs.core.logger import get_logger
from libs.database.functions import (
    DatabaseRole,
    create_database_engine,
    get_managed_database_url,
)
from libs.document_intelligence.functions import (
    DOCUMENT_STORAGE_BUCKET,
    delete_expired_documents,
)
from libs.document_intelligence.settings import (
    DOCUMENT_STAGING_PREFIX,
    DOCUMENT_STAGING_RETENTION,
)

logger = get_logger(__name__)


@flow(
    name="document-intelligence-retention-cleanup",
    flow_run_name="document-retention-{environment}",
    timeout_seconds=900,
    retries=2,
    retry_delay_seconds=60,
)
async def run_document_retention_cleanup(
    environment: EnvironmentMode = settings.environment,
) -> int:
    """Delete one bounded batch of expired documents from storage and PostgreSQL."""
    previous_environment = settings.environment
    settings.environment = environment
    try:
        database_url = await get_managed_database_url(
            environment=environment,
            role=DatabaseRole.OWNER,
        )
        engine = create_database_engine(database_url=database_url)
        try:
            deleted_documents = await delete_expired_documents(engine=engine)
            deleted_staging_objects = await delete_blobs_before(
                bucket=DOCUMENT_STORAGE_BUCKET,
                prefix=f"{DOCUMENT_STAGING_PREFIX}/",
                before=datetime.now(UTC) - DOCUMENT_STAGING_RETENTION,
            )
        finally:
            await engine.dispose()
    finally:
        settings.environment = previous_environment
    logger.info(
        f"Document retention cleanup deleted {deleted_documents} documents and "
        f"{deleted_staging_objects} staging objects"
    )
    return deleted_documents


if __name__ == "__main__":
    asyncio.run(run_document_retention_cleanup())
