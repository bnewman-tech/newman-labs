"""Tests for the document-security trust boundary."""

import asyncio
import os
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import doc_firewall
import pytest
from pydantic import ValidationError

from libs.document_intelligence import security
from libs.document_intelligence.schemas import (
    ApprovedDocument,
    DocumentSecurityScan,
    DocumentUpload,
    SecurityVerdict,
)
from libs.document_intelligence.security import (
    DocumentRejectedError,
    DocumentSecurityScanError,
)

FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures"


@pytest.fixture
def document_upload() -> DocumentUpload:
    """Build one valid untrusted PDF upload."""
    return DocumentUpload(
        document_id=uuid4(),
        original_filename="newman-security.pdf",
        media_type="application/pdf",
        content=b"%PDF-1.7\nnewman security test",
    )


@pytest.mark.parametrize("verdict", [SecurityVerdict.ALLOW, SecurityVerdict.FLAG])
async def test_approve_document_returns_approved_contract(
    document_upload: DocumentUpload,
    verdict: SecurityVerdict,
) -> None:
    """Allow and review-only flag decisions create the trusted document type."""
    with (
        patch(
            "libs.document_intelligence.security._scan_document",
            return_value=DocumentSecurityScan(
                scanner_name="doc_firewall",
                scanner_version="newman-test-v1",
                verdict=verdict,
                risk_score=0.0 if verdict is SecurityVerdict.ALLOW else 0.48,
                findings=[] if verdict is SecurityVerdict.ALLOW else ["Review-only finding"],
            ),
        ),
        patch("libs.document_intelligence.security.logfire.info"),
    ):
        approved = await security.approve_document(source=document_upload)

    assert approved.security_scan == DocumentSecurityScan(
        scanner_name="doc_firewall",
        scanner_version="newman-test-v1",
        verdict=verdict,
        risk_score=0.0 if verdict is SecurityVerdict.ALLOW else 0.48,
        findings=[] if verdict is SecurityVerdict.ALLOW else ["Review-only finding"],
    )
    assert approved.model_dump(exclude={"security_scan"}) == (document_upload.model_dump())


async def test_approve_document_rejects_a_blocked_scan(
    document_upload: DocumentUpload,
) -> None:
    """A definitive unsafe verdict is a document rejection."""
    with (
        patch(
            "libs.document_intelligence.security._scan_document",
            return_value=DocumentSecurityScan(
                scanner_name="doc_firewall",
                scanner_version="newman-test-v1",
                verdict=SecurityVerdict.BLOCK,
            ),
        ),
        patch("libs.document_intelligence.security.logfire.info"),
        pytest.raises(DocumentRejectedError, match="rejected"),
    ):
        await security.approve_document(source=document_upload)


@pytest.mark.parametrize("verdict", [SecurityVerdict.ERROR, SecurityVerdict.TIMEOUT])
async def test_approve_document_reports_an_inconclusive_scan(
    document_upload: DocumentUpload,
    verdict: SecurityVerdict,
) -> None:
    """Scanner failures remain fail-closed without blaming the document."""
    with (
        patch(
            "libs.document_intelligence.security._scan_document",
            return_value=DocumentSecurityScan(
                scanner_name="doc_firewall",
                scanner_version="newman-test-v1",
                verdict=verdict,
            ),
        ),
        patch("libs.document_intelligence.security.logfire.info"),
        pytest.raises(DocumentSecurityScanError, match="could not complete"),
    ):
        await security.approve_document(source=document_upload)


