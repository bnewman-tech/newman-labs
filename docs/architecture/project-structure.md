# Newman Labs architecture

Newman Labs is a modular monolith: one repository, one FastAPI application, one
Neon database, and one dbt project.

```text
apps/labs/                    FastAPI composition, routes, templates, and assets
labs/houston_signal/          Houston Signal product and source integrations
labs/invoice_parser/          Invoice extraction agent and local fixtures
libs/blob_storage/            Private S3-compatible object operations
libs/core/                    Runtime settings, HTTP, logging, and Pydantic policy
libs/database/                SQLAlchemy, Alembic, CRUD, and audit writes
libs/dbt/                     Typed dbt runner
libs/docling/                 Local PDF conversion
libs/document_intelligence/   Document intake, parsing, retrieval, and retention
libs/prefect_utils/           Prefect deployments, Secrets, and Variables
libs/pydantic_ai_core/        Shared AI models, embeddings, and telemetry
analytics/                    Source staging and lab-owned marts
```

## Ownership

Imports point inward:

```text
apps -> labs -> libs
```

- `apps/labs` owns FastAPI lifecycle and delivery. It contains no lab business
  logic.
- A lab owns its services, integrations, schemas, agents, local fixtures, and domain
  tests. Labs never import one another.
- A library owns reusable infrastructure or behavior used across product
  boundaries. Libraries never import a lab.
- `analytics` normalizes source tables and builds lab-owned reporting models. It
  owns no application behavior.

Source integrations keep their complete contract together:

```text
labs/<lab>/integrations/<source>/
├── functions.py
├── schemas.py
├── scripts/ingest.py
└── tests/
```

The integration fetches and validates source data. Its ingest script owns
source-specific PostgreSQL writes and records the outcome in
`orchestration.ingestion_run`. Prefect schedules the script; dbt transforms the
committed source tables.

## Document intelligence

The document path is explicit:

```text
untrusted PDF
  -> format, size, and pinned YARA preflight
  -> private generated staging key
  -> Prefect Managed isolated execution
  -> DocFirewall scan
  -> exact-hash reuse lookup
  -> Docling parse
  -> basic extraction: private object storage and PostgreSQL
  -> indexed research: Docling chunks, model-specific embeddings, and persistence
```

`document_intelligence.document` records the upload, private original, and typed
security-scan snapshot, including the scanner name and runtime version.
`document_parse` records one parser and version plus private Markdown and Docling
JSON object references. Each parse owns its `document_chunk` rows; each chunk may
own multiple `document_embedding` rows for different embedding contracts.
Basic extraction stops after conversion. Callers opt into chunking and embeddings
only when the document must support indexed research or semantic search.
A saved converted document can be indexed later from its private Docling JSON
without uploading or parsing the PDF again. DenseOn is the local 768-dimension
default; `text-embedding-3-small` is available through Pydantic AI Gateway at
1,536 dimensions. Both models reuse the same deterministic Docling chunks and
persist separate vectors. Searches select one model contract and never compare
vectors produced by different models.

PostgreSQL stores lifecycle metadata, object references, searchable chunk text,
and vectors. Neon Object Storage stores the original PDF and full parser artifacts.
Exact SHA-256 reuse avoids repeated parsing. Failed persistence removes untracked
objects, and retention removes every private object before deleting its database
record.

Invoice Parser is a small consumer of the generic document path. FastAPI validates
the upload and applies the pinned YARA rules before writing a private generated
staging key. An unscheduled Prefect Managed deployment runs the memory-intensive
DocFirewall, Docling, persistence, and typed extraction workflow on isolated
compute. The browser polls the run and receives the result through a private
transient object that is deleted on delivery. The Lab does not persist an
invoice-specific analysis, history, or review record. Its agent has one read-only
tool that searches a committed fake ERP supplier dataset; the model cannot write
supplier state or resolve ambiguous candidates.

Format validation and the pinned raw-byte YARA rules run before private staging.
DocFirewall then runs on isolated managed compute before reuse, parsing, permanent
document storage, embeddings, or AI. `ALLOW` and review-only `FLAG` results create
the internal approved-document contract.
YARA matches, scanner errors, scanner timeouts, blocked content, and unscannable
files reject the upload. One bounded child process reuses the scanner and its Docling
worker between uploads; a timeout terminates that process and the next scan starts
cleanly. Newman Labs vendors DocFirewall 0.5.1's YARA file because that release's
published package omits the advertised asset and its binary-match formatter is
incompatible with `yara-python` 4.5. OCR image scanning remains
off until the deployed runtime provides and verifies the native Tesseract engine;
enabling only the Python wrapper would silently leave that scan unavailable.

Docling is synchronous and CPU-heavy, so conversion runs in a bounded thread. A
timeout or cancellation does not release its concurrency permit before the real
thread exits.

The public upload screen owns a concise notice beside the upload action. It links
to the privacy notice, names the third-party services used by that Lab, and warns
against prohibited content. The document pipeline does not persist a separate
consent record.

## Runtime boundaries

`libs/core/dependencies.py` contains only environment-backed settings. Fixed
library policy stays with its owning library. Prefect Secret blocks are canonical
for database, object-storage, Logfire, and AI-provider credentials; consumers load
their own credential when constructing the connection or client.

`apps/labs` applies bounded process-local per-client request limits before reading
request bodies. Health checks and static assets are exempt; expensive API paths
carry stricter policies. This is lightweight single-process abuse protection, not
a distributed quota or denial-of-service boundary.

FastAPI Cloud stores only `ENVIRONMENT`, `PREFECT_API_URL`, and
`PREFECT_API_KEY`. Supported environments are `dev` and `prod`.

Alembic owns the `raw`, `orchestration`, and `document_intelligence` schemas. dbt
owns `analytics_staging` and `analytics_<lab>` schemas. Application code reads dbt
relations but never creates them.
