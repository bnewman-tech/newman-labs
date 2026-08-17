# Deployment

## Environments

Newman Labs uses two retained Neon branches:

- `development` for development application and data work;
- `production` for the public application and scheduled ingests.

Each branch owns its PostgreSQL data, compute endpoints, private object-storage
state, and branch-scoped credentials. Neon branches do not merge data back into
their parent. Git, Alembic, dbt, and `prefect.yaml` remain the deployment sources
of truth.

Each environment stores two complete Neon credential URLs in Prefect, both using
the committed direct endpoint. The database library loads the selected URL and
rejects it unless its environment host, database, role, and TLS mode match. It
then performs the only routing transform: the web role moves to the corresponding
pooled endpoint. Alembic, dbt, asyncpg ingestion, retention, and transaction locks
use `neondb_owner` on the direct endpoint. FastAPI uses `newman_labs_web` on the
pooled endpoint.

FastAPI's SQLAlchemy session is request-scoped. Exiting the dependency closes the
session and returns its connection to the local pool; application shutdown disposes
that pool. Neon's pooled endpoint then returns the server connection after each
transaction.

Create `newman_labs_web` through SQL on each retained branch with login enabled
and writable transactions. Neon roles created through its Console, CLI, or API
inherit `neon_superuser` and are not suitable for the public runtime. Alembic owns
the role's object grants because resetting or replacing schemas and tables removes
those grants. The role can select only Houston Signal's published facts and
ingestion status. Invoice Parser adds `SELECT` and `INSERT` on retained documents
and parses plus `SELECT` on chunks for exact-document reuse.
It cannot write raw Houston data, orchestration state, analytics models, or delete
retained documents. The document-retention flow continues to use the owner role.
Default privileges preserve Houston mart access when dbt replaces its views. The
four database blocks are `neon-database-dev-direct-url`,
`neon-database-dev-web-url`, `neon-database-prod-direct-url`, and
`neon-database-prod-web-url`. Replace a block atomically when rotating a role or
changing an endpoint; never assemble a managed URL from independently updated
secret fragments.

Neon Object Storage is private and S3-compatible. Object keys use domain paths
such as `documents/<document-id>/original.pdf`; prefixes are organization, not
security boundaries. Branching provides environment isolation. Presigned download
URLs expire after five minutes and are never persisted as object identity.

## Change lifecycle

Open a pull request into `main`. The PR Checker runs formatting, linting, type
checking, dependency auditing, Alembic, dbt, tests, and migration reversibility
against disposable PostgreSQL.

Merging does not deploy. Publishing a non-prerelease GitHub release with a `v*`
tag on `main` runs the production workflow in this order:

1. apply forward-only Alembic migrations;
2. build and test dbt;
3. validate `prefect.yaml`, delete retired owned Prefect state, deploy every
   committed definition, and verify the live version, image, parameters, tags,
   queue, and schedules;
4. deploy FastAPI Cloud;
5. verify the public health, lab, data, and asset paths.

The protected GitHub `prod` environment contains only release control-plane
credentials. FastAPI Cloud contains `ENVIRONMENT=prod` plus the Prefect bootstrap
URL and key. Application credentials remain in named Prefect Secret blocks.
The production web process loads `newman-labs-invoice-parser-passcode` at startup
and retains only a derived token. The raw upload passcode is not stored in Git,
FastAPI Cloud, logs, cookies, or browser URLs.

## Production safety

Production is live once a production schedule is enabled or its database or object
store retains application data. After that boundary:

- never reset, downgrade, stamp, or rewrite an applied production migration;
- use corrective forward migrations;
- test schema changes on an isolated branch before release;
- keep the production database and object store private;
- protect the Neon production branch when the account plan supports it.

For recovery, disable affected schedules, restore into a new Neon branch, apply
and validate Alembic and dbt there, verify representative reads, then cut over the
approved endpoint and rotate its managed credential. Never treat a Neon branch as
a substitute for reviewed migration code.
