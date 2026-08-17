"""Invoice extraction workflow tests."""

from contextlib import nullcontext
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import pytest
from pydantic_ai import UnexpectedModelBehavior, UsageLimitExceeded, capture_run_messages
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from labs.invoice_parser import functions
from labs.invoice_parser.functions import (
    extract_invoice_document,
    get_invoice_extraction_job,
    run_invoice_extraction,
    start_invoice_extraction,
)
from labs.invoice_parser.schemas import (
    InvoiceAgentOutput,
    InvoiceExtraction,
    InvoiceExtractionJob,
    InvoiceLineItem,
    InvoiceParty,
    ParsedInvoice,
    SupplierMatch,
)
from libs.core.dependencies import EnvironmentMode
from libs.database.schemas import ProcessedDocument
from libs.document_intelligence.schemas import DocumentUpload


def parsed_invoice() -> ParsedInvoice:
    """Return one synthetic invoice extraction."""
    return ParsedInvoice(
        invoice_number="INV-2026-0816",
        issue_date=date(2026, 8, 16),
        purchase_order_number="MR-4821",
        currency="USD",
        seller=InvoiceParty(name="Northstar Design Studio", address="1418 Elliott Avenue"),
        buyer=InvoiceParty(name="Meridian Research Group", address="500 Congress Avenue"),
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
        tax_total=Decimal("0.00"),
        total=Decimal("9500.00"),
    )


def agent_output() -> InvoiceAgentOutput:
    """Return one invoice enriched through the fake ERP supplier lookup."""
    return InvoiceAgentOutput(
        invoice=parsed_invoice(),
        supplier_match=SupplierMatch(
            supplier_id="SUP-1001",
            name="Northstar Design Studio LLC",
        ),
    )


def invoice_model(
    *,
    output: InvoiceAgentOutput | dict[str, object],
    printed_name: str | None = None,
    agent_infos: list[AgentInfo] | None = None,
) -> FunctionModel:
    """Return a deterministic model that performs the required supplier lookup."""
    output_args = output.model_dump(mode="json") if isinstance(output, InvoiceAgentOutput) else output
    invoice = cast("dict[str, object]", output_args["invoice"])
    seller = cast("dict[str, object]", invoice["seller"])
    lookup_name = printed_name or cast("str", seller["name"])

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if agent_infos is not None:
            agent_infos.append(info)
        tool_returned = any(isinstance(part, ToolReturnPart) for message in messages for part in message.parts)
        if not tool_returned:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name=info.function_tools[0].name,
                        args={"printed_name": lookup_name},
                    )
                ]
            )
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=info.output_tools[0].name,
                    args=output_args,
                )
            ]
        )

    return FunctionModel(respond, profile={"supports_thinking": True})


async def test_extract_invoice_uses_typed_pydantic_ai_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The single agent returns the validated invoice contract."""
    expected = agent_output()
    agent_infos: list[AgentInfo] = []
    model = invoice_model(output=expected, agent_infos=agent_infos)

    build_model = AsyncMock(return_value=model)
    monkeypatch.setattr(functions, "build_agent_model", build_model)

    result = await run_invoice_extraction(markdown="# Synthetic invoice")

    build_model.assert_awaited_once_with(model=functions.PydanticAIModel.MINIMAX_M3)
    assert result.output == expected
    assert result.metadata == {"lab": "invoice_parser", "stage": "extraction"}
    assert result.usage.requests == 2
    request_parameters = agent_infos[0].model_request_parameters
    assert request_parameters.thinking == "low"
    assert request_parameters.instruction_parts is not None
    assert "Return null" in request_parameters.instruction_parts[0].content
    assert "'NOT PROVIDED'" in request_parameters.instruction_parts[0].content
    function_tool = request_parameters.function_tools[0]
    assert function_tool.name == "search_supplier_candidates"
    tool_description = function_tool.description
    assert tool_description is not None
    assert "printed invoice seller name" in tool_description
    function_properties = cast(
        "dict[str, dict[str, object]]",
        function_tool.parameters_json_schema["properties"],
    )
    assert function_properties["printed_name"]["description"] == ("Seller name exactly as it appears on the invoice.")

    output_schema = request_parameters.output_tools[0].parameters_json_schema
    output_definitions = cast("dict[str, dict[str, object]]", output_schema["$defs"])
    parsed_invoice_schema = output_definitions["ParsedInvoice"]
    parsed_invoice_properties = cast(
        "dict[str, dict[str, object]]",
        parsed_invoice_schema["properties"],
    )
    assert parsed_invoice_properties["total"]["description"] == ("Final total printed on the invoice.")


async def test_extract_invoice_rejects_an_invalid_total(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-positive invoice total exhausts bounded output retries."""
    invalid = agent_output().model_dump(mode="json")
    invalid["invoice"]["total"] = "0.00"

    monkeypatch.setattr(
        functions,
        "build_agent_model",
        AsyncMock(return_value=invoice_model(output=invalid)),
    )

    with capture_run_messages() as messages, pytest.raises(UnexpectedModelBehavior):
        await run_invoice_extraction(markdown="# Synthetic invoice")

    assert sum(isinstance(message, ModelResponse) for message in messages) == 5


