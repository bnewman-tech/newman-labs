# Invoice Parser

Invoice Parser is a small, public document-extraction workflow. FastAPI validates
one PDF and applies the pinned YARA gate before private staging. The production
upload requires its shared access passcode, and the application applies bounded
process-local per-client limits with stricter policies for submissions and polling.
Each polling request carries a signed job capability, and Prefect deployment
concurrency rejects work beyond the configured capacity. Managed compute then
runs DocFirewall, Docling, the generic document pipeline, and one
Pydantic AI agent before returning a typed invoice and optional supplier match
from the read-only fake ERP integration.

The MVP deliberately stops there. It does not classify documents, query a
production ERP,
persist invoice analyses, retain browser history, save human reviews, or create
embeddings. The document record and its private objects follow the shared 30-day
retention policy. The structured invoice uses a private transient handoff object
that is deleted when the browser retrieves it; no invoice-analysis record is
retained.

## Data

The four PDFs under `data/` are fictional United States invoices for local live
testing. The four permanent public demos under `apps/labs/static/demos/` are also
fictional United States invoices and include committed pre-parsed JSON fixtures.
Two show the supplier tool's deterministic outcomes: one match and one ambiguous
name that requires review.

## Run

Open `/invoice-parser/` to use a permanent demo or upload a PDF. The page posts to
`POST /invoice-parser/api/extractions`, polls the returned job, and
displays the validated response on the same page beside the browser's native PDF
viewer. Uploads use the Prefect Secret passcode. Production dispatches
`invoice-extraction-prod`; `dev` extracts in-process. Uploaded documents switch
from an immediate local preview to a five-minute
URL for the persisted private object when extraction completes. Open
`/invoice-parser/presentation/` for the keyboard-driven talk, presenter notes,
slide overview, and live-demo handoff.

Run the sample PDFs configured in `labs/invoice_parser/scripts/extract.py`
through the managed development workflow with:

```bash
uv run python -m labs.invoice_parser.scripts.extract
```

## Contract

`start_invoice_extraction()` owns preflight. Production stages bytes and
dispatches `invoice-extraction-prod`. Development runs
`extract_invoice_document()` in-process. `process_document()` owns DocFirewall approval, conversion,
permanent object storage, exact-hash reuse, and document metadata, and returns the
retained parser output with the document.
`run_invoice_extraction()` sends `document.markdown` and fresh typed lookup state
to one named Pydantic AI agent with `InvoiceAgentOutput` as its output type. The
agent calls one read-only supplier lookup tool backed by the committed fake ERP
JSON dataset. A native usage limit caps the run at one tool call, while the output
validator requires that lookup and verifies the result against the deterministic
ERP candidates. The Agent allows three bounded tool retries and three bounded
output retries. The transient response includes `all_messages()` so the Lab can
show the actual prompt, tool exchange, retry feedback, and output beside the
document. Python owns every database write, timeout, acceptance rule, and error
response.
