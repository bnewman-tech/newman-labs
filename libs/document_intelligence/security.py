"""Fail-closed document scanning before parsing or persistence."""

from __future__ import annotations

import asyncio
import atexit
import multiprocessing
import os
import signal
import sys
import threading
from importlib import import_module
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING, cast

import logfire

from libs.core.logger import configure_ml_library_logging
from libs.docling.settings import PDF_MAX_FILE_SIZE_BYTES, PDF_MAX_PAGES
from libs.document_intelligence.schemas import (
    ApprovedDocument,
    DocumentSecurityScan,
    DocumentUpload,
    SecurityVerdict,
)

if TYPE_CHECKING:
    from multiprocessing.connection import Connection
    from multiprocessing.process import BaseProcess

    from doc_firewall import Scanner

DOCUMENT_SECURITY_SCAN_TIMEOUT_SECONDS = 120
DOCUMENT_SECURITY_SCAN_SLOTS = 1
DOCUMENT_SECURITY_PREFLIGHT_SLOTS = 2
DOCUMENT_SECURITY_SCANNER_NAME = "doc_firewall"
DOCUMENT_SECURITY_SCANNER_VERSION = version("doc-firewall")
DOCUMENT_SECURITY_YARA_RULES = Path(__file__).parent / "vendor" / "doc_firewall" / "document_malware.yar"
DOCLING_COMPILE_TORCH_MODELS_ENV = "DOCLING_INFERENCE_COMPILE_TORCH_MODELS"
yara = import_module("yara")
_YARA_RULES = yara.compile(filepath=str(DOCUMENT_SECURITY_YARA_RULES))

_security_preflight_slots = asyncio.Semaphore(DOCUMENT_SECURITY_PREFLIGHT_SLOTS)
_security_scan_slots = asyncio.Semaphore(DOCUMENT_SECURITY_SCAN_SLOTS)
_security_scan_lock = threading.Lock()
_security_scan_connection: Connection | None = None
_security_scan_process: BaseProcess | None = None


class DocumentRejectedError(ValueError):
    """The upload did not satisfy the document-intake contract."""


class DocumentSecurityScanError(RuntimeError):
    """The document scanner could not produce a conclusive verdict."""


def validate_document(*, source: DocumentUpload) -> None:
    """Reject malformed PDF input before starting the scanner process."""
    if source.media_type != "application/pdf":
        raise DocumentRejectedError("Only application/pdf documents are supported")
    if not source.original_filename.lower().endswith(".pdf"):
        raise DocumentRejectedError("The filename must use the .pdf extension")
    if not source.content:
        raise DocumentRejectedError("The document is empty")
    if len(source.content) > PDF_MAX_FILE_SIZE_BYTES:
        raise DocumentRejectedError("The document exceeds the configured size limit")
    if not source.content.startswith(b"%PDF-"):
        raise DocumentRejectedError("The document signature is not PDF")


async def preflight_document(*, source: DocumentUpload) -> None:
    """Validate and reject known malicious bytes before private staging."""
    validate_document(source=source)
    async with _security_preflight_slots:
        task = asyncio.create_task(asyncio.to_thread(_YARA_RULES.match, data=source.content, timeout=10))
        try:
            matches = await asyncio.shield(task)
        except asyncio.CancelledError:
            try:
                await task
            finally:
                raise
    if matches:
        raise DocumentRejectedError("The document security scan rejected the upload")


def _scan_document(
    *,
    content: bytes,
    filename: str,
) -> DocumentSecurityScan:
    """Scan in one reusable process and replace that process after a timeout."""
    global _security_scan_connection, _security_scan_process  # ruff: ignore[global-statement]
    with _security_scan_lock:
        if _security_scan_process is None or not _security_scan_process.is_alive():
            if _security_scan_process is not None:
                _security_scan_process.join()
            if _security_scan_connection is not None:
                _security_scan_connection.close()
            context = multiprocessing.get_context("spawn")
            _security_scan_connection, child_connection = context.Pipe()
            _security_scan_process = context.Process(
                target=_scan_document_process,
                kwargs={"connection": child_connection},
            )
            _security_scan_process.start()
            child_connection.close()

        connection = cast("Connection", _security_scan_connection)
        process = _security_scan_process
        try:  # ruff: ignore[too-many-statements-in-try-clause]
            connection.send((content, filename))
            if connection.poll(timeout=DOCUMENT_SECURITY_SCAN_TIMEOUT_SECONDS):
                return DocumentSecurityScan.model_validate(connection.recv())

            process.terminate()
            process.join(5)
            if process.is_alive():
                process.kill()
                process.join()
            connection.close()
            _security_scan_connection = None
            _security_scan_process = None
            return DocumentSecurityScan(
                scanner_name=DOCUMENT_SECURITY_SCANNER_NAME,
                scanner_version=DOCUMENT_SECURITY_SCANNER_VERSION,
                verdict=SecurityVerdict.TIMEOUT,
            )
        except Exception:  # ruff: ignore[blind-except] - infrastructure fails closed.
            if process.is_alive():
                process.kill()
            process.join()
            connection.close()
            _security_scan_connection = None
            _security_scan_process = None
            return DocumentSecurityScan(
                scanner_name=DOCUMENT_SECURITY_SCANNER_NAME,
                scanner_version=DOCUMENT_SECURITY_SCANNER_VERSION,
                verdict=SecurityVerdict.ERROR,
            )