async def test_extract_invoice_retries_when_totals_do_not_reconcile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A validly shaped but inconsistent invoice exhausts output retries."""
    invalid = agent_output().model_dump(mode="json")
    invalid["invoice"]["tax_total"] = "100.00"

    monkeypatch.setattr(
        functions,
        "build_agent_model",
        AsyncMock(return_value=invoice_model(output=invalid)),
    )

    with capture_run_messages() as messages, pytest.raises(UnexpectedModelBehavior):
        await run_invoice_extraction(markdown="# Synthetic invoice")

    assert sum(isinstance(message, ModelResponse) for message in messages) == 5


async def test_extract_invoice_skips_reconciliation_when_tax_is_not_printed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing optional tax evidence does not cause the agent to invent a value."""
    invoice = agent_output().model_copy(update={"invoice": parsed_invoice().model_copy(update={"tax_total": None})})
    monkeypatch.setattr(
        functions,
        "build_agent_model",
        AsyncMock(return_value=invoice_model(output=invoice)),
    )

    result = await run_invoice_extraction(markdown="# Synthetic invoice")

    assert result.output == invoice
    assert result.usage.requests == 2


async def test_supplier_lookup_requires_review_for_an_ambiguous_printed_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two supplier candidates remain unresolved instead of being guessed."""
    invoice = parsed_invoice().model_copy(update={"seller": InvoiceParty(name="Pacific Industrial")})
    expected = InvoiceAgentOutput(invoice=invoice, supplier_match=None)
    monkeypatch.setattr(
        functions,
        "build_agent_model",
        AsyncMock(return_value=invoice_model(output=expected)),
    )

    result = await run_invoice_extraction(markdown="# Synthetic invoice")

    assert result.output == expected
    assert result.usage.requests == 2


async def test_supplier_lookup_cannot_execute_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The run rejects multiple supplier lookup calls before executing them."""

    def request_two_lookups(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=info.function_tools[0].name,
                    args={"printed_name": "Northstar Design Studio"},
                    tool_call_id="lookup-1",
                ),
                ToolCallPart(
                    tool_name=info.function_tools[0].name,
                    args={"printed_name": "Northstar Design Studio"},
                    tool_call_id="lookup-2",
                ),
            ]
        )

    monkeypatch.setattr(
        functions,
        "build_agent_model",
        AsyncMock(return_value=FunctionModel(request_two_lookups, profile={"supports_thinking": True})),
    )

    with pytest.raises(UsageLimitExceeded, match="tool_calls_limit of 1"):
        await run_invoice_extraction(markdown="# Synthetic invoice")


