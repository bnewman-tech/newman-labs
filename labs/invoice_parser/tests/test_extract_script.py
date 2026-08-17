"""Live invoice extraction script tests."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from pydantic import SecretStr

from labs.invoice_parser.schemas import InvoiceExtraction
from labs.invoice_parser.scripts import extract
from libs.core.dependencies import EnvironmentMode
from libs.document_intelligence.schemas import DocumentUpload


def test_main_processes_the_configured_invoices(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The live script processes each PDF through one managed runtime."""
    document_ids = [uuid4(), uuid4()]
    invoice_files = (
        tmp_path / "newman-first.pdf",
        tmp_path / "newman-second.pdf",
    )
    for ordinal, file_path in enumerate(invoice_files, start=1):
        file_path.write_bytes(f"%PDF-1.7\nnewman {ordinal}".encode())

    def extract_document(*, source: DocumentUpload) -> InvoiceExtraction:
        ordinal = 1 if source.original_filename == invoice_files[0].name else 2
        assert source.media_type == "application/pdf"
        assert source.content == f"%PDF-1.7\nnewman {ordinal}".encode()
        return InvoiceExtraction(
            document_id=document_ids[ordinal - 1],
            document_url=f"https://storage.example/newman-{ordinal}.pdf?signature=temporary",
            document_markdown=f"# Invoice INV-2026-081{ordinal}",
            invoice={
                "invoice_number": f"INV-2026-081{ordinal}",
                "issue_date": "2026-08-16",
                "currency": "USD",
                "seller": {"name": "newman services"},
                "total": "100.00",
            },
            all_agent_messages=[],
        )

    monkeypatch.setattr(extract, "INVOICE_FILES", invoice_files)
    monkeypatch.setattr(extract, "extract_invoice_document", AsyncMock(side_effect=extract_document))
    configure_logfire = AsyncMock()
    monkeypatch.setattr(extract, "configure_logfire", configure_logfire)
    database_url = SecretStr("postgresql://newman_labs_web:newman@localhost:5432/newman_labs_test")
    get_managed_database_url = AsyncMock(return_value=database_url)
    monkeypatch.setattr(extract, "get_managed_database_url", get_managed_database_url)
    get_api_db_engine = Mock()
    monkeypatch.setattr(extract, "get_api_db_engine", get_api_db_engine)
    dispose_api_engine = AsyncMock()
    monkeypatch.setattr(extract, "dispose_api_engine", dispose_api_engine)
    log_result = Mock()
    monkeypatch.setattr(extract.logger, "info", log_result)

    asyncio.run(extract.main())

    configure_logfire.assert_awaited_once_with()
    get_managed_database_url.assert_awaited_once_with(
        environment=extract.settings.environment,
        role=extract.DatabaseRole.WEB,
    )
    get_api_db_engine.assert_called_once_with(database_url=database_url)
    dispose_api_engine.assert_awaited_once_with()
    assert log_result.call_count == 2
    logged_results = [InvoiceExtraction.model_validate_json(log_call.args[0]) for log_call in log_result.call_args_list]
    assert [result.document_id for result in logged_results] == document_ids


def test_managed_flow_processes_a_staged_invoice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prefect compute reads the private source and publishes a transient result."""
    previous_environment = extract.settings.environment
    document_id = uuid4()
    expected = InvoiceExtraction(
        document_id=document_id,
        document_url="https://storage.example/newman.pdf?signature=temporary",
        document_markdown="# Invoice INV-2026-0816",
        invoice={
            "invoice_number": "INV-2026-0816",
            "issue_date": "2026-08-16",
            "currency": "USD",
            "seller": {"name": "newman services"},
            "total": "100.00",
        },
        all_agent_messages=[],
    )
    configure_logfire = AsyncMock()
    database_url = SecretStr("postgresql://newman_labs_web:newman@localhost:5432/newman_labs_test")
    read_blob = AsyncMock(return_value=SimpleNamespace(content=b"%PDF-1.7\n"))
    process = AsyncMock(return_value=expected)
    create_blobs = AsyncMock()
    delete_blob = AsyncMock()
    dispose_api_engine = AsyncMock()
    shutdown_security = Mock()
    monkeypatch.setattr(extract, "configure_logfire", configure_logfire)
    monkeypatch.setattr(
        extract,
        "get_managed_database_url",
        AsyncMock(return_value=database_url),
    )
    monkeypatch.setattr(extract, "get_api_db_engine", Mock())
    monkeypatch.setattr(extract, "read_blob", read_blob)
    monkeypatch.setattr(extract, "extract_invoice_document", process)
    monkeypatch.setattr(extract, "create_blobs", create_blobs)
    monkeypatch.setattr(extract, "delete_blob", delete_blob)
    monkeypatch.setattr(extract, "dispose_api_engine", dispose_api_engine)
    monkeypatch.setattr(extract, "shutdown_document_security", shutdown_security)

    result = asyncio.run(
        extract.run_managed_invoice_extraction.fn(
            document_id=document_id,
            original_filename="newman-invoice.pdf",
            media_type="application/pdf",
            environment=EnvironmentMode.PROD,
        )
    )

    assert result is None
    read_blob.assert_awaited_once_with(
        bucket="newman-labs",
        key=f"document-processing/{document_id}/source.pdf",
    )
    assert process.await_args is not None
    source = process.await_args.kwargs["source"]
    assert source.document_id == document_id
    assert source.content == b"%PDF-1.7\n"
    assert create_blobs.await_args is not None
    result_blob = create_blobs.await_args.kwargs["blobs"][0]
    assert result_blob.key == f"document-processing/{document_id}/result.json"
    assert InvoiceExtraction.model_validate_json(result_blob.content) == expected
    delete_blob.assert_awaited_once_with(
        bucket="newman-labs",
        key=f"document-processing/{document_id}/source.pdf",
    )
    shutdown_security.assert_called_once_with()
    dispose_api_engine.assert_awaited_once_with()
    assert extract.settings.environment is previous_environment
