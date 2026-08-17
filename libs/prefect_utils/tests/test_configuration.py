"""Managed Prefect configuration tests."""

from pathlib import Path

import yaml


def test_prod_runtime_uses_versioned_managed_artifacts() -> None:
    """Managed bootstrap uses the exact provider-supported runtime contract."""
    configuration_path = Path(__file__).resolve().parents[3] / "prefect.yaml"
    configuration = yaml.safe_load(configuration_path.read_text())

    token_script = configuration["pull"][0]["prefect.deployments.steps.run_shell_script"]["script"]
    assert "--from prefect-cloud==0.1.13" in token_script
    assert configuration["prefect-version"] == "3.8.3"

    deployments = configuration["deployments"]
    images = {deployment["work_pool"]["job_variables"]["image"] for deployment in deployments}
    assert images == {"prefecthq/prefect-client:3-python3.13"}
    assert {deployment["version"] for deployment in deployments} == {"{{ $GITHUB_SHA }}"}
    invoice_deployments = [deployment for deployment in deployments if deployment["name"].startswith("invoice-")]
    assert {deployment["concurrency_limit"]["collision_strategy"] for deployment in invoice_deployments} == {
        "CANCEL_NEW"
    }
    assert {deployment["concurrency_limit"]["limit"] for deployment in invoice_deployments} == {1, 2}

    install_script = configuration["pull"][2]["prefect.deployments.steps.run_shell_script"]["script"]
    assert "uv export --locked --no-dev" in install_script
    assert "uv pip install --system --torch-backend cpu" in install_script
    assert "uv==0.12.5" in token_script
