"""Invoice Parser page and extraction API tests."""

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import UUID

import httpx
import pytest

from apps.labs.main import app
from apps.labs.rate_limiting import INVOICE_SUBMISSION_RATE_LIMIT
from apps.labs.routes import invoice_parser
from apps.labs.security import (
    create_job_access_token,
    create_passcode_token,
)
from labs.invoice_parser.functions import InvoiceExtractionCapacityError, InvoiceExtractionJobFailedError
from labs.invoice_parser.schemas import (
    InvoiceExtraction,
    InvoiceExtractionJob,
    InvoiceLineItem,
    InvoiceParty,
    ParsedInvoice,
    SupplierMatch,
)
from libs.document_intelligence.security import DocumentRejectedError

DOCUMENT_ID = UUID("f909d5d9-a23c-44d3-b92d-e59aee4c8498")
FLOW_RUN_ID = UUID("08f78d8a-2418-4e65-991f-76b606770799")


@pytest.fixture(autouse=True)
def configure_invoice_extraction_access(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide the valid test passcode without storing a raw secret in app state."""
    monkeypatch.setattr(
        app.state,
        "invoice_parser_access_token",
        create_passcode_token(passcode="newman-test-passcode"),
    )


def job_access_token() -> str:
    """Return the valid polling capability for the fixed test job."""
    return create_job_access_token(
        invoice_access_token=app.state.invoice_parser_access_token,
        document_id=DOCUMENT_ID,
        flow_run_id=FLOW_RUN_ID,
    )


def extraction() -> InvoiceExtraction:
    """Return one complete extraction response."""
    return InvoiceExtraction(
        document_id=DOCUMENT_ID,
        document_url="https://storage.example/newman-invoice.pdf?signature=temporary",
        document_markdown="# Invoice INV-1042\n\nEngineering services: $9,500.00",
        invoice=ParsedInvoice(
            invoice_number="INV-1042",
            issue_date=date(2026, 8, 15),
            purchase_order_number="MR-4821",
            currency="USD",
            seller=InvoiceParty(name="Northstar Design Studio"),
            buyer=InvoiceParty(name="Meridian Research Group"),
            line_items=[
                InvoiceLineItem(
                    description="Engineering services",
                    quantity=Decimal(1),
                    unit="project",
                    unit_price=Decimal("9500.00"),
                    line_total=Decimal("9500.00"),
                )
            ],
            subtotal=Decimal("9500.00"),
            total=Decimal("9500.00"),
        ),
        supplier_match=SupplierMatch(
            supplier_id="SUP-1001",
            name="Northstar Design Studio LLC",
        ),
        all_agent_messages=[],
    )


async def test_invoice_parser_page_renders_the_small_extraction_workflow() -> None:
    """The public Lab exposes one document-to-agent workflow."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/invoice-parser/")
        script = await client.get("/static/js/invoice-parser.js")
        basic_demo = await client.get("/static/demos/invoice-basic.pdf")
        detailed_demo = await client.get("/static/demos/invoice-detailed.pdf")
        fixtures = [
            await client.get(f"/static/demos/{name}.json")
            for name in (
                "invoice-basic",
                "invoice-detailed",
                "invoice-supplier-match",
                "invoice-supplier-review",
            )
        ]
        supplier_pdfs = [
            await client.get(f"/static/demos/{name}.pdf")
            for name in ("invoice-supplier-match", "invoice-supplier-review")
        ]

    assert response.status_code == 200
    assert script.status_code == 200
    assert 'window.prompt("Enter the invoice processing access code.")' in script.text
    assert 'headers: { "X-Invoice-Job-Access": job.access_token }' in script.text
    assert 'searchParams.set("access_token"' not in script.text
    assert "all_agent_messages: payload.all_agent_messages" in script.text
    assert "Save one approved document" in response.text
    assert 'accept="application/pdf,.pdf"' in response.text
    assert "The transient extraction handoff is deleted after delivery" in " ".join(response.text.split())
    assert "Extraction starts automatically when you choose or drop a PDF" in response.text
    assert "data-invoice-submit" not in response.text
    assert "Prefect Managed" in response.text
    assert "Open the presentation" in response.text
    assert "data-invoice-pdf-frame" in response.text
    assert 'data-invoice-tab="pdf"' in response.text
    assert 'data-invoice-tab="data"' in response.text
    assert 'data-invoice-tab="ocr"' in response.text
    assert 'data-invoice-tab="json"' in response.text
    assert "US goods" in response.text
    assert "Supplier match" in response.text
    assert "Needs review" in response.text
    assert "data-invoice-supplier-status" in response.text
    assert "UK goods" not in response.text
    assert "browser history" not in response.text.lower()
    assert "set-cookie" not in response.headers
    assert basic_demo.status_code == 200
    assert basic_demo.content.startswith(b"%PDF")
    assert detailed_demo.status_code == 200
    assert detailed_demo.content.startswith(b"%PDF")
    for supplier_pdf in supplier_pdfs:
        assert supplier_pdf.status_code == 200
        assert supplier_pdf.content.startswith(b"%PDF")
    for fixture in fixtures:
        assert fixture.status_code == 200
        payload = fixture.json()
        assert payload["demo"] is True
        assert payload["document_markdown"].startswith("# Invoice")
        assert payload["invoice"]["currency"] == "USD"
        ParsedInvoice.model_validate(payload["invoice"])
        if payload["supplier_match"] is not None:
            SupplierMatch.model_validate(payload["supplier_match"])


