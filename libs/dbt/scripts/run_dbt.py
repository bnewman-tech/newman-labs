"""Run dbt Core using the typed application database settings."""

import asyncio
import sys

from libs.core.dependencies import settings
from libs.database.functions import (
    DatabaseRole,
    get_managed_database_url,
    get_test_database_url,
)
from libs.dbt.functions import run_dbt_command


async def main() -> int:
    """Execute the requested dbt command and forward its output."""
    arguments = sys.argv[1:]
    managed = bool(arguments and arguments[0] == "--managed")
    if managed:
        arguments = arguments[1:]
    if not arguments:
        raise RuntimeError("A dbt command is required")

    if managed:
        database_url = await get_managed_database_url(
            environment=settings.environment,
            role=DatabaseRole.OWNER,
        )
    else:
        database_url = get_test_database_url()

    result = await run_dbt_command(
        arguments=arguments,
        database_url=database_url,
    )
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(
            result.stderr,
            end="" if result.stderr.endswith("\n") else "\n",
            file=sys.stderr,
        )
    return result.return_code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
