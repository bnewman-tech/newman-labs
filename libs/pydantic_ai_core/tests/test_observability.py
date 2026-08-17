"""Tests for shared Pydantic AI observability."""

import asyncio
from collections.abc import Iterator
from unittest.mock import AsyncMock, Mock, patch

import pytest
from pydantic import SecretStr

from libs.core.dependencies import EnvironmentMode
from libs.prefect_utils.secrets import PrefectSecret
from libs.pydantic_ai_core import observability


@pytest.fixture(autouse=True)
def reset_logfire_configuration() -> Iterator[None]:
    """Keep process-wide Logfire state isolated between tests."""
    observability._LOGFIRE_CONFIGURED.clear()
    yield
    observability._LOGFIRE_CONFIGURED.clear()


async def test_configure_logfire_uses_managed_token_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every runtime configures full AI telemetry exactly once."""
    managed_value = "newman-test-value"
    get_secret = AsyncMock(return_value=SecretStr(managed_value))
    root_logger = Mock()
    root_logger.handlers = []
    monkeypatch.setattr(observability, "get_secret", get_secret)

    with (
        patch.object(observability.logfire, "configure") as configure,
        patch.object(observability, "_LogfireExportHandler") as handler,
        patch.object(observability.logfire, "instrument_pydantic_ai") as instrument_ai,
        patch.object(observability.logfire, "instrument_httpx") as instrument_httpx,
        patch.object(observability.Embedder, "instrument_all") as instrument_embeddings,
        patch.object(observability.logging, "getLogger", return_value=root_logger),
    ):
        await asyncio.gather(
            observability.configure_logfire(),
            observability.configure_logfire(),
        )

    get_secret.assert_awaited_once_with(name=PrefectSecret.LOGFIRE_TOKEN)
    configure.assert_called_once()
    assert configure.call_args.kwargs == {
        "service_name": "newman-labs",
        "environment": "dev",
        "token": managed_value,
        "send_to_logfire": True,
        "console": observability.logfire.ConsoleOptions(
            colors="auto",
            span_style="show-parents",
            verbose=False,
            show_project_link=False,
        ),
    }
    handler.assert_called_once()
    assert handler.call_args.kwargs["level"] == "INFO"
    assert isinstance(
        handler.call_args.kwargs["fallback"],
        observability.logging.NullHandler,
    )
    root_logger.addHandler.assert_called_once_with(handler.return_value)
    instrument_ai.assert_called_once_with(
        include_binary_content=True,
        include_content=True,
    )
    instrument_embeddings.assert_called_once_with()
    instrument_httpx.assert_called_once_with(capture_all=False)


async def test_configure_logfire_disables_console_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production logs stay machine-readable and do not render a span tree."""
    monkeypatch.setattr(
        observability.settings,
        "environment",
        EnvironmentMode.PROD,
    )
    monkeypatch.setattr(
        observability,
        "get_secret",
        AsyncMock(return_value=SecretStr("newman-test-value")),
    )

    with (
        patch.object(observability.logfire, "configure") as configure,
        patch.object(observability, "_LogfireExportHandler"),
        patch.object(observability.logfire, "instrument_pydantic_ai"),
        patch.object(observability.logfire, "instrument_httpx"),
        patch.object(observability.Embedder, "instrument_all"),
        patch.object(
            observability.logging,
            "getLogger",
            return_value=Mock(handlers=[]),
        ),
    ):
        await observability.configure_logfire()

    assert configure.call_args.kwargs["console"] is False


async def test_configure_logfire_preserves_an_existing_export_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeated runtime setup does not duplicate Logfire log export."""
    root_logger = Mock()
    root_logger.handlers = [observability.logfire.LogfireLoggingHandler(fallback=observability.logging.NullHandler())]
    monkeypatch.setattr(
        observability,
        "get_secret",
        AsyncMock(return_value=SecretStr("newman-test-value")),
    )

    with (
        patch.object(observability.logfire, "configure"),
        patch.object(observability.logfire, "instrument_pydantic_ai"),
        patch.object(observability.logfire, "instrument_httpx"),
        patch.object(observability.Embedder, "instrument_all"),
        patch.object(observability.logging, "getLogger", return_value=root_logger),
    ):
        await observability.configure_logfire()

    root_logger.addHandler.assert_not_called()


def test_logfire_export_handler_does_not_reprint_on_the_console() -> None:
    """Stdlib logs still reach Logfire, but the console span tree stays the only printer."""
    record = observability.logging.LogRecord(
        name="newman.test",
        level=observability.logging.INFO,
        pathname="newman.py",
        lineno=1,
        msg="newman reply",
        args=(),
        exc_info=None,
    )

    attributes = observability._LogfireExportHandler(
        fallback=observability.logging.NullHandler(),
    ).fill_attributes(record)

    assert attributes["logfire.disable_console_log"] is True
    assert attributes["code.function"] == record.funcName
