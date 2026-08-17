"""Application dependency tests."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from libs.core.dependencies import EnvironmentMode, Settings


def test_non_secret_runtime_configuration_has_typed_defaults() -> None:
    """Routine development behavior does not require dotenv configuration."""
    fields = Settings.model_fields

    assert set(fields) == {
        "cloudflare_web_analytics_site_id",
        "environment",
        "log_level",
    }
    assert fields["environment"].default is EnvironmentMode.DEV
    assert fields["log_level"].default == "INFO"


def test_empty_environment_values_keep_defaults_and_values_stay_validated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Blank deployment variables do not erase defaults or bypass validation."""
    monkeypatch.setenv("LOG_LEVEL", "")
    config = Settings(_env_file=None)

    assert config.log_level == "INFO"
    with pytest.raises(ValidationError):
        Settings.model_validate({"environment": "invalid"})


def test_dotenv_template_documents_external_configuration() -> None:
    """The committed dotenv contract lists required external configuration."""
    dotenv = Path(__file__).resolve().parents[3] / ".env.example"
    keys = {line.partition("=")[0] for line in dotenv.read_text().splitlines() if line and not line.startswith("#")}

    assert keys == {
        "PREFECT_API_KEY",
        "PREFECT_API_URL",
    }


def test_runtime_exposes_only_development_and_production() -> None:
    """The runtime contract exposes only dev and prod environments."""
    assert list(EnvironmentMode) == [
        EnvironmentMode.DEV,
        EnvironmentMode.PROD,
    ]