async def test_invoice_parser_data_panel_uses_collapsible_field_groups() -> None:
    """The Data tab is a sticky identity line plus collapsible label/value groups."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/invoice-parser/")
        script = await client.get("/static/js/invoice-parser.js")

    assert response.status_code == 200
    assert script.status_code == 200
    assert "data-invoice-field-group" in response.text
    assert "data-invoice-group-found" in response.text
    assert 'class="invoice-identity"' in response.text
    assert "invoice-field-section" not in response.text
    assert "invoice-result-summary" not in response.text
    assert 'missingValueLabel = "-"' in script.text
    assert "Not found" not in script.text
    assert "Not shown" not in script.text
    assert "invoice-line-table" in script.text


async def test_invoice_parser_presentation_remains_available() -> None:
    """The presentation stays truthful, complete, and keyboard driven."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/invoice-parser/presentation/")
        script = await client.get("/static/js/invoice-presentation.js")

    page = " ".join(response.text.split())

    assert response.status_code == 200
    assert script.status_code == 200
    assert "data-presentation" in page
    assert "data-speaker-notes" in page
    assert page.count("data-slide") == 21
    assert "data-duration=" not in page
    assert "Timing:" not in page
    assert "Finish by" not in page
    assert "[Sources]" not in page
    assert 'id="duration"' not in script.text
    assert "current.duration" not in script.text
    assert "PyHou" not in page
    assert "data-presentation-date" in page
    assert "Intl.DateTimeFormat" in script.text
    assert "if (includeSlides) message.slides = slideMetadata;" in script.text
    assert "postMessage(message, presentationOrigin)" in script.text
    assert 'postMessage({ type: "presentation-state", index, slides:' not in script.text
    assert "postMessage({type},'*')" not in script.text
    assert "Swap the model string. The Agent contract stays." in page
    assert "Who owns the loop?" in page
    assert "Tools use typed dependencies" in page
    assert "Schemas travel with the request" in page
    assert "Final total printed on the invoice." in page
    assert "The run leaves a message trace" in page
    assert "all_agent_messages" in page
    assert "search_supplier_candidates" in page
    assert '"part_kind"' in page
    assert "One candidate continues. Ambiguity stops." in page
    assert "0 or 2+ candidates" in page
    assert "The model never chooses among ambiguous records." in page
    assert "Pydantic validates structure, not reality." in page
    assert "Validation can send focused feedback back to the model" in page
    assert "Retry interpretation problems." in page
    assert "A Pydantic schema for typed validation" in page
    assert "/static/images/brian-newman-headshot.webp" in page
    assert "/static/images/brian-newman-portfolio-qr.png" in page
    assert "FunctionModel" in page
    assert "Newman Labs home" in page
    assert page.count('<figure class="code-editor') == 8
    assert 'class="code-line" data-line="34"' in page
    assert "/static/images/invoice-presentation-hero.jpg" in page
    assert "/static/demos/invoice-supplier-match.pdf" in page
    assert "/static/demos/invoice-supplier-match-preview.png" in page
    assert "/static/js/invoice-presentation.js" in page


