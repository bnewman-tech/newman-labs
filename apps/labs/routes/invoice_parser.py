"""Invoice Parser pages and extraction API."""

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, Response

from apps.labs.schemas import InvoiceExtractionJobResponse
from apps.labs.security import (
    create_job_access_token,
    has_valid_invoice_access,
    has_valid_job_access,
)
from apps.labs.templating import templates
from labs.invoice_parser.functions import (
    InvoiceExtractionCapacityError,
    InvoiceExtractionJobFailedError,
    get_invoice_extraction_job,
    start_invoice_extraction,
)
from labs.invoice_parser.schemas import InvoiceExtraction, InvoiceExtractionJob
from libs.docling.settings import PDF_MAX_FILE_SIZE_BYTES, PDF_MAX_PAGES
from libs.document_intelligence.schemas import (
    DOCUMENT_FILENAME_MAX_LENGTH,
    DocumentUpload,
)
from libs.document_intelligence.security import DocumentRejectedError

router = APIRouter(prefix="/invoice-parser", tags=["invoice-parser"])
INVOICE_EXTRACTION_RETRY_AFTER_SECONDS = 2
INVOICE_EXTRACTION_CAPACITY_RETRY_AFTER_SECONDS = 60


def require_invoice_extraction_access(
    request: Request,
    passcode: Annotated[str, Form(max_length=128)] = "",
) -> None:
    """Validate access before invoice extraction starts."""
    if not has_valid_invoice_access(request=request, passcode=passcode):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The invoice processing access code is not valid.",
        )


@router.get("/", response_class=HTMLResponse, name="invoice_parser")
async def invoice_parser_page(request: Request) -> HTMLResponse:
    """Render the single-document extraction workspace."""
    return templates.TemplateResponse(
        request=request,
        name="labs/invoice_parser.html",
        context={
            "active_page": "invoice-parser",
            "max_file_size_mb": PDF_MAX_FILE_SIZE_BYTES // (1024 * 1024),
            "max_pages": PDF_MAX_PAGES,
        },
    )


@router.get(
    "/presentation/",
    response_class=HTMLResponse,
    name="invoice_parser_presentation",
)
async def invoice_parser_presentation(request: Request) -> HTMLResponse:
    """Render the browser-native Pydantic AI presentation."""
    return templates.TemplateResponse(
        request=request,
        name="labs/invoice_parser_presentation.html",
        context={"active_page": "invoice-parser"},
    )


@router.post(
    "/api/extractions",
    name="extract_invoice",
    status_code=status.HTTP_202_ACCEPTED,
)
async def extract_invoice(
    request: Request,
    _access: Annotated[None, Depends(require_invoice_extraction_access)],
    document: Annotated[
        UploadFile,
        File(description="One English-language PDF invoice"),
    ],
) -> InvoiceExtractionJobResponse:
    """Securely start one invoice extraction."""
    original_filename = (document.filename or "document.pdf").replace("\\", "/")
    original_filename = original_filename.rsplit("/", maxsplit=1)[-1]
    if len(original_filename) > DOCUMENT_FILENAME_MAX_LENGTH:
        await document.close()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The PDF filename cannot exceed 255 characters.",
        )
    try:
        content = await document.read(PDF_MAX_FILE_SIZE_BYTES + 1)
    finally:
        await document.close()

    try:
        job = await start_invoice_extraction(
            source=DocumentUpload(
                document_id=uuid4(),
                original_filename=original_filename,
                media_type=document.content_type or "",
                content=content,
            )
        )
        return InvoiceExtractionJobResponse(
            document_id=job.document_id,
            flow_run_id=job.flow_run_id,
            access_token=create_job_access_token(
                invoice_access_token=request.app.state.invoice_parser_access_token,
                document_id=job.document_id,
                flow_run_id=job.flow_run_id,
            ),
        )
    except DocumentRejectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


@router.get("/api/extractions/{flow_run_id}", name="get_invoice_extraction")
async def get_invoice_extraction(
    request: Request,
    flow_run_id: UUID,
    document_id: UUID,
    access_token: Annotated[str, Header(alias="X-Invoice-Job-Access")],
    response: Response,
) -> InvoiceExtraction | InvoiceExtractionJobResponse:
    """Poll one extraction and return its result when complete."""
    if not has_valid_job_access(
        request=request,
        document_id=document_id,
        flow_run_id=flow_run_id,
        access_token=access_token,
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice extraction not found.",
        )
    job = InvoiceExtractionJob(
        document_id=document_id,
        flow_run_id=flow_run_id,
    )
    try:
        extraction = await get_invoice_extraction_job(job=job)
    except InvoiceExtractionCapacityError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Maximum processing capacity reached. Try again in a few minutes.",
            headers={"Retry-After": str(INVOICE_EXTRACTION_CAPACITY_RETRY_AFTER_SECONDS)},
        ) from exc
    except InvoiceExtractionJobFailedError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The managed invoice extraction did not complete. Try again.",
        ) from exc
    if extraction is None:
        response.status_code = status.HTTP_202_ACCEPTED
        response.headers["Retry-After"] = str(INVOICE_EXTRACTION_RETRY_AFTER_SECONDS)
        return InvoiceExtractionJobResponse(
            document_id=job.document_id,
            flow_run_id=job.flow_run_id,
            access_token=access_token,
        )
    return extraction
