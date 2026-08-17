"""Read-only supplier search against the synthetic ERP dataset."""

import re
from pathlib import Path

from pydantic import TypeAdapter

from labs.invoice_parser.schemas import SupplierMatch

_SUPPLIERS_PATH = Path(__file__).parents[2] / "data" / "suppliers.json"
_SUPPLIERS = tuple(TypeAdapter(list[SupplierMatch]).validate_json(_SUPPLIERS_PATH.read_bytes()))


def search_suppliers(*, printed_name: str) -> list[SupplierMatch]:
    """Return fake ERP suppliers whose normalized name contains the printed name."""
    normalized_name = " ".join(re.sub(r"[^a-z0-9]+", " ", printed_name.casefold()).split())
    return [
        supplier
        for supplier in _SUPPLIERS
        if normalized_name and normalized_name in " ".join(re.sub(r"[^a-z0-9]+", " ", supplier.name.casefold()).split())
    ]