async def test_invoice_parser_presentation_uses_local_fonts() -> None:
    """The standalone presentation avoids third-party font requests."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/invoice-parser/presentation/")

    assert response.status_code == 200
    assert "/static/fonts/newsreader-latin-wght-normal.woff2" in response.text
    assert "/static/fonts/manrope-latin-wght-normal.woff2" in response.text
    assert "fonts.googleapis.com" not in response.text
    assert "fonts.gstatic.com" not in response.text


async def test_invoice_parser_presenter_keeps_controls_stable() -> None:
    """Presenter title wrapping does not move the notes and controls."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        script = await client.get("/static/js/invoice-presentation.js")

    assert script.status_code == 200
    assert "grid-template-rows:auto minmax(0,1fr) auto" in script.text
    assert "min-width:0;min-height:0" in script.text
    assert ".preview{min-height:150px" in script.text


async def test_extract_invoice_route_dispatches_a_managed_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A preflighted PDF upload is staged for managed extraction."""
    start = AsyncMock(
        return_value=InvoiceExtractionJob(
            document_id=DOCUMENT_ID,
            flow_run_id=FLOW_RUN_ID,
        )
    )
    monkeypatch.setattr(invoice_parser, "start_invoice_extraction", start)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/invoice-parser/api/extractions",
            data={"passcode": "newman-test-passcode"},
            files={"document": ("newman-invoice.pdf", b"%PDF-1.7\n", "application/pdf")},
        )

    assert response.status_code == 202
    assert response.json()["document_id"] == str(DOCUMENT_ID)
    assert response.json()["flow_run_id"] == str(FLOW_RUN_ID)
    assert len(response.json()["access_token"]) == 64
    assert start.await_args is not None
    source = start.await_args.kwargs["source"]
    assert source.original_filename == "newman-invoice.pdf"
    assert source.content == b"%PDF-1.7\n"


async def test_extract_invoice_route_returns_safe_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Document-security failures are safe client errors."""
    monkeypatch.setattr(
        invoice_parser,
        "start_invoice_extraction",
        AsyncMock(side_effect=DocumentRejectedError("The document is not safe")),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/invoice-parser/api/extractions",
            data={"passcode": "newman-test-passcode"},
            files={"document": ("newman.pdf", b"%PDF-1.7\n", "application/pdf")},
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "The document is not safe"}


async def test_extract_invoice_rejects_invalid_access_before_staging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An invalid upload code cannot reach storage or managed work."""
    start = AsyncMock()
    monkeypatch.setattr(invoice_parser, "start_invoice_extraction", start)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/invoice-parser/api/extractions",
            data={"passcode": "incorrect"},
            files={"document": ("newman.pdf", b"%PDF-1.7\n", "application/pdf")},
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "The invoice processing access code is not valid."}
    start.assert_not_awaited()


async def test_extract_invoice_rejects_missing_passcode_before_staging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An omitted upload code cannot stage managed work."""
    start = AsyncMock()
    monkeypatch.setattr(invoice_parser, "start_invoice_extraction", start)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/invoice-parser/api/extractions",
            files={"document": ("newman.pdf", b"%PDF-1.7\n", "application/pdf")},
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "The invoice processing access code is not valid."}
    start.assert_not_awaited()


async def test_extract_invoice_rate_limits_repeated_submissions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeated submissions return 429 with Retry-After before managed work."""
    start = AsyncMock()
    monkeypatch.setattr(invoice_parser, "start_invoice_extraction", start)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(INVOICE_SUBMISSION_RATE_LIMIT.max_requests):
            response = await client.post(
                "/invoice-parser/api/extractions",
                data={"passcode": "incorrect"},
                files={"document": ("newman.pdf", b"%PDF-1.7\n", "application/pdf")},
            )
            assert response.status_code == 403
        locked = await client.post(
            "/invoice-parser/api/extractions",
            data={"passcode": "incorrect"},
            files={"document": ("newman.pdf", b"%PDF-1.7\n", "application/pdf")},
        )

    assert locked.status_code == 429
    assert locked.json() == {"detail": INVOICE_SUBMISSION_RATE_LIMIT.detail}
    assert locked.headers["retry-after"].isdigit()
    assert int(locked.headers["retry-after"]) > 0
    start.assert_not_awaited()


async def test_extract_invoice_allows_valid_passcode_after_failed_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Submissions below the request limit do not block a valid passcode."""
    start = AsyncMock(
        return_value=InvoiceExtractionJob(
            document_id=DOCUMENT_ID,
            flow_run_id=FLOW_RUN_ID,
        )
    )
    monkeypatch.setattr(invoice_parser, "start_invoice_extraction", start)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(INVOICE_SUBMISSION_RATE_LIMIT.max_requests - 1):
            failed = await client.post(
                "/invoice-parser/api/extractions",
                data={"passcode": "incorrect"},
                files={"document": ("newman.pdf", b"%PDF-1.7\n", "application/pdf")},
            )
            assert failed.status_code == 403
        response = await client.post(
            "/invoice-parser/api/extractions",
            data={"passcode": "newman-test-passcode"},
            files={"document": ("newman-invoice.pdf", b"%PDF-1.7\n", "application/pdf")},
        )

    assert response.status_code == 202
    start.assert_awaited_once()


