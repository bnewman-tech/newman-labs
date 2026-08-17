# Invoice Parser demos

The four PDFs are fictional United States services and goods invoices. Their
matching JSON files contain committed invoice, supplier-match, and parsed-text
fixtures. `invoice-supplier-match.pdf` resolves to one canonical supplier;
`invoice-supplier-review.pdf` deliberately resolves to two candidates and keeps
the supplier match null. The public demo loads the real PDFs in the same native
browser viewer used for uploads, so it can display the complete inspection
workspace without calling the model.

The files contain no real companies, addresses, contacts, customer data, or
payment data. They remain committed so the public Invoice Parser always has four
stable demonstrations.
