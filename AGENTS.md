# Repository guidance

Build Newman Labs as public-facing engineering work: simple enough to understand,
strong enough to defend, and documented well enough that an outside engineer can
trace every important decision.

## Working standard

- Make it work, prove it, then simplify it.
- Engineer to zero: leave code clear, typed, tested, documented, and handoff-ready.
- Prefer cohesive functions that read top-to-bottom over helper layers that make
  readers jump around.
- Inline tiny one-use helpers, wrappers, and constants unless a name carries real
  domain meaning or extraction adds reuse, policy, testability, or clarity.
- Before production activation, make hard cutovers: replace and delete the old
  contract in the same change. Do not add compatibility routes, aliases, shims,
  dual writes, fallback imports, or migration bridges.
- Production is live as soon as a production schedule is enabled or the production
  database or object store retains application data. From that point forward,
  migrations are forward-only: never reset, downgrade, stamp, rewrite an applied
  revision, or delete retained data outside an explicit reviewed retention path.
  Recover with a corrective migration or a provider restore into an isolated
  branch, validate it, and then cut over deliberately.
- Read docs/architecture/project-structure.md before changing package ownership.
- Read brand/DESIGN.md before visual, logo, icon, image, or social work.

## Public readability

Write for an outside engineer with no private context.

- Names state the contract; comments explain why, risk, source quirks, or
  non-obvious policy.
- Docstrings describe public behavior and important failure modes. Do not narrate
  obvious code.
- Documentation must match implemented behavior. Do not add marketing language,
  invented scale claims, placeholder architecture, or AI-generated filler.
- Preserve proven non-obvious findings in a focused test, nearby why comment,
  lab README, or architecture decision; remove the experimental code.
- Keep READMEs short and navigational. Put durable product requirements in the
  lab README and cross-cutting decisions in docs/architecture or docs/decisions.

## Ownership

Imports point inward:

    apps -> labs -> libs

- apps/labs is the FastAPI composition root. It owns lifecycle, routes, Jinja
  templates, static assets, health, common errors, Logfire startup, and explicit
  router registration.
- Use module-level `APIRouter` objects and direct `include_router()` composition.
  Do not create router factories solely to pass shared application objects.
- labs/<lab> owns product services, schemas, integrations, agents, evals, and
  domain tests. FastAPI delivery remains in apps/labs.
- libs/core/dependencies.py is the single environment-backed configuration source for
  the application and managed flows. `.env` is local-only; deployed environments
  inject their own values and secrets.
- `ENVIRONMENT` accepts only `dev` and `prod`. Do not add aliases, intermediate
  environments, or compatibility values.
- Keep fixed library policy as named constants beside the owning implementation.
  Central settings are for values that genuinely vary by environment or deployment;
  callers must not pass internal library limits through unrelated layers.
- libs owns a true platform boundary or reuse proven by at least two consumers.
- Libraries never import a lab; labs never import each other.
- Keep short route-specific orchestration in the route. Add a service only when
  it owns a database query, persisted workflow, or meaningful multi-step use case.
- Do not add generic CRUD, repository, agent, parser, queue, plugin, or provider
  frameworks.

## Library structure

Newman Labs uses Brian Newman's proven integration-library shape at a deliberately
small public scale. The repository must stand on its own without private context.

- A standalone capability normally uses `functions.py`, `schemas.py`, `scripts/`,
  and `tests/`. Add `auth.py` or `settings.py` only when that capability actually
  owns authentication or configurable policy.
- Put callable behavior in `functions.py`. Do not use vague module names such as
  `helpers.py`, `utils.py`, `manager.py`, or `provider.py` when the code is simply
  the library's public functions.
- Keep fixed endpoints, page sizes, model names, retry limits, and other library
  policy inside the owning package. Use a local `settings.py` when several modules
  share the policy; otherwise keep named constants at the top of `functions.py`.
- Use `libs/core/dependencies.py` only for values supplied by the runtime or
  deployment environment. It must not become an inventory of every library's
  constants.
- Database code uses `crud/`, `models/`, and `schemas/` packages. CRUD modules own
  explicit persistence operations; do not add a generic CRUD base or repository
  abstraction.
- Prefect utilities use responsibility subpackages such as `secrets/` and
  `variables/`, each with direct functions. Domain flows remain in the integration
  or workflow package they orchestrate.
- Preserve independently meaningful operations as callable functions. Keep
  sequencing and branching in an explicit orchestrator, but do not create tiny
  pass-through wrappers solely to satisfy a layer diagram.

## Python contracts

- Use Python 3.13 and uv.
- Use async network, database, and object-storage I/O.
- Move synchronous CPU-heavy Docling work off the event loop with a bounded
  thread; do not describe a thread as durable background execution.
- Keep Docling concurrency permits tied to the actual thread lifetime. Request
  cancellation or timeout must not release capacity while parsing still runs.
- Use keyword-only arguments for new or changed functions except where a
  framework callback signature dictates otherwise.
- Prefer f-strings for runtime string construction and logging. Do not mix
  percent-style logging arguments into new or changed code.
- Do not add trivial properties, pass-through wrappers, or one-use helpers that
  hide a direct expression or function call.
- Prefer Pydantic models for domain/external boundaries and function outputs.
- Use NewmanLabsModel for internal contracts and ExternalSourceModel for
  additive third-party payloads.
