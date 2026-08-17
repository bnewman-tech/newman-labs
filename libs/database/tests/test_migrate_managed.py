"""Managed database migration preflight tests."""

from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from libs.core.dependencies import EnvironmentMode, settings
from libs.database.functions import DatabaseRole
from libs.database.scripts import migrate_managed


def _result(*, row: tuple[object, ...] | None = None, revisions: list[str] | None = None) -> MagicMock:
    result = MagicMock()
    if row is not None:
        result.one.return_value = row
    if revisions is not None:
        result.scalars.return_value.all.return_value = revisions
    return result


def _migration_runtime(
    monkeypatch: pytest.MonkeyPatch,
    *,
    results: list[MagicMock],
) -> tuple[AsyncMock, MagicMock]:
    connection = AsyncMock()
    connection.exec_driver_sql.side_effect = results
    engine = MagicMock()
    engine.begin.return_value.__aenter__.return_value = connection
    engine.dispose = AsyncMock()
    script_directory = MagicMock()
    script_directory.walk_revisions.return_value = [SimpleNamespace(revision="0001")]
    script_directory.get_current_head.return_value = "0001"
    monkeypatch.setattr(
        migrate_managed,
        "get_managed_database_url",
        AsyncMock(return_value=SecretStr("postgresql://newman/newman-labs")),
    )
    monkeypatch.setattr(migrate_managed, "create_database_engine", MagicMock(return_value=engine))
    monkeypatch.setattr(
        migrate_managed.ScriptDirectory,
        "from_config",
        MagicMock(return_value=script_directory),
    )
    return connection, engine


async def test_development_migration_selects_the_development_owner_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The release migrator cannot select a pooled or cross-environment URL."""
    get_database_url = AsyncMock(return_value=SecretStr("postgresql://newman/newman-labs"))
    monkeypatch.setattr(settings, "environment", EnvironmentMode.DEV)
    monkeypatch.setattr(
        migrate_managed,
        "get_managed_database_url",
        get_database_url,
    )
    monkeypatch.setattr(
        migrate_managed,
        "create_database_engine",
        MagicMock(side_effect=RuntimeError("stop after URL selection")),
    )

    with pytest.raises(RuntimeError, match="stop after URL selection"):
        await migrate_managed.migrate_managed_database()

    get_database_url.assert_awaited_once_with(
        environment=EnvironmentMode.DEV,
        role=DatabaseRole.OWNER,
    )


async def test_managed_migration_upgrades_a_known_revision_on_the_locked_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preflight, upgrade, and verification share one transaction and lock."""
    connection, engine = _migration_runtime(
        monkeypatch,
        results=[
            _result(row=(True, True, True, 2)),
            _result(revisions=["0001"]),
            _result(revisions=["0001"]),
        ],
    )

    await migrate_managed.migrate_managed_database()

    connection.run_sync.assert_awaited_once_with(
        migrate_managed.upgrade_to_head,
        configuration=ANY,
    )
    connection.execute.assert_awaited_once()
    engine.begin.assert_called_once_with()
    engine.dispose.assert_awaited_once_with()


async def test_managed_migration_bootstraps_a_blank_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicitly reset target can be recreated only when no app tables remain."""
    connection, _engine = _migration_runtime(
        monkeypatch,
        results=[
            _result(row=(False, False, False, 0)),
            _result(revisions=["0001"]),
        ],
    )

    await migrate_managed.migrate_managed_database()

    connection.run_sync.assert_awaited_once()


@pytest.mark.parametrize(
    ("state", "revisions"),
    [
        ((True, True, True, 2), ["discarded-revision"]),
        ((False, False, False, 1), None),
    ],
)
async def test_managed_migration_rejects_inconsistent_history(
    monkeypatch: pytest.MonkeyPatch,
    state: tuple[object, ...],
    revisions: list[str] | None,
) -> None:
    """Unknown history and unversioned application tables fail closed."""
    results = [_result(row=state)]
    if revisions is not None:
        results.append(_result(revisions=revisions))
    connection, engine = _migration_runtime(monkeypatch, results=results)

    with pytest.raises(RuntimeError, match="operator review"):
        await migrate_managed.migrate_managed_database()

    connection.run_sync.assert_not_awaited()
    engine.dispose.assert_awaited_once_with()


def test_upgrade_to_head_reuses_the_supplied_connection() -> None:
    """Alembic receives the connection already holding the migration lock."""
    connection = MagicMock()
    configuration = MagicMock()
    configuration.attributes = {}

    with patch.object(migrate_managed.command, "upgrade") as upgrade:
        migrate_managed.upgrade_to_head(
            connection,
            configuration=configuration,
        )

    assert configuration.attributes["connection"] is connection
    upgrade.assert_called_once_with(configuration, "head")
