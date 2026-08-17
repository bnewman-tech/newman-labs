# Newman Labs

Newman Labs is a monorepo for small, inspectable data products served by one
FastAPI application. Each lab owns its services, integrations, schemas, and tests;
the application package owns FastAPI routes, Jinja templates, and static assets.

The published Labs are [Houston Signal](labs/houston_signal/README.md), which combines
Houston 311 activity with the Houston Emergency Center's active Fire and Police
incident feed, and [Invoice Parser](labs/invoice_parser/README.md), an in-development
document-intelligence Lab for secure intake and typed AI extraction.

## Structure

```text
apps/labs/                 FastAPI application and shared web shell
labs/houston_signal/       Houston Signal product and source integrations
labs/invoice_parser/       Invoice extraction agent and local fixtures
libs/core/                 Runtime dependencies, HTTP, logging, and Pydantic policy
libs/blob_storage/         S3-compatible private object CRUD
libs/database/             Reusable SQLAlchemy, Alembic, connections, and sessions
libs/dbt/                  Typed dbt process runner
libs/docling/              Local Docling PDF conversion
libs/document_intelligence/ Intake, reuse, chunks, embeddings, and retention
libs/prefect_utils/        Prefect deployment, Secret, and Variable utilities
libs/pydantic_ai_core/     Typed Ollama, OpenAI/Google Gateway, embeddings, and AI telemetry
analytics/                 Newman Labs dbt project
brand/                     Shared design contract and assets
```

Imports point inward: `apps -> labs -> libs`. See the
[architecture guide](docs/architecture/project-structure.md) for package ownership
and database schema boundaries.

## Local development

Requires Python 3.13, uv, Prefect Cloud access, and the persistent Neon development
branch.

```bash
uv sync --locked --all-groups
source .venv/bin/activate
uv run library-skills --all --yes
cp .env.example .env
uv run python -m libs.database.scripts.migrate_managed
uv run fastapi dev
uv run python -m libs.dbt.scripts.run_dbt --managed build
```

Open `http://127.0.0.1:8000/houston-signal/`. Manual workflows and verification are
documented in [development](docs/operations/development.md).

## Data pipelines

```bash
uv run python -m labs.houston_signal.integrations.houston_311.scripts.ingest
uv run python -m labs.houston_signal.integrations.houston_emergency_center.scripts.ingest
```

These commands perform live source and database I/O. Source behavior and coverage
limits are documented in the [Houston Signal README](labs/houston_signal/README.md).

## Operations

- [Deployment, Neon, and production safety](docs/operations/deployment.md)
- [Logfire observability](docs/operations/observability.md)
- [Houston Signal data attribution](docs/legal/houston-signal-data-attribution.md)

`prefect.yaml` is the managed deployment source of truth. Prefect Secret blocks
hold application credentials, and each database, storage, observability, or AI
boundary loads only the credential it consumes. The local `.env` contains only
`PREFECT_API_URL` and `PREFECT_API_KEY`.

## Verification

```bash
uv run ruff format --check .
uv run ruff check .
uv run ty check --error all
uv run pytest -m "not integration"
uv run alembic check
uv run python -m libs.dbt.scripts.run_dbt build
```

Houston Signal is independent of the City of Houston and is not intended for
emergency response, public-safety decisions, damage verification, insurance
decisions, or outreach to affected residents.