- Reserve models modules and packages for SQLAlchemy. Put Pydantic contracts in
  schemas modules or domain-grouped schemas packages.
- Use enums for categorical values and explicit types instead of untyped
  dictionaries across service boundaries.
- Return None from integration functions when they fail to produce a meaningful
  value. Empty collections mean a successful empty result.

## Integrations

Use this lab-owned structure:

    labs/<lab>/integrations/<integration>/
    ├── functions.py
    ├── schemas.py
    ├── scripts/ingest.py
    └── tests/

Each public integration function owns authentication, request construction,
retry scope, pagination, parsing, source transforms, error logging, and its
failure sentinel. Keep the full HTTP contract readable in one place; do not hide
it behind a generic request wrapper.

Source-specific database reads, COPY columns, temporary tables, upserts,
watermarks, and retention rules live in `scripts/ingest.py` with the local and
Prefect entrypoint. Keep the process readable from fetch through commit and use
one generic ingestion audit row. dbt views are built during deployment and remain
current as source rows change.

## Data and persistence

- Database names ending in `_test` or `_verify` are the only disposable targets.
  Destructive migration-history operations must fail closed everywhere else.
- Production jobs must attest the committed Neon endpoint and database name before
  migrations, dbt, or ingestion can write.
- Use pooled SQLAlchemy sessions for FastAPI request work.
- Use short-lived asyncpg transactions and COPY for set-based ingestion.
- libs/database owns reusable connection and transaction lifecycle, request
  sessions, models, Alembic, shared persistence schemas, and generic ingestion
  audit writes. It does not own source-specific ingestion modules.
- SQLAlchemy models, Pydantic persistence schemas, Alembic, repositories, and
  reusable PostgreSQL interactions live under libs/database. Models map tables;
  schemas type repository inputs and outputs. Do not duplicate a table into a
  schema unless a real boundary consumes it.
- Do not add a generic CRUD base. Bulk ingestion and row-oriented workflow state
  are different paths.
- Use Polars for parsing/vectorized transforms, not synchronous database I/O.
- Put source-local normalization in dbt staging; downstream models consume the
  normalized contract.
- Store source-run outcomes in `orchestration.ingestion_run`; do not add per-source
  run tables or a custom dbt scheduler.

## Document and AI boundaries

- `libs/docling` owns the local Docling converter and returns Docling's native
  document model. Do not copy that provider setup into a Lab.
- `libs/blob_storage` owns typed create, read, update, and delete operations for
  private S3-compatible storage. Create and update use conditional writes.
- `libs/document_intelligence` owns intake validation, bounded conversion
  orchestration, normalized evidence, deterministic chunks, and embeddings.
- Document and workflow PostgreSQL persistence belongs to `libs/database`.
- Keep deterministic chunks separate from model-generated embeddings. One chunk
  may have multiple embedding rows identified by provider, model, and dimensions.
- Keep originals private under generated keys. Extracted content remains
  untrusted data and never becomes authorization, instructions, a command, or an
  unrestricted URL.
- `libs/pydantic_ai_core` owns typed provider construction, not lab agents or
  domain schemas.
- Each lab agent uses typed dependencies and structured output. The agent is a
  component, not the application.
- Python owns authorization, state transitions, database writes, and side effects.
- Newman Labs captures Pydantic AI prompts, results, tool content, and binary
  content in Logfire. A public upload screen must disclose storage, full
  telemetry, and the third-party services used by that Lab beside the upload
  action. Do not add a separate consent record. Never deliberately add credentials
  or authorization headers to telemetry.

## Prefect and secrets

- Prefect owns schedules, retries, run visibility, and orchestration; domain and
  database logic remain in their owning packages.
- prefect.yaml is the managed deployment source of truth.
- Every managed deployment carries the `newman-labs` ownership tag. The deployment
  entrypoint deletes owned Prefect deployments absent from `prefect.yaml` before
  applying the committed definitions; never leave retired deployments or schedules
  behind after a hard cutover.
- Lab source ingests run once daily unless the product requirement explicitly needs
  a more frequent observation interval.
- Prefect Secret blocks are the canonical credential store for managed flows and
  the production web application. FastAPI Cloud stores the environment marker
  plus the Prefect API URL and key needed to reach Prefect. Each managed boundary
  calls the shared Secret loader and passes the value directly into the connection,
  exporter, or provider it constructs. Never copy managed secrets into central
  settings or fetch them from arbitrary route logic.
- Never put secret values in workflow or deployment YAML.
- The protected GitHub production environment holds only release/control-plane
  credentials required by its workflows.

## Quality and tests

Required repository gates:

    uv run ruff format --check .
    uv run ruff check .
    uv run ty check --error all
    uv run pytest <focused path>

- Ruff selects ALL stable and preview rules. ty treats all rules as errors.
- Fix findings instead of adding broad ignores. Every suppression is narrow and
  explains the real framework or contract constraint.
- Add focused behavior and regression tests beside the owning surface.
- Mock external boundaries; use explicit live tests only when contract evidence
  requires them.
- Use lowercase newman for invented test data. Never use Codex in invented test
  names, fixtures, payloads, canaries, or artifacts.
- Never commit secrets, private documents, real invoices, or generated parser
  artifacts. .env is local; .env.example contains names and harmless placeholders.
- Run the focused checks, then run .agents/skills/simplify before calling
  implementation complete.
