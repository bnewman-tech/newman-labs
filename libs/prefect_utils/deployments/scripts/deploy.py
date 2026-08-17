"""Reconcile and deploy committed Prefect definitions."""

import asyncio
import os

from libs.prefect_utils.deployments import (
    reconcile_prefect_deployments,
    verify_prefect_deployments,
)


async def deploy_prefect_definitions() -> None:
    """Hard-cut owned state, deploy prefect.yaml, and verify the live release."""
    expected_version = os.environ.get("GITHUB_SHA")
    if not expected_version:
        raise RuntimeError("GITHUB_SHA is required to deploy Prefect definitions")

    deleted_deployments, deleted_schedules = await reconcile_prefect_deployments()
    if deleted_deployments:
        print(f"Deleted stale Prefect deployments: {', '.join(deleted_deployments)}")
    if deleted_schedules:
        print(f"Deleted stale Prefect schedules: {', '.join(deleted_schedules)}")

    process = await asyncio.create_subprocess_exec(
        "prefect",
        "--no-prompt",
        "deploy",
        "--all",
    )
    if await process.wait() != 0:
        raise RuntimeError("Prefect deployment failed")
    await verify_prefect_deployments(expected_version=expected_version)


if __name__ == "__main__":
    asyncio.run(deploy_prefect_definitions())
