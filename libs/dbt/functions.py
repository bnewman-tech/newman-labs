"""Asynchronous dbt Core process execution."""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy.engine import make_url

from libs.dbt.schemas import DBTCommandResult

if TYPE_CHECKING:
    from pydantic import SecretStr

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DBT_PROJECT_DIR = REPOSITORY_ROOT / "analytics"
DBT_PROFILE_TEMPLATE = DBT_PROJECT_DIR / "profiles.yml"


def database_environment(*, database_url: SecretStr) -> dict[str, str]:
    """Translate one SQLAlchemy URL into dbt-postgres environment variables."""
    url = make_url(database_url.get_secret_value())
    query = dict(url.query)
    sslmode = query.get("sslmode", "prefer")
    if isinstance(sslmode, tuple):
        sslmode = sslmode[0]

    return {
        "PGHOST": url.host or "localhost",
        "PGPORT": str(url.port or 5432),
        "PGUSER": url.username or "postgres",
        "PGPASSWORD": url.password or "",
        "PGDATABASE": url.database or "postgres",
        "PGSSLMODE": str(sslmode),
    }


async def run_dbt_command(
    *,
    arguments: list[str],
    database_url: SecretStr,
) -> DBTCommandResult:
    """Run dbt without blocking the event loop."""
    dbt_executable = Path(sys.executable).with_name("dbt")
    if not dbt_executable.exists():
        raise RuntimeError(f"dbt executable not found beside {sys.executable}")

    environment = os.environ.copy()
    environment.update(database_environment(database_url=database_url))
    with tempfile.TemporaryDirectory(prefix="newman-labs-dbt-") as profiles_dir:
        profile_path = Path(profiles_dir, "profiles.yml")
        await asyncio.to_thread(
            shutil.copyfile,
            DBT_PROFILE_TEMPLATE,
            profile_path,
        )
        process = await asyncio.create_subprocess_exec(
            str(dbt_executable),
            *arguments,
            "--project-dir",
            str(DBT_PROJECT_DIR),
            "--profiles-dir",
            profiles_dir,
            env=environment,
            cwd=REPOSITORY_ROOT,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = await process.communicate()
        except asyncio.CancelledError:
            with contextlib.suppress(ProcessLookupError):
                process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=10)
            except TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
                await process.wait()
            raise

    return DBTCommandResult(
        return_code=process.returncode or 0,
        stdout=stdout_bytes.decode(errors="replace"),
        stderr=stderr_bytes.decode(errors="replace"),
    )