async def test_supplier_lookup_retries_an_unrecognized_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The validator rejects supplier IDs not returned by the lookup tool."""
    invalid = agent_output().model_copy(
        update={
            "supplier_match": SupplierMatch(
                supplier_id="SUP-9999",
                name="Invented Supplier",
            )
        }
    )
    monkeypatch.setattr(
        functions,
        "build_agent_model",
        AsyncMock(return_value=invoice_model(output=invalid)),
    )

    with capture_run_messages() as messages, pytest.raises(UnexpectedModelBehavior):
        await run_invoice_extraction(markdown="# Synthetic invoice")

    assert sum(isinstance(message, ModelResponse) for message in messages) == 5


async def test_supplier_lookup_retries_when_the_tool_uses_the_wrong_seller_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The validator rejects a supplier lookup made with a different seller name."""
    expected = agent_output()
    monkeypatch.setattr(
        functions,
        "build_agent_model",
        AsyncMock(return_value=invoice_model(output=expected, printed_name="a")),
    )

    with capture_run_messages() as messages, pytest.raises(UnexpectedModelBehavior):
        await run_invoice_extraction(markdown="# Synthetic invoice")

    assert sum(isinstance(message, ModelResponse) for message in messages) == 5


async def test_document_workflow_persists_then_extracts_markdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The lab saves the generic document before invoking its one agent."""
    document_id = uuid4()
    parse_id = uuid4()
    source = DocumentUpload(
        document_id=document_id,
        original_filename="newman-invoice.pdf",
        media_type="application/pdf",
        content=b"%PDF-1.7\n",
    )
    processed = ProcessedDocument(
        document_id=document_id,
        parse_id=parse_id,
        chunk_count=0,
        storage_bucket="newman-labs",
        original_object_key=f"documents/{document_id}/original.pdf",
        markdown_object_key=f"documents/{document_id}/parses/{parse_id}/document.md",
        docling_document_object_key=f"documents/{document_id}/parses/{parse_id}/docling.json",
        markdown="# Invoice",
        docling_document={"name": "newman-invoice"},
    )
    process_document = AsyncMock(return_value=processed)
    agent_messages: list[ModelMessage] = [ModelRequest.user_text_prompt("# Invoice")]
    run_extraction = AsyncMock(
        return_value=SimpleNamespace(
            output=agent_output(),
            all_messages=Mock(return_value=agent_messages),
        )
    )
    create_download_url = AsyncMock(return_value="https://storage.example/newman.pdf?signature=temporary")
    monkeypatch.setattr(functions, "process_document", process_document)
    monkeypatch.setattr(functions, "run_invoice_extraction", run_extraction)
    monkeypatch.setattr(functions, "create_download_url", create_download_url)
    monkeypatch.setattr(functions.logfire, "span", Mock(return_value=nullcontext()))

    result = await extract_invoice_document(source=source)

    assert result.document_id == document_id
    assert result.document_url.startswith("https://storage.example/")
    assert result.document_markdown == "# Invoice"
    assert result.invoice == parsed_invoice()
    assert result.supplier_match == agent_output().supplier_match
    assert result.all_agent_messages == agent_messages
    process_document.assert_awaited_once_with(source=source)
    run_extraction.assert_awaited_once_with(markdown="# Invoice")
    create_download_url.assert_awaited_once_with(
        bucket="newman-labs",
        key=f"documents/{document_id}/original.pdf",
    )


async def test_start_invoice_extraction_preflights_stages_and_dispatches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The web boundary stores only preflighted bytes and passes references to Prefect."""
    document_id = uuid4()
    flow_run_id = uuid4()
    source = DocumentUpload(
        document_id=document_id,
        original_filename="newman-invoice.pdf",
        media_type="application/pdf",
        content=b"%PDF-1.7\n",
    )
    preflight = AsyncMock()
    create_blobs = AsyncMock()
    dispatch = AsyncMock(return_value=SimpleNamespace(id=flow_run_id))
    monkeypatch.setattr(functions, "preflight_document", preflight)
    monkeypatch.setattr(functions, "create_blobs", create_blobs)
    monkeypatch.setattr(functions, "arun_deployment", dispatch)

    monkeypatch.setattr(functions.settings, "environment", EnvironmentMode.PROD)

    job = await start_invoice_extraction(source=source)

    assert job == InvoiceExtractionJob(
        document_id=document_id,
        flow_run_id=flow_run_id,
    )
    preflight.assert_awaited_once_with(source=source)
    assert create_blobs.await_args is not None
    staged = create_blobs.await_args.kwargs["blobs"][0]
    assert staged.key == f"document-processing/{document_id}/source.pdf"
    assert staged.content == source.content
    dispatch.assert_awaited_once_with(
        name=functions.INVOICE_EXTRACTION_DEPLOYMENTS[EnvironmentMode.PROD],
        parameters={
            "document_id": str(document_id),
            "original_filename": source.original_filename,
            "media_type": source.media_type,
            "environment": "prod",
        },
        timeout=0,
        as_subflow=False,
        idempotency_key=str(document_id),
    )