def _scan_document_process(*, connection: Connection) -> None:
    """Scan every received document with one child-process Scanner."""
    previous_compile_setting = os.environ.get(DOCLING_COMPILE_TORCH_MODELS_ENV)
    os.environ[DOCLING_COMPILE_TORCH_MODELS_ENV] = "false"
    if multiprocessing.parent_process() is not None:
        null_output = os.open(os.devnull, os.O_WRONLY)
        try:
            os.dup2(null_output, sys.stdout.fileno())
            os.dup2(null_output, sys.stderr.fileno())
        finally:
            os.close(null_output)
    configure_ml_library_logging()
    previous_interrupt_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
    scanner: Scanner | None = None
    try:  # ruff: ignore[too-many-statements-in-try-clause]
        while True:
            content, filename = connection.recv()
            try:  # ruff: ignore[too-many-statements-in-try-clause]
                yara_matches = _YARA_RULES.match(data=content, timeout=10)
                if yara_matches:
                    connection.send(
                        DocumentSecurityScan(
                            scanner_name=DOCUMENT_SECURITY_SCANNER_NAME,
                            scanner_version=DOCUMENT_SECURITY_SCANNER_VERSION,
                            verdict=SecurityVerdict.BLOCK,
                            risk_score=1.0,
                            findings=sorted({f"YARA Rule Match: {match.rule}" for match in yara_matches}),
                        )
                    )
                    continue
                if scanner is None:
                    from doc_firewall import (  # ruff: ignore[import-outside-top-level]
                        Limits,
                        ScanConfig,
                        Scanner,
                    )

                    config = ScanConfig(
                        profile="balanced",
                        enable_pdf=True,
                        enable_result_cache=True,
                        on_timeout_verdict="block",
                        on_unscannable_verdict="block",
                        limits=Limits(
                            max_mb=PDF_MAX_FILE_SIZE_BYTES // (1024 * 1024),
                            max_pages=PDF_MAX_PAGES,
                            fast_scan_timeout_ms=90_000,
                            parse_timeout_ms=90_000,
                            format_checks_timeout_ms=90_000,
                            detectors_timeout_ms=90_000,
                            docling_subprocess_timeout_s=90,
                        ),
                    )
                    # DocFirewall 0.5.1 cannot format yara-python 4.5 binary
                    # matches. The validated raw-byte gate above owns YARA.
                    config.enable_yara = False
                    config.enable_builtin_yara_rules = False
                    scanner = Scanner(config=config)
                report = scanner.scan_bytes(content, filename=filename)
                connection.send(
                    DocumentSecurityScan(
                        scanner_name=DOCUMENT_SECURITY_SCANNER_NAME,
                        scanner_version=DOCUMENT_SECURITY_SCANNER_VERSION,
                        verdict=SecurityVerdict(report.verdict.value.lower()),
                        risk_score=report.risk_score,
                        findings=sorted({finding.title for finding in report.findings}),
                    )
                )
            except Exception:  # ruff: ignore[blind-except] - scan fails closed.
                connection.send(
                    DocumentSecurityScan(
                        scanner_name=DOCUMENT_SECURITY_SCANNER_NAME,
                        scanner_version=DOCUMENT_SECURITY_SCANNER_VERSION,
                        verdict=SecurityVerdict.ERROR,
                    )
                )
    except EOFError:
        pass
    finally:
        signal.signal(signal.SIGINT, previous_interrupt_handler)
        connection.close()
        if previous_compile_setting is None:
            os.environ.pop(DOCLING_COMPILE_TORCH_MODELS_ENV, None)
        else:
            os.environ[DOCLING_COMPILE_TORCH_MODELS_ENV] = previous_compile_setting


def shutdown_document_security() -> None:
    """Terminate the reusable scanner process during application shutdown."""
    global _security_scan_connection, _security_scan_process  # ruff: ignore[global-statement]
    with _security_scan_lock:
        if _security_scan_process is not None:
            if _security_scan_process.is_alive():
                _security_scan_process.terminate()
            _security_scan_process.join()
            _security_scan_process = None
        if _security_scan_connection is not None:
            _security_scan_connection.close()
            _security_scan_connection = None


async def approve_document(*, source: DocumentUpload) -> ApprovedDocument:
    """Validate and scan one PDF before it reaches Docling or storage."""
    validate_document(source=source)
    async with _security_scan_slots:
        task = asyncio.create_task(
            asyncio.to_thread(
                _scan_document,
                content=source.content,
                filename=source.original_filename,
            )
        )
        try:
            scan = await asyncio.shield(task)
        except asyncio.CancelledError:
            try:
                await task
            finally:
                raise
    logfire.info(
        "Document security scan completed",
        verdict=scan.verdict,
        risk_score=scan.risk_score,
        findings=scan.findings,
    )
    if scan.verdict is SecurityVerdict.BLOCK:
        raise DocumentRejectedError("The document security scan rejected the upload")
    if scan.verdict in {SecurityVerdict.ERROR, SecurityVerdict.TIMEOUT}:
        raise DocumentSecurityScanError("The document security scan could not complete")
    return ApprovedDocument(**source.model_dump(), security_scan=scan)


atexit.register(shutdown_document_security)
