"""Tests for the local Docling conversion boundary."""

import asyncio
import threading
from contextlib import suppress
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from docling.datamodel.base_models import InputFormat
from docling.datamodel.object_detection_engine_options import (
    TransformersObjectDetectionEngineOptions,
)
from docling.datamodel.pipeline_options import (
    LayoutObjectDetectionOptions,
    PdfPipelineOptions,
    RapidOcrOptions,
)
from docling_core.types.doc import DocItemLabel, DoclingDocument, Size

from libs.docling.functions import (
    _get_pdf_converter,
    convert_pdf,
)
from libs.docling.schemas import DoclingConversion
from libs.docling.settings import (
    PDF_CONVERSION_TIMEOUT_SECONDS,
    PDF_MAX_FILE_SIZE_BYTES,
    PDF_MAX_PAGES,
)


def test_docling_runtime_uses_headless_opencv() -> None:
    """The server runtime must not depend on desktop OpenCV system libraries."""
    assert version("opencv-python-headless")
    with pytest.raises(PackageNotFoundError):
        version("opencv-python")


def test_pdf_converter_uses_local_text_and_table_pipeline() -> None:
    """Conversion keeps text and table extraction local without unused models."""
    converter = _get_pdf_converter()
    pipeline_options = converter.format_to_options[InputFormat.PDF].pipeline_options

    assert isinstance(pipeline_options, PdfPipelineOptions)
    assert converter.allowed_formats == [InputFormat.PDF]
    assert pipeline_options.document_timeout == PDF_CONVERSION_TIMEOUT_SECONDS
    assert pipeline_options.enable_remote_services is False
    assert pipeline_options.do_ocr is True
    assert isinstance(pipeline_options.ocr_options, RapidOcrOptions)
    assert pipeline_options.ocr_options.backend == "torch"
    assert pipeline_options.ocr_options.lang == ["english"]
    assert pipeline_options.ocr_options.rapidocr_params == {"Global.log_level": "error"}
    assert pipeline_options.do_table_structure is True
    assert isinstance(pipeline_options.layout_options, LayoutObjectDetectionOptions)
    assert isinstance(
        pipeline_options.layout_options.engine_options,
        TransformersObjectDetectionEngineOptions,
    )
    assert pipeline_options.layout_options.engine_options.compile_model is False
    assert pipeline_options.do_code_enrichment is False
    assert pipeline_options.do_formula_enrichment is False
    assert pipeline_options.generate_picture_images is False
    assert pipeline_options.do_picture_classification is False
    assert pipeline_options.do_picture_description is False


async def test_convert_pdf_returns_native_docling_document() -> None:
    """Consumers receive Docling's real document model and normalized metadata."""
    document = DoclingDocument(name="newman-sample")
    document.add_page(page_no=1, size=Size(width=612, height=792))
    document.add_text(label=DocItemLabel.TEXT, text="Newman sample")
    converter = MagicMock()
    worker_thread: threading.Thread | None = None

    def convert_in_worker(**_: object) -> object:
        nonlocal worker_thread
        worker_thread = threading.current_thread()
        return MagicMock(document=document)

    converter.convert.side_effect = convert_in_worker

    with (
        patch("libs.docling.functions._get_pdf_converter", return_value=converter),
        patch("libs.docling.functions.version", return_value="2.119.0"),
    ):
        result = await convert_pdf(
            source=b"%PDF-1.7\n",
            filename="newman-sample.pdf",
        )

    convert_call = converter.convert.call_args.kwargs
    assert convert_call["max_num_pages"] == PDF_MAX_PAGES
    assert convert_call["max_file_size"] == PDF_MAX_FILE_SIZE_BYTES
    assert result.document is document
    assert result.markdown == "Newman sample"
    assert result.page_count == 1
    assert result.version == "2.119.0"
    assert worker_thread is not threading.current_thread()


async def test_convert_pdf_rejects_empty_markdown() -> None:
    """A structurally empty conversion cannot enter document intelligence."""
    converter = MagicMock()
    converter.convert.return_value.document = DoclingDocument(name="newman-empty")

    with (
        patch("libs.docling.functions._get_pdf_converter", return_value=converter),
        pytest.raises(ValueError, match="no document text"),
    ):
        await convert_pdf(
            source=b"%PDF-1.7\n",
            filename="newman-empty.pdf",
        )


async def test_convert_pdf_reads_path_asynchronously(tmp_path: Path) -> None:
    """A local path supplies both the PDF bytes and source filename."""
    pdf_path = tmp_path / "newman-path.pdf"
    pdf_path.write_bytes(b"%PDF-1.7\n")
    converted = DoclingConversion(
        document=DoclingDocument(name="newman-path"),
        markdown="Newman path test",
        page_count=1,
        version="2.119.0",
    )

    with patch("libs.docling.functions._convert_pdf", return_value=converted) as worker:
        result = await convert_pdf(source=pdf_path)

    assert result is converted
    assert worker.call_args.kwargs == {
        "content": b"%PDF-1.7\n",
        "filename": "newman-path.pdf",
    }


async def test_convert_pdf_requires_filename_for_bytes() -> None:
    """Raw bytes cannot silently lose their source filename."""
    with pytest.raises(ValueError, match="filename is required"):
        await convert_pdf(source=b"%PDF-1.7\n")


async def test_cancellation_keeps_conversion_slot_until_worker_exits() -> None:
    """Cancellation cannot release Docling concurrency while its thread runs."""
    worker_started = threading.Event()
    release_worker = threading.Event()
    calls = 0
    converted = DoclingConversion(
        document=DoclingDocument(name="newman-cancellation"),
        markdown="Newman cancellation test",
        page_count=1,
        version="2.119.0",
    )

    def blocking_conversion(**_: object) -> DoclingConversion:
        nonlocal calls
        calls += 1
        worker_started.set()
        release_worker.wait(timeout=2)
        return converted

    with patch("libs.docling.functions._convert_pdf", side_effect=blocking_conversion):
        first = asyncio.create_task(
            convert_pdf(
                source=b"%PDF-1.7\n",
                filename="newman-first.pdf",
            )
        )
        assert await asyncio.to_thread(worker_started.wait, 1)
        first.cancel()
        with suppress(asyncio.CancelledError):
            await first

        second = asyncio.create_task(
            convert_pdf(
                source=b"%PDF-1.7\n",
                filename="newman-second.pdf",
            )
        )
        await asyncio.sleep(0.05)
        assert calls == 1
        assert not second.done()

        release_worker.set()
        assert await second == converted
        assert calls == 2
