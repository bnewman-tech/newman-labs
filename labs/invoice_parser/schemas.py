"""Typed invoice extraction contracts."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import Field, field_validator
from pydantic_ai import ModelMessage

from libs.core.pydantic_base import NewmanLabsModel


class InvoiceParty(NewmanLabsModel):
    """Seller or buyer identified on an invoice."""

    name: str = Field(min_length=1, max_length=255)
    address: str | None = Field(default=None, max_length=2_000)
    tax_id: str | None = Field(default=None, max_length=100)

    @field_validator("address")
    @classmethod
    def normalize_address(cls, value: str | None) -> str | None:
        """Normalize punctuation and whitespace that models render inconsistently."""
        return " ".join(value.replace(",", " ").replace(".", "").split()) if value is not None else None


class InvoiceLineItem(NewmanLabsModel):
    """One invoice line without assuming a regional tax or catalog format."""

    description: str = Field(min_length=1, max_length=2_000)
    quantity: Decimal | None = Field(default=None, gt=0)
    unit: str | None = Field(default=None, max_length=100)
    unit_price: Decimal | None = None
    discount: Decimal | None = Field(default=None, ge=0)
    tax_rate: Decimal | None = Field(default=None, ge=0, le=100)
    tax_amount: Decimal | None = None
    line_total: Decimal


class ParsedInvoice(NewmanLabsModel):
    """Structured invoice extracted from Docling evidence by Pydantic AI."""

    invoice_number: str = Field(min_length=1, max_length=100)
    issue_date: date
    due_date: date | None = None
    purchase_order_number: str | None = Field(default=None, max_length=100)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    seller: InvoiceParty
    buyer: InvoiceParty | None = None
    payment_terms: str | None = Field(default=None, max_length=500)
    line_items: list[InvoiceLineItem] = Field(default_factory=list, max_length=500)
    subtotal: Decimal | None = None
    discount_total: Decimal | None = Field(default=None, ge=0)
    shipping_total: Decimal | None = Field(default=None, ge=0)
    tax_total: Decimal | None = None
    total: Decimal = Field(
        gt=0,
        description="Final total printed on the invoice.",
    )

    @field_validator("line_items", mode="before")
    @classmethod
    def normalize_line_items(cls, value: object) -> object:
        """Unwrap the singular item container emitted by some models."""
        if isinstance(value, dict) and set(value) == {"item"}:
            items = value["item"]
            return items if isinstance(items, list) else [items]
        return value

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, value: object) -> object:
        """Normalize a three-letter currency code without guessing its value."""
        return value.upper() if isinstance(value, str) else value


class SupplierMatch(NewmanLabsModel):
    """One canonical supplier resolved through the agent's lookup tool."""

    supplier_id: str = Field(pattern=r"^SUP-\d{4}$")
    name: str = Field(min_length=1, max_length=255)


class InvoiceAgentOutput(NewmanLabsModel):
    """Invoice fields plus the optional fake ERP supplier match."""

    invoice: ParsedInvoice
    supplier_match: SupplierMatch | None = None


class InvoiceExtraction(NewmanLabsModel):
    """One persisted document with its transient extraction and agent trace."""

    document_id: UUID
    document_url: str = Field(pattern=r"^https://", min_length=1)
    document_markdown: str = Field(min_length=1)
    invoice: ParsedInvoice
    supplier_match: SupplierMatch | None = None
    all_agent_messages: list[ModelMessage]


class InvoiceExtractionJob(NewmanLabsModel):
    """One in-flight invoice extraction."""

    document_id: UUID
    flow_run_id: UUID
