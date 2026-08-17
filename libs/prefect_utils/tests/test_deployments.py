"""Prefect deployment reconciliation tests."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import aiofiles
import pytest
from prefect.client.schemas.objects import DeploymentSchedule
from prefect.client.schemas.schedules import CronSchedule

from libs.prefect_utils.deployments import functions
from libs.prefect_utils.deployments.scripts import deploy


async def test_reconcile_prefect_deployments_removes_owned_stale_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Reconciliation preserves current and unrelated workspace deployments."""
    configuration_path = tmp_path / "prefect.yaml"
    async with aiofiles.open(configuration_path, "w") as file:
        await file.write(
            """prefect-version: 3.8.3
deployments:
  - name: houston-311-daily-prod
    version: "{{ $GITHUB_SHA }}"
    entrypoint: package.py:houston_311_flow
    tags:
      - newman-labs
    schedules:
      - cron: "30 5 * * *"
        timezone: America/Chicago
        active: true
    work_pool:
      work_queue_name: default
      job_variables:
        image: prefecthq/prefect-client:3-python3.13
"""
        )

    current_id = UUID("00000000-0000-0000-0000-000000000001")
    stale_id = UUID("00000000-0000-0000-0000-000000000002")
    unrelated_id = UUID("00000000-0000-0000-0000-000000000003")
    current_flow_id = UUID("00000000-0000-0000-0000-000000000011")
    stale_flow_id = UUID("00000000-0000-0000-0000-000000000012")
    stale_schedule_id = UUID("00000000-0000-0000-0000-000000000021")
    current_schedule_id = UUID("00000000-0000-0000-0000-000000000022")
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.read_deployments.return_value = [
        SimpleNamespace(
            id=current_id,
            flow_id=current_flow_id,
            name="houston-311-daily-prod",
            tags=["newman-labs"],
            schedules=[
                DeploymentSchedule(
                    id=current_schedule_id,
                    deployment_id=current_id,
                    schedule=CronSchedule(
                        cron="30 5 * * *",
                        timezone="America/Chicago",
                    ),
                    active=True,
                ),
                DeploymentSchedule(
                    id=stale_schedule_id,
                    deployment_id=current_id,
                    schedule=CronSchedule(
                        cron="*/15 * * * *",
                        timezone="America/Chicago",
                    ),
                    active=True,
                ),
            ],
        ),
        SimpleNamespace(
            id=stale_id,
            flow_id=stale_flow_id,
            name="retired-production",
            tags=["newman-labs"],
        ),
        SimpleNamespace(
            id=unrelated_id,
            flow_id=UUID("00000000-0000-0000-0000-000000000013"),
            name="unrelated-production",
            tags=["another-project"],
        ),
    ]
    client.read_flow.side_effect = [
        SimpleNamespace(name="houston-signal-311-pipeline"),
        SimpleNamespace(name="retired-flow"),
    ]
    monkeypatch.setattr(functions, "get_client", lambda: client)
    monkeypatch.setattr(
        functions,
        "load_flow_from_entrypoint",
        Mock(return_value=SimpleNamespace(name="houston-signal-311-pipeline")),
    )

    (
        deleted_deployments,
        deleted_schedules,
    ) = await functions.reconcile_prefect_deployments(configuration_path=configuration_path)

    assert deleted_deployments == ["retired-flow/retired-production"]
    assert deleted_schedules == [f"houston-signal-311-pipeline/houston-311-daily-prod:{stale_schedule_id}"]
    client.delete_deployment.assert_awaited_once_with(stale_id)
    client.delete_deployment_schedule.assert_awaited_once_with(
        deployment_id=current_id,
        schedule_id=stale_schedule_id,
    )


async def test_verify_prefect_deployments_requires_the_exact_release_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Readback catches a stale version even when the deployment name matches."""
    configuration_path = tmp_path / "prefect.yaml"
    async with aiofiles.open(configuration_path, "w") as file:
        await file.write(
            """prefect-version: 3.8.3
deployments:
  - name: houston-311-daily-prod
    version: "{{ $GITHUB_SHA }}"
    entrypoint: package.py:houston_311_flow
    parameters:
      environment: prod
    tags:
      - newman-labs
      - prod
    schedules:
      - cron: "30 5 * * *"
        timezone: America/Chicago
        active: true
    work_pool:
      work_queue_name: default
      job_variables:
        image: prefecthq/prefect-client:3-python3.13
