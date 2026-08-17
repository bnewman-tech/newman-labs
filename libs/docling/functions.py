"""Local Docling PDF conversion."""

from __future__ import annotations

import asyncio
from functools import cache
from importlib.metadata import version
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

import aiofiles

from libs.core.logger import configure_ml_library_logging
from libs.docling.schemas import DoclingConversion
from libs.docling.settings import (
    PDF_CONVERSION_TIMEOUT_SECONDS,
    PDF_MAX_FILE_SIZE_BYTES,
    PDF_MAX_PAGES,
)

if TYPE_CHECKING:
    from docling.document_converter import DocumentConverter

_conversion_slots = asyncio.Semaphore(1)
_conversion_tasks: set[asyncio.Task[DoclingConversion]] = set()


class DoclingConversionTimeoutError(TimeoutError):
    """Docling conversion did not finish within the caller's wait limit."""


@cache
def _get_pdf_converter() -> DocumentConverter:
    """Return the process-wide local PDF converter."""
    configure_ml_library_logging()
    from transformers.utils.logging import (  # ruff: ignore[import-outside-top-level] - Silence model-loading progress before Docling constructs its pipeline.
        disable_progress_bar,
    )

    disable_progress_bar()
    from docling.datamodel.base_models import (  # ruff: ignore[import-outside-top-level] - Keep the web process light until its first PDF conversion.
        InputFormat,
    )
    from docling.datamodel.object_detection_engine_options import (  # ruff: ignore[import-outside-top-level] - Keep the web process light until its first PDF conversion.
        TransformersObjectDetectionEngineOptions,
    )
    from docling.datamodel.pipeline_options import (  # ruff: ignore[import-outside-top-level] - Keep the web process light until its first PDF conversion.
        LayoutObjectDetectionOptions,
        PdfPipelineOptions,
        RapidOcrOptions,
        TableFormerMode,
        TableStructureOptions,
    )
    from docling.document_converter import (  # ruff: ignore[import-outside-top-level] - Keep the web process light until its first PDF conversion.
        DocumentConverter,
        PdfFormatOption,
    )

    pipeline_options = PdfPipelineOptions(
        document_timeout=PDF_CONVERSION_TIMEOUT_SECONDS,
        enable_remote_services=False,
        do_ocr=True,
        ocr_options=RapidOcrOptions(
            backend="torch",
            lang=["english"],
            rapidocr_params={"Global.log_level": "error"},
        ),
        # Short-lived managed CPU workers should not pay TorchInductor's compile
        # cost or require a system C++ compiler before running the layout model.
        layout_options=LayoutObjectDetectionOptions(
            engine_options=TransformersObjectDetectionEngineOptions(
                compile_model=False,
            )
        ),
        do_table_structure=True,
        table_structure_options=TableStructureOptions(mode=TableFormerMode.ACCURATE),
    )
    return DocumentConverter(
        allowed_formats=[InputFormat.PDF],
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)},
    )


def _convert_pdf(
    *,
    content: bytes,
    filename: str,
) -> DoclingConversion:
    """Run the synchronous Docling SDK inside the bounded worker thread."""
    from docling.datamodel.document import (  # ruff: ignore[import-outside-top-level] - Imported with the cached converter on first use.
        DocumentStream,
    )

    result = _get_pdf_converter().convert(
        source=DocumentStream(name=filename, stream=BytesIO(content)),
        max_num_pages=PDF_MAX_PAGES,
        max_file_size=PDF_MAX_FILE_SIZE_BYTES,
    )
    markdown = result.document.export_to_markdown().strip()
    if not markdown:
        raise ValueError("Docling produced no document text")
    return DoclingConversion(
        document=result.document,
        markdown=markdown,
        page_count=len(result.document.pages),
        version=version("docling"),
    )


async def convert_pdf(
    *,
    source: bytes | Path,
    filename: str | None = None,
) -> DoclingConversion:
    """Convert PDF bytes or a local PDF path with bounded local concurrency."""
    if isinstance(source, Path):
        filename = source.name
        async with aiofiles.open(source, "rb") as pdf_file:
            content = await pdf_file.read(PDF_MAX_FILE_SIZE_BYTES + 1)
    else:
        if filename is None:
            raise ValueError("filename is required when source contains PDF bytes")
        content = source

    if len(content) > PDF_MAX_FILE_SIZE_BYTES:
        raise ValueError("PDF exceeds the maximum file size")

    try:
        async with asyncio.timeout(PDF_CONVERSION_TIMEOUT_SECONDS):
            await _conversion_slots.acquire()
            task = asyncio.create_task(
                asyncio.to_thread(
                    _convert_pdf,
                    content=content,
                    filename=filename,
                )
            )
            _conversion_tasks.add(task)

            def conversion_finished(
                completed_task: asyncio.Task[DoclingConversion],
            ) -> None:
                _conversion_slots.release()
                _conversion_tasks.discard(completed_task)
                if not completed_task.cancelled():
                    completed_task.exception()

            task.add_done_callback(conversion_finished)
            return await asyncio.shield(task)
    except TimeoutError as exc:
        raise DoclingConversionTimeoutError("Docling conversion exceeded the configured timeout") from exc
