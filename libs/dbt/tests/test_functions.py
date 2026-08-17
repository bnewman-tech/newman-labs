"""dbt process environment and lifecycle tests."""

import asyncio
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr

from libs.dbt.functions import database_environment, run_dbt_command


def test_database_url_translates_to_dbt_postgres_environment() -> None:
    """Local and managed runtimes share one typed database URL boundary."""
    environment = database_environment(
        database_url=SecretStr(
            "postgresql+asyncpg://newman_user:newman_password@db.example:6543/"
            "newman_db?sslmode=require&channel_binding=require"
        )
    )

    assert environment == {
        "PGHOST": "db.example",
        "PGPORT": "6543",
        "PGUSER": "newman_user",
        "PGPASSWORD": "newman_password",
        "PGDATABASE": "newman_db",
        "PGSSLMODE": "require",
    }


@pytest.mark.asyncio
async def test_cancellation_terminates_the_dbt_child_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cancelled flow does not leave an unmanaged dbt process running."""
    communicating = asyncio.Event()
    profiles_dir: Path | None = None

    class WaitingProcess:
        returncode: int | None = None
        terminated = False

        async def communicate(self) -> tuple[bytes, bytes]:
            communicating.set()
            await asyncio.Event().wait()
            return b"", b""

        def terminate(self) -> None:
            self.terminated = True
            self.returncode = -15

        def kill(self) -> None:
            self.returncode = -9

        async def wait(self) -> int:
            return self.returncode or 0

    process = WaitingProcess()

    async def create_process(*args: Any, **kwargs: Any) -> WaitingProcess:
        nonlocal profiles_dir
        profiles_dir = Path(args[args.index("--profiles-dir") + 1])
        profile_text = await asyncio.to_thread(
            (profiles_dir / "profiles.yml").read_text,
            encoding="utf-8",
        )
        assert profile_text.startswith("newman_labs:\n")
        del kwargs
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)
    task = asyncio.create_task(
        run_dbt_command(
            arguments=["build", "--select", "tag:newman_demo"],
            database_url=SecretStr("postgresql+asyncpg://postgres:postgres@localhost/newman"),
        )
    )
    await communicating.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert process.terminated is True
    assert profiles_dir is not None
    assert not await asyncio.to_thread(profiles_dir.exists)
