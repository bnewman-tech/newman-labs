"""Prefect deployment reconciliation."""

import asyncio
from pathlib import Path

import aiofiles
import prefect
import yaml
from prefect.client.orchestration import get_client
from prefect.client.schemas.schedules import CronSchedule
from prefect.flows import load_flow_from_entrypoint

from libs.prefect_utils.deployments.schemas import (
    PrefectConfiguration,
    PrefectDeploymentDefinition,
)

NEWMAN_LABS_DEPLOYMENT_TAG = "newman-labs"
PREFECT_CONFIGURATION_PATH = Path("prefect.yaml")
PREFECT_RELEASE_VERSION = "{{ $GITHUB_SHA }}"
PREFECT_MANAGED_IMAGE = "prefecthq/prefect-client:3-python3.13"


async def load_prefect_configuration(
    *,
    configuration_path: Path = PREFECT_CONFIGURATION_PATH,
) -> PrefectConfiguration:
    """Load and validate the committed Prefect deployment contract."""
    async with aiofiles.open(configuration_path) as file:
        configuration = PrefectConfiguration.model_validate(yaml.safe_load(await file.read()))
    if configuration.prefect_version != prefect.__version__:
        raise RuntimeError("prefect.yaml does not match the locked Prefect runtime version")
    if any(
        deployment.version != PREFECT_RELEASE_VERSION
        or deployment.work_pool.job_variables.image != PREFECT_MANAGED_IMAGE
        for deployment in configuration.deployments
    ):
        raise RuntimeError(
            "prefect.yaml deployments do not use the committed release version and managed runtime image"
        )
    return configuration


async def configured_prefect_deployments(
    *,
    configuration: PrefectConfiguration,
) -> dict[tuple[str, str], PrefectDeploymentDefinition]:
    """Resolve configured deployment keys and reject invalid ownership or duplicates."""
    configured_deployments = {}
    for deployment in configuration.deployments:
        if NEWMAN_LABS_DEPLOYMENT_TAG not in deployment.tags:
            raise ValueError(
                f"Prefect deployment {deployment.name!r} must include the {NEWMAN_LABS_DEPLOYMENT_TAG!r} ownership tag"
            )
        flow = await asyncio.to_thread(
            load_flow_from_entrypoint,
            deployment.entrypoint,
        )
        deployment_key = (flow.name, deployment.name)
        if deployment_key in configured_deployments:
            raise ValueError("prefect.yaml contains duplicate deployment definitions")
        configured_deployments[deployment_key] = deployment
    return configured_deployments


async def reconcile_prefect_deployments(
    *,
    configuration_path: Path = PREFECT_CONFIGURATION_PATH,
) -> tuple[list[str], list[str]]:
    """Delete owned deployments and schedules absent from prefect.yaml."""
    configuration = await load_prefect_configuration(configuration_path=configuration_path)
    configured_deployments = await configured_prefect_deployments(configuration=configuration)

    deleted_deployments = []
    deleted_schedules = []
    async with get_client() as client:
        for deployment in await client.read_deployments():
            if NEWMAN_LABS_DEPLOYMENT_TAG not in deployment.tags:
                continue
            flow = await client.read_flow(deployment.flow_id)
            deployment_key = (flow.name, deployment.name)
            configured_deployment = configured_deployments.get(deployment_key)
            if configured_deployment is None:
                await client.delete_deployment(deployment.id)
                deleted_deployments.append(f"{flow.name}/{deployment.name}")
                continue

            configured_schedules = {
                (schedule.cron, schedule.timezone, schedule.active) for schedule in configured_deployment.schedules
            }
            for schedule in deployment.schedules:
                current_schedule = schedule.schedule
                schedule_key = (
                    (
                        current_schedule.cron,
                        str(current_schedule.timezone),
                        schedule.active,
                    )
                    if isinstance(current_schedule, CronSchedule)
                    else None
                )
                if schedule_key in configured_schedules:
                    continue
                await client.delete_deployment_schedule(
                    deployment_id=deployment.id,
                    schedule_id=schedule.id,
                )
                deleted_schedules.append(f"{flow.name}/{deployment.name}:{schedule.slug or schedule.id}")

    return sorted(deleted_deployments), sorted(deleted_schedules)


async def verify_prefect_deployments(
    *,
    expected_version: str,
    configuration_path: Path = PREFECT_CONFIGURATION_PATH,
) -> None:
    """Assert live owned deployments exactly match the committed release."""
    configuration = await load_prefect_configuration(configuration_path=configuration_path)
    configured_deployments = await configured_prefect_deployments(configuration=configuration)
    live_deployments = {}
    async with get_client() as client:
        for deployment_summary in await client.read_deployments():
            if NEWMAN_LABS_DEPLOYMENT_TAG not in deployment_summary.tags:
                continue
            deployment = await client.read_deployment(deployment_summary.id)
            flow = await client.read_flow(deployment.flow_id)
            live_deployments[flow.name, deployment.name] = deployment

    if live_deployments.keys() != configured_deployments.keys():
        raise RuntimeError("Live Prefect deployments do not match prefect.yaml")

    for deployment_key, configured in configured_deployments.items():
        live = live_deployments[deployment_key]
        configured_schedules = {
            (schedule.cron, schedule.timezone, schedule.active) for schedule in configured.schedules
        }
        live_schedules = {
            (
                schedule.schedule.cron,
                str(schedule.schedule.timezone),
                schedule.active,
            )
            for schedule in live.schedules
            if isinstance(schedule.schedule, CronSchedule)
        }
        live_concurrency_limit = (
            live.global_concurrency_limit.limit if live.global_concurrency_limit else live.concurrency_limit
        )
        live_collision_strategy = (
            live.concurrency_options.collision_strategy.value if live.concurrency_options else None
        )
        live_grace_period_seconds = live.concurrency_options.grace_period_seconds if live.concurrency_options else None
        live_contract = (
            live.version,
            live.entrypoint,
            set(live.tags),
            live.parameters,
            live.work_queue_name,
            live.job_variables.get("image"),
            live_concurrency_limit,
            live_collision_strategy,
            live_grace_period_seconds,
            live_schedules,
        )
        configured_contract = (
            expected_version,
            configured.entrypoint,
            configured.tags,
            configured.parameters,
            configured.work_pool.work_queue_name,
            configured.work_pool.job_variables.image,
            configured.concurrency_limit.limit if configured.concurrency_limit else None,
            configured.concurrency_limit.collision_strategy if configured.concurrency_limit else None,
            configured.concurrency_limit.grace_period_seconds if configured.concurrency_limit else None,
            configured_schedules,
        )
        if live_contract != configured_contract:
            raise RuntimeError(
                f"Live Prefect deployment {deployment_key[0]}/{deployment_key[1]} does not match the committed release"
            )
