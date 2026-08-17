# Invoice parser fixtures

These PDFs are synthetic United States invoices for local extraction testing. All
names, addresses, invoice numbers, and amounts are fictitious.

`suppliers.json` is the fictional supplier master exposed by the Lab's read-only
fake ERP integration. It contains only canonical supplier IDs and names; normalized
name matching demonstrates unique and ambiguous lookup outcomes.

- `invoice_01_clean_standard.pdf` is a straightforward invoice.
- `invoice_02_missing_po.pdf` omits an optional purchase order number.
- `invoice_03_total_mismatch.pdf` contains a deliberately inconsistent printed total.
- `invoice_04_noisy_service_ticket.pdf` includes unrelated service-ticket content.