async def test_cancellation_waits_for_the_running_security_scan(
    document_upload: DocumentUpload,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancellation cannot release scanner capacity before its thread exits."""
    scan_started = threading.Event()
    finish_scan = threading.Event()

    def scan_document(**_: object) -> DocumentSecurityScan:
        scan_started.set()
        finish_scan.wait(timeout=5)
        return DocumentSecurityScan(
            scanner_name="doc_firewall",
            scanner_version="newman-test-v1",
            verdict=SecurityVerdict.ALLOW,
        )

    monkeypatch.setattr(security, "_scan_document", scan_document)
    task = asyncio.create_task(security.approve_document(source=document_upload))
    assert await asyncio.to_thread(scan_started.wait, 5)

    task.cancel()
    await asyncio.sleep(0)

    assert not task.done()
    assert security._security_scan_slots.locked()

    finish_scan.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not security._security_scan_slots.locked()


@pytest.mark.parametrize(
    "verdict",
    [SecurityVerdict.BLOCK, SecurityVerdict.ERROR, SecurityVerdict.TIMEOUT],
)
def test_approved_document_rejects_non_approved_verdicts(
    document_upload: DocumentUpload,
    verdict: SecurityVerdict,
) -> None:
    """The trusted Pydantic contract rejects unsafe and inconclusive decisions."""
    with pytest.raises(ValidationError, match="allow or flag"):
        ApprovedDocument.model_validate({
            **document_upload.model_dump(),
            "security_scan": {
                "scanner_name": "doc_firewall",
                "scanner_version": "newman-test-v1",
                "verdict": verdict,
            },
        })


def test_security_scan_terminates_timed_out_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A wedged parser process is stopped before the timeout is reported."""
    parent_connection = MagicMock()
    parent_connection.poll.return_value = False
    child_connection = MagicMock()
    process = MagicMock()
    process.is_alive.return_value = False
    context = MagicMock()
    context.Pipe.return_value = (parent_connection, child_connection)
    context.Process.return_value = process
    monkeypatch.setattr(security, "_security_scan_connection", None)
    monkeypatch.setattr(security, "_security_scan_process", None)
    monkeypatch.setattr(
        security.multiprocessing,
        "get_context",
        MagicMock(return_value=context),
    )

    scan = security._scan_document(
        content=b"%PDF-1.7\nnewman timeout test",
        filename="newman-timeout.pdf",
    )

    assert scan.verdict is SecurityVerdict.TIMEOUT
    process.terminate.assert_called_once_with()
    process.join.assert_called_once_with(5)
    process.kill.assert_not_called()
    parent_connection.close.assert_called_once_with()
    child_connection.close.assert_called_once_with()
    assert security._security_scan_process is None
    assert security._security_scan_connection is None


def test_security_process_requires_vendored_yara(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The worker owns YARA and does not duplicate it inside DocFirewall."""
    configure_ml_logging = MagicMock()
    finding = SimpleNamespace(title="YARA Rule Match: newman")
    scanner = MagicMock()
    scanner.scan_bytes.return_value = SimpleNamespace(
        verdict=SimpleNamespace(value="ALLOW"),
        risk_score=0.0,
        findings=[finding],
    )

    def build_scanner(**_: object) -> MagicMock:
        assert os.environ[security.DOCLING_COMPILE_TORCH_MODELS_ENV] == "false"
        return scanner

    scanner_type = MagicMock(side_effect=build_scanner)
    yara_rules = MagicMock()
    yara_rules.match.return_value = []
    monkeypatch.setattr(doc_firewall, "Scanner", scanner_type)
    monkeypatch.setattr(security, "configure_ml_library_logging", configure_ml_logging)
    monkeypatch.setattr(security, "_YARA_RULES", yara_rules)
    monkeypatch.setenv(security.DOCLING_COMPILE_TORCH_MODELS_ENV, "true")
    connection = MagicMock()
    connection.recv.side_effect = [
        (b"%PDF-1.7\nnewman yara test", "newman-yara.pdf"),
        EOFError,
    ]

    security._scan_document_process(connection=connection)

    assert os.environ[security.DOCLING_COMPILE_TORCH_MODELS_ENV] == "true"
    config = scanner_type.call_args.kwargs["config"]
    configure_ml_logging.assert_called_once_with()
    assert config.profile == "balanced"
    assert config.enable_yara is False
    assert config.enable_builtin_yara_rules is False
    assert config.yara_rules_path is None
    assert config.enable_ocr_injection_scan is False
    assert config.enable_indirect_injection is True
    assert config.enable_result_cache is True
    assert config.required_capabilities == []
    assert config.on_timeout_verdict == "block"
    assert config.on_unscannable_verdict == "block"
    assert config.thresholds.deep_scan_trigger == pytest.approx(0.2)
    yara_rules.match.assert_called_once_with(
        data=b"%PDF-1.7\nnewman yara test",
        timeout=10,
    )
    scanner.scan_bytes.assert_called_once_with(
        b"%PDF-1.7\nnewman yara test",
        filename="newman-yara.pdf",
    )
    connection.send.assert_called_once_with(
        DocumentSecurityScan(
            scanner_name=security.DOCUMENT_SECURITY_SCANNER_NAME,
            scanner_version=security.DOCUMENT_SECURITY_SCANNER_VERSION,
            verdict=SecurityVerdict.ALLOW,
            risk_score=0.0,
            findings=["YARA Rule Match: newman"],
        )
    )
    connection.close.assert_called_once_with()


def test_security_process_blocks_yara_before_docfirewall(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A definitive YARA match skips the expensive document scanner."""
    yara_rules = MagicMock()
    yara_rules.match.return_value = [SimpleNamespace(rule="newman_test_rule")]
    monkeypatch.setattr(security, "_YARA_RULES", yara_rules)
    scanner_type = MagicMock()
    monkeypatch.setattr(doc_firewall, "Scanner", scanner_type)
    connection = MagicMock()
    connection.recv.side_effect = [
        (b"%PDF-1.7\nnewman malicious marker", "newman-malicious.pdf"),
        EOFError,
    ]

    security._scan_document_process(connection=connection)

    scanner_type.assert_not_called()
    connection.send.assert_called_once_with(
        DocumentSecurityScan(
            scanner_name=security.DOCUMENT_SECURITY_SCANNER_NAME,
            scanner_version=security.DOCUMENT_SECURITY_SCANNER_VERSION,
            verdict=SecurityVerdict.BLOCK,
            risk_score=1.0,
            findings=["YARA Rule Match: newman_test_rule"],
        )
    )


@pytest.mark.parametrize(
    ("scanner_verdict", "expected_verdict", "risk_score"),
    [
        ("FLAG", SecurityVerdict.FLAG, 0.48),
        ("BLOCK", SecurityVerdict.BLOCK, 1.0),
    ],
)
def test_security_process_preserves_docfirewall_verdict(
    monkeypatch: pytest.MonkeyPatch,
    scanner_verdict: str,
    expected_verdict: SecurityVerdict,
    risk_score: float,
) -> None:
    """DocFirewall review and definitive decisions retain their meaning."""
    finding = SimpleNamespace(title="PDF White-on-White Stealth Text")
    scanner = MagicMock()
    scanner.scan_bytes.return_value = SimpleNamespace(
        verdict=SimpleNamespace(value=scanner_verdict),
        risk_score=risk_score,
        findings=[finding],
    )
    monkeypatch.setattr(doc_firewall, "Scanner", MagicMock(return_value=scanner))
    yara_rules = MagicMock()
    yara_rules.match.return_value = []
    monkeypatch.setattr(security, "_YARA_RULES", yara_rules)
    connection = MagicMock()
    connection.recv.side_effect = [
        (b"%PDF-1.7\nnewman flagged invoice", "newman-flagged.pdf"),
        EOFError,
    ]

    security._scan_document_process(connection=connection)

    connection.send.assert_called_once_with(
        DocumentSecurityScan(
            scanner_name=security.DOCUMENT_SECURITY_SCANNER_NAME,
            scanner_version=security.DOCUMENT_SECURITY_SCANNER_VERSION,
            verdict=expected_verdict,
            risk_score=risk_score,
            findings=["PDF White-on-White Stealth Text"],
        )
    )


@pytest.mark.parametrize(
    ("filename", "expected_rule"),
    [
        ("active-content.pdf", "PDF_OpenAction_Launch"),
        ("prompt-injection.pdf", "LLM_Prompt_Injection_System_Override"),
    ],
)
def test_vendored_yara_detects_harmless_pdf_fixture(
    filename: str,
    expected_rule: str,
) -> None:
    """Synthetic hostile markers exercise the real pinned YARA rules."""
    matches = security.yara.compile(filepath=str(security.DOCUMENT_SECURITY_YARA_RULES)).match(
        data=(FIXTURE_DIRECTORY / filename).read_bytes()
    )

    assert expected_rule in {match.rule for match in matches}


def test_vendored_yara_allows_benign_pdf_fixture() -> None:
    """The YARA gate does not flag the inert allow control."""
    matches = security.yara.compile(filepath=str(security.DOCUMENT_SECURITY_YARA_RULES)).match(
        data=(FIXTURE_DIRECTORY / "benign.pdf").read_bytes()
    )

    assert matches == []


async def test_preflight_document_allows_valid_pdf_before_staging(
    document_upload: DocumentUpload,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Private staging receives only validated bytes without loading DocFirewall."""
    yara_rules = MagicMock()
    match_threads: list[int] = []

    def match_document(**_: object) -> list[object]:
        match_threads.append(threading.get_ident())
        return []

    yara_rules.match.side_effect = match_document
    monkeypatch.setattr(security, "_YARA_RULES", yara_rules)

    request_thread = threading.get_ident()
    await security.preflight_document(source=document_upload)
    await security.preflight_document(source=document_upload)

    assert yara_rules.match.call_count == 2
    assert all(match_thread != request_thread for match_thread in match_threads)
    yara_rules.match.assert_called_with(data=document_upload.content, timeout=10)


async def test_preflight_document_bounds_concurrent_yara_scans(
    document_upload: DocumentUpload,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Public uploads cannot fan out unbounded work in the shared executor."""
    first_scan_started = threading.Event()
    finish_scans = threading.Event()
    state_lock = threading.Lock()
    active_scans = 0
    started_scans = 0
    maximum_active_scans = 0

    def match_document(**_: object) -> list[object]:
        nonlocal active_scans, maximum_active_scans, started_scans
        with state_lock:
            active_scans += 1
            started_scans += 1
            maximum_active_scans = max(maximum_active_scans, active_scans)
            first_scan_started.set()
        finish_scans.wait(timeout=5)
        with state_lock:
            active_scans -= 1
        return []

    yara_rules = MagicMock()
    yara_rules.match.side_effect = match_document
    monkeypatch.setattr(security, "_YARA_RULES", yara_rules)
    monkeypatch.setattr(security, "_security_preflight_slots", asyncio.Semaphore(1))

    tasks = [
        asyncio.create_task(security.preflight_document(source=document_upload)),
        asyncio.create_task(security.preflight_document(source=document_upload)),
    ]
    assert await asyncio.to_thread(first_scan_started.wait, 5)
    await asyncio.sleep(0.05)

    with state_lock:
        assert started_scans == 1
        assert maximum_active_scans == 1

    finish_scans.set()
    await asyncio.gather(*tasks)
    assert maximum_active_scans == 1


async def test_preflight_cancellation_waits_for_the_yara_thread(
    document_upload: DocumentUpload,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancellation cannot release preflight capacity while YARA still runs."""
    scan_started = threading.Event()
    finish_scan = threading.Event()

    def match_document(**_: object) -> list[object]:
        scan_started.set()
        finish_scan.wait(timeout=5)
        return []

    yara_rules = MagicMock()
    yara_rules.match.side_effect = match_document
    preflight_slots = asyncio.Semaphore(1)
    monkeypatch.setattr(security, "_YARA_RULES", yara_rules)
    monkeypatch.setattr(security, "_security_preflight_slots", preflight_slots)

    task = asyncio.create_task(security.preflight_document(source=document_upload))
    assert await asyncio.to_thread(scan_started.wait, 5)

    task.cancel()
    await asyncio.sleep(0)

    assert not task.done()
    assert preflight_slots.locked()

    finish_scan.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not preflight_slots.locked()


async def test_preflight_document_blocks_yara_before_staging(
    document_upload: DocumentUpload,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Known malicious bytes never reach private object storage."""
    yara_rules = MagicMock()
    yara_rules.match.return_value = [SimpleNamespace(rule="newman_test_rule")]
    monkeypatch.setattr(security, "_YARA_RULES", yara_rules)

    with pytest.raises(DocumentRejectedError, match="security scan rejected"):
        await security.preflight_document(source=document_upload)
