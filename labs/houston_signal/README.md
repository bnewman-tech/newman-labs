# Houston Signal

Houston Signal combines observed Houston 311 activity with a rolling 365-day
Emergency Center incident history. Prefect schedules both typed source ingests daily,
PostgreSQL commits source state and one audit row, dbt normalizes both sources into
`fact_houston_activity`, and FastAPI presents the overview, map, and pipeline status.

## Owned surfaces

```text
schemas.py                             Pydantic web-view contracts
services.py                            Typed database-backed view queries
integrations/houston_311/functions.py  ArcGIS extraction and source transformation
integrations/houston_311/schemas.py    Additive external-source Pydantic contracts
integrations/houston_311/scripts/      Source ingestion and Prefect entrypoint
integrations/houston_emergency_center/functions.py ArcGIS extraction and transformation
integrations/houston_emergency_center/schemas.py   Typed external and normalized contracts
integrations/houston_emergency_center/scripts/     Source ingestion and Prefect entrypoint
tests/                                 Lab service behavior
```

FastAPI routes and Jinja delivery live in `apps/labs`; this package owns the
Houston Signal services and integration behavior those routes call.

Business and pipeline measures come from committed PostgreSQL data. Prefect owns
schedules, retries, and runtime logs.

## Source limits

Houston 311 publishes open requests and only a recent window of closed requests.
Bootstrap retains everything the source currently exposes; incremental runs preserve
new and changed cases after that baseline. Older creation-date counts are therefore
not a complete historical ledger.

The Houston Emergency Center source is an active Fire and Police snapshot, not a
complete incident history. The integration retains each incident it observes for 365
days and marks it inactive after it disappears from a later successful snapshot.
Calls that open and close between source refreshes may never be observed.

The public map returns rounded one-kilometer 311 cells, not addresses, case numbers,
or exact coordinates. Emergency Center locations are not published. Houston Signal
is exploratory analysis and is not intended for emergency response or public-safety
decisions.

Source links, attribution, and map-use requirements live in
`docs/legal/houston-signal-data-attribution.md`.
