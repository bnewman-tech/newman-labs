"""Run live invoice extraction against the local sample PDFs."""

import asyncio
import sys
from pathlib import Path
from uuid import UUID, uuid4

import aiofiles
from prefect import flow

sys.path.append(str(Path.cwd()))

from labs.invoice_parser.functions import (
    extract_invoice_document,
    invoice_extraction_result_key,
    invoice_extraction_source_key,
)
from libs.blob_storage.functions import create_blobs, delete_blob, read_blob
from libs.blob_storage.schemas import BlobUpload
from libs.core.dependencies import EnvironmentMode, settings
from libs.core.logger import get_logger
from libs.database.functions import (
    DatabaseRole,
    dispose_api_engine,
    get_api_db_engine,
    get_managed_database_url,
)
from libs.document_intelligence.functions import DOCUMENT_STORAGE_BUCKET
from libs.document_intelligence.schemas import DocumentUpload
from libs.document_intelligence.security import shutdown_document_security
from libs.pydantic_ai_core.observability import configure_logfire

logger = get_logger(__name__)

INVOICE_FILES = (
    Path("labs/invoice_parser/data/invoice_01_clean_standard.pdf"),
    Path("labs/invoice_parser/data/invoice_02_missing_po.pdf"),
    Path("labs/invoice_parser/data/invoice_03_total_mismatch.pdf"),
    Path("labs/invoice_parser/data/invoice_04_noisy_service_ticket.pdf"),
)


@flow(
    name="invoice-extraction",
    flow_run_name="invoice-extraction-{document_id}",
    timeout_seconds=600,
)
async def run_managed_invoice_extraction(
    document_id: UUID,
    original_filename: str,
    media_type: str,
    environment: EnvironmentMode = settings.environment,
) -> None:
    """Run one staged invoice through the full managed extraction pipeline."""
    previous_environment = settings.environment
    settings.environment = environment
    try:
        await configure_logfire()
        database_url = await get_managed_database_url(
            environment=environment,
            role=DatabaseRole.WEB,
        )
        get_api_db_engine(database_url=database_url)
        source_key = invoice_extraction_source_key(document_id=document_id)
        try:
            staged = await read_blob(
                bucket=DOCUMENT_STORAGE_BUCKET,
                key=source_key,
            )
            result = await extract_invoice_document(
                source=DocumentUpload(
                    document_id=document_id,
                    original_filename=original_filename,
                    media_type=media_type,
                    content=staged.content,
                )
            )
            await create_blobs(
                blobs=[
                    BlobUpload(
                        bucket=DOCUMENT_STORAGE_BUCKET,
                        key=invoice_extraction_result_key(document_id=document_id),
                        content=result.model_dump_json().encode(),
                        content_type="application/json",
                    )
                ]
            )
        finally:
            await delete_blob(
                bucket=DOCUMENT_STORAGE_BUCKET,
                key=source_key,
            )
            await asyncio.to_thread(shutdown_document_security)
            await dispose_api_engine()
    finally:
        settings.environment = previous_environment


async def main() -> None:
    """Run each configured local invoice through the managed workflow."""
    await configure_logfire()
    database_url = await get_managed_database_url(
        environment=settings.environment,
        role=DatabaseRole.WEB,
    )
    get_api_db_engine(database_url=database_url)
    try:
        for file_path in INVOICE_FILES:
            async with aiofiles.open(file_path, mode="rb") as file:
                content = await file.read()

            result = await extract_invoice_document(
                source=DocumentUpload(
                    document_id=uuid4(),
                    original_filename=file_path.name,
                    media_type="application/pdf",
                    content=content,
                )
            )
            logger.info(result.model_dump_json(indent=2))
    finally:
        await dispose_api_engine()


if __name__ == "__main__":
    asyncio.run(main())
