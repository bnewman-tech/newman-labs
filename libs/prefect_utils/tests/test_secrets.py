"""Prefect Secret utility tests."""

from unittest.mock import AsyncMock, Mock

import pytest
from prefect.blocks.system import Secret

from libs.prefect_utils.secrets import (
    PrefectSecret,
    get_secret,
)


async def test_get_secret_loads_required_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Named Secret blocks return trimmed secret values."""
    secret = Mock()
    secret.get.return_value = "  newman-secret  "
    load_secret = AsyncMock(return_value=secret)
    monkeypatch.setattr(Secret, "aload", load_secret)

    value = await get_secret(name=PrefectSecret.OLLAMA_API_KEY)

    load_secret.assert_awaited_once_with(PrefectSecret.OLLAMA_API_KEY.value)
    assert value.get_secret_value() == "newman-secret"


async def test_get_secret_rejects_empty_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A configured but empty required block fails closed."""
    secret = Mock()
    secret.get.return_value = "  "
    monkeypatch.setattr(Secret, "aload", AsyncMock(return_value=secret))

    with pytest.raises(RuntimeError, match="ollama-api-key is empty"):
        await get_secret(name=PrefectSecret.OLLAMA_API_KEY)


async def test_get_secret_names_failed_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Startup errors identify the missing block without exposing a value."""
    monkeypatch.setattr(
        Secret,
        "aload",
        AsyncMock(side_effect=ValueError("not found")),
    )

    with pytest.raises(RuntimeError, match="newman-labs-logfire-token"):
        await get_secret(name=PrefectSecret.LOGFIRE_TOKEN)
