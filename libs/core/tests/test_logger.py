"""Tests for application logging."""

import logging
import os
import warnings

import pytest
from rich.logging import RichHandler

from libs.core.logger import configure_ml_library_logging, get_logger


def test_configure_ml_library_logging_suppresses_dependency_noise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ML dependency warnings and progress bars stay out of application output."""
    logger_names = (
        "docling",
        "docling_core",
        "huggingface_hub",
        "sentence_transformers",
        "torch._dynamo",
        "transformers",
    )
    original_levels = {name: logging.getLogger(name).level for name in logger_names}
    for environment_name in (
        "HF_HUB_DISABLE_PROGRESS_BARS",
        "HF_HUB_VERBOSITY",
        "TRANSFORMERS_NO_ADVISORY_WARNINGS",
        "TRANSFORMERS_VERBOSITY",
    ):
        monkeypatch.delenv(environment_name, raising=False)

    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            configure_ml_library_logging()
            warnings.warn_explicit(
                "Using padding='same' with even kernel lengths and odd dilation "
                "may require a zero-padded copy of the input be created",
                UserWarning,
                filename="conv.py",
                lineno=560,
                module="torch.nn.modules.conv",
            )

        assert os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] == "1"
        assert os.environ["HF_HUB_VERBOSITY"] == "error"
        assert os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] == "1"
        assert os.environ["TRANSFORMERS_VERBOSITY"] == "error"
        assert all(logging.getLogger(name).level == logging.ERROR for name in logger_names)
        assert caught == []
    finally:
        for name, level in original_levels.items():
            logging.getLogger(name).setLevel(level)


def test_get_logger_uses_rich_console_when_unconfigured() -> None:
    """The first logger installs a Rich handler with color and traceback columns."""
    root_logger = logging.getLogger()
    existing_handlers = list(root_logger.handlers)
    root_logger.handlers.clear()
    try:
        logger = get_logger("newman.test.logger")

        assert logger.name == "newman.test.logger"
        assert any(isinstance(handler, RichHandler) for handler in root_logger.handlers)
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("httpcore").level == logging.WARNING
    finally:
        root_logger.handlers[:] = existing_handlers


def test_get_logger_keeps_an_existing_console_handler() -> None:
    """Later callers do not replace a handler already attached to the root logger."""
    root_logger = logging.getLogger()
    existing = logging.NullHandler()
    root_logger.addHandler(existing)
    handlers_before = list(root_logger.handlers)
    try:
        get_logger("newman.test.existing-logger")

        assert root_logger.handlers == handlers_before
    finally:
        root_logger.removeHandler(existing)
