"""Shared Logfire runtime configuration."""

import asyncio
import logging
from threading import Event
from typing import Any, override

import logfire
from pydantic_ai import Embedder

from libs.core.dependencies import EnvironmentMode, settings
from libs.prefect_utils.secrets import PrefectSecret, get_secret

_LOGFIRE_CONFIGURED = Event()
_LOGFIRE_LOCK = asyncio.Lock()


class _LogfireExportHandler(logfire.LogfireLoggingHandler):
    """Send stdlib logs to Logfire without reprinting them on the console."""

    @override
    def fill_attributes(self, record: logging.LogRecord) -> dict[str, Any]:
        attributes = super().fill_attributes(record)
        attributes["logfire.disable_console_log"] = True
        return attributes


async def configure_logfire() -> None:
    """Configure shared telemetry once for the current process."""
    if _LOGFIRE_CONFIGURED.is_set():
        return

    async with _LOGFIRE_LOCK:
        if _LOGFIRE_CONFIGURED.is_set():
            return

        token = await get_secret(name=PrefectSecret.LOGFIRE_TOKEN)
        logfire.configure(
            service_name="newman-labs",
            environment=settings.environment.value,
            token=token.get_secret_value(),
            send_to_logfire=True,
            console=(
                logfire.ConsoleOptions(
                    colors="auto",
                    span_style="show-parents",
                    verbose=False,
                    show_project_link=False,
                )
                if settings.environment is EnvironmentMode.DEV
                else False
            ),
        )
        root_logger = logging.getLogger()
        if not any(isinstance(handler, logfire.LogfireLoggingHandler) for handler in root_logger.handlers):
            root_logger.addHandler(
                _LogfireExportHandler(
                    level=settings.log_level,
                    fallback=logging.NullHandler(),
                )
            )
        logfire.instrument_pydantic_ai(
            include_binary_content=True,
            include_content=True,
        )
        Embedder.instrument_all()
        logfire.instrument_httpx(capture_all=False)
        _LOGFIRE_CONFIGURED.set()
