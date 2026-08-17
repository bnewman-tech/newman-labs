"""Synthetic ERP supplier lookup tests."""

from labs.invoice_parser.integrations.fake_erp.functions import search_suppliers


def test_search_suppliers_returns_one_canonical_match() -> None:
    """A known printed name resolves to its canonical ERP supplier ID."""
    candidates = search_suppliers(printed_name="Northstar Design Studio")

    assert [candidate.supplier_id for candidate in candidates] == ["SUP-1001"]
    assert candidates[0].name == "Northstar Design Studio LLC"


def test_search_suppliers_preserves_ambiguous_candidates() -> None:
    """A shared partial name returns every candidate instead of guessing."""
    candidates = search_suppliers(printed_name="Pacific Industrial")

    assert [candidate.supplier_id for candidate in candidates] == ["SUP-3007", "SUP-3011"]


def test_search_suppliers_returns_an_empty_list_for_an_unknown_name() -> None:
    """An unknown printed name produces a successful empty lookup."""
    assert search_suppliers(printed_name="Unknown Supplier") == []
