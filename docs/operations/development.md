# Development

## Setup

Requirements:

- Python 3.13
- uv
- Prefect Cloud access
- the persistent Neon development branch

```bash
uv sync --locked --all-groups
source .venv/bin/activate
uv run library-skills --all --yes
cp .env.example .env
uv run python -m libs.database.scripts.migrate_managed
uv run python -m libs.dbt.scripts.run_dbt --managed build
uv run fastapi dev
```

The local `.env` contains only `PREFECT_API_URL` and `PREFECT_API_KEY`.
`ENVIRONMENT` defaults to `dev`. Open `http://127.0.0.1:8000/` and verify:

```bash
curl --fail http://127.0.0.1:8000/health/live
curl --fail http://127.0.0.1:8000/health/ready
```

The Invoice Parser upload page loads the processing access code from the Prefect
Secret `newman-labs-invoice-parser-passcode` and runs extraction in the FastAPI
process. It does not dispatch `invoice-extraction-prod`.

## Manual workflows

Run the Houston source ingests only when live source and development-database
writes are intended:

```bash
uv run python -m labs.houston_signal.integrations.houston_311.scripts.ingest
uv run python -m labs.houston_signal.integrations.houston_emergency_center.scripts.ingest
```

Place test PDFs in the ignored `libs/docling/artifacts/` directory to inspect local
Docling output:

```bash
uv run python -m libs.docling.scripts.convert_pdf
```

The live AI smoke matrix sends one paid request to every approved model. Each run
uses low reasoning and must call a function tool before returning validated invoice
output:

```bash
uv run python -m libs.pydantic_ai_core.scripts.smoke_model_matrix
```

## Quality

```bash
uv run ruff format --check .
uv run ruff check .
uv run ty check --error all
uv run pytest -m "not integration"
```

Integration tests require a disposable PostgreSQL database whose name ends in
`_test` or `_verify`. The PR Checker creates one, applies Alembic, builds dbt, runs
the full suite, and verifies migration reversibility. Never point integration tests,
Alembic downgrade, or Alembic stamp at a retained Neon database.
