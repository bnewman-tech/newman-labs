"""Application logging."""

import logging
import os
import warnings

from rich.logging import RichHandler

from libs.core.dependencies import settings


def configure_ml_library_logging() -> None:
    """Keep local ML dependencies quiet while preserving application logs."""
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("HF_HUB_VERBOSITY", "error")
    os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    for logger_name in (
        "docling",
        "docling_core",
        "huggingface_hub",
        "sentence_transformers",
        "torch._dynamo",
        "transformers",
    ):
        logging.getLogger(logger_name).setLevel(logging.ERROR)
    warnings.filterwarnings(
        "ignore",
        message=r"Using padding='same' with even kernel lengths and odd dilation may require a zero-padded copy.*",
        category=UserWarning,
        module=r"torch\.nn\.modules\.conv",
    )


def get_logger(name: str) -> logging.Logger:
    """Return a named logger using the application logging configuration."""
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.log_level)
    if not root_logger.handlers:
        logging.basicConfig(
            level=settings.log_level,
            format="%(message)s",
            datefmt="[%X]",
            handlers=[
                RichHandler(
                    rich_tracebacks=True,
                    show_path=True,
                    omit_repeated_times=True,
                )
            ],
        )
    # httpx logs full URLs at INFO, including Prefect secret-block paths.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    return logging.getLogger(name)