async def test_get_invoice_extraction_job_returns_and_deletes_transient_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A completed run delivers its typed result and removes the handoff object."""
    document_id = uuid4()
    flow_run_id = uuid4()
    job = InvoiceExtractionJob(document_id=document_id, flow_run_id=flow_run_id)
    state = Mock()
    state.is_final.return_value = True
    state.is_cancelled.return_value = False
    state.is_completed.return_value = True
    client = AsyncMock()
    client.read_flow_run.return_value = SimpleNamespace(
        state=state,
        parameters={"document_id": str(document_id)},
    )
    client_context = MagicMock()
    client_context.__aenter__ = AsyncMock(return_value=client)
    client_context.__aexit__ = AsyncMock(return_value=None)
    expected = InvoiceExtraction(
        document_id=document_id,
        document_url="https://storage.example/newman.pdf?signature=temporary",
        document_markdown="# Invoice",
        invoice=parsed_invoice(),
        all_agent_messages=[],
    )
    read_blob = AsyncMock(return_value=SimpleNamespace(content=expected.model_dump_json().encode()))
    delete_blob = AsyncMock()
    monkeypatch.setattr(functions, "get_client", Mock(return_value=client_context))
    monkeypatch.setattr(functions, "read_blob", read_blob)
    monkeypatch.setattr(functions, "delete_blob", delete_blob)

    result = await get_invoice_extraction_job(job=job)

    assert result == expected
    read_blob.assert_awaited_once_with(
        bucket=functions.DOCUMENT_STORAGE_BUCKET,
        key=f"document-processing/{document_id}/result.json",
    )
    delete_blob.assert_awaited_once_with(
        bucket=functions.DOCUMENT_STORAGE_BUCKET,
        key=f"document-processing/{document_id}/result.json",
    )


async def test_get_invoice_extraction_job_rejects_a_mismatched_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A completed Prefect run cannot retrieve another document's result."""
    document_id = uuid4()
    job = InvoiceExtractionJob(document_id=document_id, flow_run_id=uuid4())
    client = AsyncMock()
    client.read_flow_run.return_value = SimpleNamespace(
        parameters={"document_id": str(uuid4())},
    )
    client_context = MagicMock()
    client_context.__aenter__ = AsyncMock(return_value=client)
    client_context.__aexit__ = AsyncMock(return_value=None)
    read_blob = AsyncMock()
    monkeypatch.setattr(functions, "get_client", Mock(return_value=client_context))
    monkeypatch.setattr(functions, "read_blob", read_blob)

    with pytest.raises(
        functions.InvoiceExtractionJobFailedError,
        match="does not match the requested document",
    ):
        await get_invoice_extraction_job(job=job)

    read_blob.assert_not_awaited()


async def test_get_invoice_extraction_job_reports_a_cancelled_run_as_full_capacity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A CANCEL_NEW collision is distinct from an infrastructure failure."""
    document_id = uuid4()
    state = Mock()
    state.is_final.return_value = True
    state.is_cancelled.return_value = True
    client = AsyncMock()
    client.read_flow_run.return_value = SimpleNamespace(
        parameters={"document_id": str(document_id)},
        state=state,
    )
    client_context = MagicMock()
    client_context.__aenter__ = AsyncMock(return_value=client)
    client_context.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(functions, "get_client", Mock(return_value=client_context))

    with pytest.raises(functions.InvoiceExtractionCapacityError, match="capacity is full"):
        await get_invoice_extraction_job(
            job=InvoiceExtractionJob(document_id=document_id, flow_run_id=uuid4()),
        )