async def test_get_invoice_extraction_route_reports_an_active_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Polling remains pending while managed compute is active."""
    monkeypatch.setattr(
        invoice_parser,
        "get_invoice_extraction_job",
        AsyncMock(return_value=None),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/invoice-parser/api/extractions/{FLOW_RUN_ID}",
            params={"document_id": str(DOCUMENT_ID)},
            headers={"X-Invoice-Job-Access": job_access_token()},
        )

    assert response.status_code == 202
    assert response.headers["retry-after"] == "2"
    assert response.json() == {
        "document_id": str(DOCUMENT_ID),
        "flow_run_id": str(FLOW_RUN_ID),
        "access_token": job_access_token(),
    }


async def test_get_invoice_extraction_route_returns_the_typed_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A completed managed job returns its transient typed result."""
    monkeypatch.setattr(
        invoice_parser,
        "get_invoice_extraction_job",
        AsyncMock(return_value=extraction()),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/invoice-parser/api/extractions/{FLOW_RUN_ID}",
            params={"document_id": str(DOCUMENT_ID)},
            headers={"X-Invoice-Job-Access": job_access_token()},
        )

    assert response.status_code == 200
    assert response.json()["invoice"]["invoice_number"] == "INV-1042"
    assert response.json()["supplier_match"]["supplier_id"] == "SUP-1001"
    assert response.json()["document_url"].startswith("https://storage.example/")


async def test_get_invoice_extraction_route_hides_managed_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Managed runtime failures do not expose internal provider details."""
    monkeypatch.setattr(
        invoice_parser,
        "get_invoice_extraction_job",
        AsyncMock(side_effect=InvoiceExtractionJobFailedError("newman provider failure")),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/invoice-parser/api/extractions/{FLOW_RUN_ID}",
            params={"document_id": str(DOCUMENT_ID)},
            headers={"X-Invoice-Job-Access": job_access_token()},
        )

    assert response.status_code == 502
    assert response.json() == {"detail": "The managed invoice extraction did not complete. Try again."}


async def test_get_invoice_extraction_route_reports_full_managed_capacity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A concurrency cancellation tells the caller to retry without exposing Prefect details."""
    monkeypatch.setattr(
        invoice_parser,
        "get_invoice_extraction_job",
        AsyncMock(side_effect=InvoiceExtractionCapacityError("newman capacity full")),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/invoice-parser/api/extractions/{FLOW_RUN_ID}",
            params={"document_id": str(DOCUMENT_ID)},
            headers={"X-Invoice-Job-Access": job_access_token()},
        )

    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"
    assert response.json() == {"detail": "Maximum processing capacity reached. Try again in a few minutes."}


async def test_extract_invoice_route_rejects_an_unbounded_filename(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An attacker-controlled multipart filename stays within persistence limits."""
    start = AsyncMock()
    monkeypatch.setattr(invoice_parser, "start_invoice_extraction", start)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/invoice-parser/api/extractions",
            data={"passcode": "newman-test-passcode"},
            files={"document": (f"{'n' * 252}.pdf", b"%PDF-1.7\n", "application/pdf")},
        )

    assert response.status_code == 422
    start.assert_not_awaited()


async def test_get_invoice_extraction_rejects_invalid_capability_before_prefect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A guessed job identifier cannot trigger an authenticated Prefect lookup."""
    get_job = AsyncMock()
    monkeypatch.setattr(invoice_parser, "get_invoice_extraction_job", get_job)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/invoice-parser/api/extractions/{FLOW_RUN_ID}",
            params={"document_id": str(DOCUMENT_ID)},
            headers={"X-Invoice-Job-Access": "invalid"},
        )

    assert response.status_code == 404
    get_job.assert_not_awaited()