"""
        )

    deployment_id = UUID("00000000-0000-0000-0000-000000000031")
    flow_id = UUID("00000000-0000-0000-0000-000000000032")
    live_deployment = SimpleNamespace(
        id=deployment_id,
        flow_id=flow_id,
        name="houston-311-daily-prod",
        version="release-sha",
        entrypoint="package.py:houston_311_flow",
        tags=["newman-labs", "prod"],
        parameters={"environment": "prod"},
        work_queue_name="default",
        job_variables={"image": "prefecthq/prefect-client:3-python3.13"},
        concurrency_limit=None,
        global_concurrency_limit=None,
        concurrency_options=None,
        schedules=[
            DeploymentSchedule(
                deployment_id=deployment_id,
                schedule=CronSchedule(
                    cron="30 5 * * *",
                    timezone="America/Chicago",
                ),
                active=True,
            )
        ],
    )
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.read_deployments.return_value = [live_deployment]
    client.read_deployment.return_value = live_deployment
    client.read_flow.return_value = SimpleNamespace(name="houston-signal-311-pipeline")
    monkeypatch.setattr(functions, "get_client", lambda: client)
    monkeypatch.setattr(
        functions,
        "load_flow_from_entrypoint",
        Mock(return_value=SimpleNamespace(name="houston-signal-311-pipeline")),
    )

    await functions.verify_prefect_deployments(
        expected_version="release-sha",
        configuration_path=configuration_path,
    )

    live_deployment.version = "stale-sha"
    with pytest.raises(RuntimeError, match="does not match the committed release"):
        await functions.verify_prefect_deployments(
            expected_version="release-sha",
            configuration_path=configuration_path,
        )


async def test_deploy_prefect_definitions_cuts_over_then_verifies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retired owned state is removed before the release is applied and read back."""
    events = []

    def record_cleanup() -> tuple[list[str], list[str]]:
        events.append("cleanup")
        return [], []

    def record_deploy() -> int:
        events.append("deploy")
        return 0

    def record_verify(*, expected_version: str) -> None:
        assert expected_version == "release-sha"
        events.append("verify")

    cleanup = AsyncMock(side_effect=record_cleanup)
    process = AsyncMock()
    process.wait.side_effect = record_deploy
    create_subprocess = AsyncMock(return_value=process)
    verify = AsyncMock(side_effect=record_verify)
    monkeypatch.setenv("GITHUB_SHA", "release-sha")
    monkeypatch.setattr(deploy, "reconcile_prefect_deployments", cleanup)
    monkeypatch.setattr(deploy, "verify_prefect_deployments", verify)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_subprocess)

    await deploy.deploy_prefect_definitions()

    assert events == ["cleanup", "deploy", "verify"]
    cleanup.assert_awaited_once_with()
    create_subprocess.assert_awaited_once_with(
        "prefect",
        "--no-prompt",
        "deploy",
        "--all",
    )
    verify.assert_awaited_once_with(expected_version="release-sha")


async def test_deploy_prefect_definitions_does_not_verify_a_failed_deploy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A rejected deployment cannot be mistaken for a verified release."""
    cleanup = AsyncMock(return_value=([], []))
    verify = AsyncMock()
    process = AsyncMock()
    process.wait.return_value = 1
    monkeypatch.setenv("GITHUB_SHA", "release-sha")
    monkeypatch.setattr(deploy, "reconcile_prefect_deployments", cleanup)
    monkeypatch.setattr(deploy, "verify_prefect_deployments", verify)
    monkeypatch.setattr(
        asyncio,
        "create_subprocess_exec",
        AsyncMock(return_value=process),
    )

    with pytest.raises(RuntimeError, match="Prefect deployment failed"):
        await deploy.deploy_prefect_definitions()

    cleanup.assert_awaited_once_with()
    verify.assert_not_awaited()


async def test_deploy_prefect_definitions_requires_a_release_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every managed deployment is traceable to one immutable release commit."""
    monkeypatch.delenv("GITHUB_SHA", raising=False)

    with pytest.raises(RuntimeError, match="GITHUB_SHA is required"):
        await deploy.deploy_prefect_definitions()
