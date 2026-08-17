"""Prefect Variable provisioning."""

from prefect.variables import Variable

SERVERLESS_WORK_POOL_VARIABLE = "serverless_work_pool_name"
SERVERLESS_WORK_POOL_NAME = "default-work-pool"


async def sync_prefect_variables() -> None:
    """Create or update variables required by Prefect deployments."""
    await Variable.aset(
        name=SERVERLESS_WORK_POOL_VARIABLE,
        value=SERVERLESS_WORK_POOL_NAME,
        tags=["newman-labs", "deployment"],
        overwrite=True,
    )


if __name__ == "__main__":
    import asyncio

    asyncio.run(sync_prefect_variables())
