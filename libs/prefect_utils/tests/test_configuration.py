"""Managed Prefect configuration tests."""

from pathlib import Path

import yaml


def test_prod_runtime_uses_versioned_managed_artifacts() -> None:
    """Managed bootstrap uses the exact provider-supported runtime contract."""
    configuration_path = Path(__file__).resolve().parents[3] / "prefect.yaml"
    configuration = yaml.safe_load(configuration_path.read_text())

    assert configuration["prefect-version"] == "3.8.3"
    clone_configuration = configuration["pull"][0]["prefect.deployments.steps.git_clone"]
    assert clone_configuration == {
        "id": "git-clone",
        "repository": "https://github.com/bnewman-tech/newman-labs.git",
        "commit_sha": "{{ $GITHUB_SHA }}",
    }

    deployments = configuration["deployments"]
    images = {deployment["work_pool"]["job_variables"]["image"] for deployment in deployments}
    assert images == {"prefecthq/prefect-client:3-python3.13"}
    assert {deployment["version"] for deployment in deployments} == {"{{ $GITHUB_SHA }}"}
    invoice_deployments = [deployment for deployment in deployments if deployment["name"].startswith("invoice-")]
    assert [deployment["name"] for deployment in invoice_deployments] == ["invoice-extraction-prod"]
    invoice_deployment = invoice_deployments[0]
    assert invoice_deployment["parameters"] == {"environment": "prod"}
    assert invoice_deployment["concurrency_limit"] == {
        "limit": 2,
        "collision_strategy": "CANCEL_NEW",
        "grace_period_seconds": 300,
    }

    install_script = configuration["pull"][1]["prefect.deployments.steps.run_shell_script"]["script"]
    assert "uv export --locked --no-dev" in install_script
    assert "uv pip install --system --torch-backend cpu" in install_script
