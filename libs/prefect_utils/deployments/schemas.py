"""Typed contracts for committed Prefect deployment definitions."""

from typing import Literal

from pydantic import Field

from libs.core.pydantic_base import ExternalSourceModel


class PrefectCronSchedule(ExternalSourceModel):
    """One committed cron schedule."""

    cron: str = Field(min_length=1)
    timezone: str = Field(min_length=1)
    active: bool = True


class PrefectJobVariables(ExternalSourceModel):
    """Managed work-pool variables Newman Labs verifies after deployment."""

    image: str = Field(min_length=1)


class PrefectWorkPool(ExternalSourceModel):
    """Committed managed work-pool routing."""

    work_queue_name: str = Field(min_length=1)
    job_variables: PrefectJobVariables


class PrefectConcurrencyLimit(ExternalSourceModel):
    """Deployment-wide managed compute capacity policy."""

    limit: int = Field(gt=0)
    collision_strategy: Literal["CANCEL_NEW"]
    grace_period_seconds: int = Field(ge=60, le=86_400)


class PrefectDeploymentDefinition(ExternalSourceModel):
    """Fields required to reconcile one committed deployment."""

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    entrypoint: str = Field(min_length=1)
    tags: set[str] = Field(default_factory=set)
    parameters: dict[str, str] = Field(default_factory=dict)
    concurrency_limit: PrefectConcurrencyLimit | None = None
    schedules: list[PrefectCronSchedule] = Field(default_factory=list)
    work_pool: PrefectWorkPool


class PrefectConfiguration(ExternalSourceModel):
    """Deployment definitions read from prefect.yaml."""

    prefect_version: str = Field(alias="prefect-version", min_length=1)
    deployments: list[PrefectDeploymentDefinition] = Field(min_length=1)
