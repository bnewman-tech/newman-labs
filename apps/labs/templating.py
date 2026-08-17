"""Shared Jinja environment for the Newman Labs web application."""

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from apps.labs.catalog import LABS
from libs.core.dependencies import EnvironmentMode, settings

APP_DIRECTORY = Path(__file__).resolve().parent
STATIC_DIRECTORY = APP_DIRECTORY / "static"
ASSET_VERSION = sha256(
    b"".join(
        path.read_bytes()
        for path in (
            STATIC_DIRECTORY / "css" / "site.css",
            STATIC_DIRECTORY / "css" / "invoice-parser.css",
            STATIC_DIRECTORY / "css" / "invoice-presentation.css",
            STATIC_DIRECTORY / "js" / "site.js",
            STATIC_DIRECTORY / "js" / "houston-signal.js",
            STATIC_DIRECTORY / "js" / "invoice-parser.js",
            STATIC_DIRECTORY / "js" / "invoice-presentation.js",
        )
    )
).hexdigest()[:12]


def shared_template_context(_request: Request) -> dict[str, object]:
    """Return values available to every Newman Labs page."""
    return {
        "asset_version": ASSET_VERSION,
        "cloudflare_web_analytics_site_id": (
            settings.cloudflare_web_analytics_site_id if settings.environment is EnvironmentMode.PROD else None
        ),
        "current_year": datetime.now(tz=UTC).year,
        "labs": LABS,
    }


templates = Jinja2Templates(
    directory=APP_DIRECTORY / "templates",
    context_processors=[shared_template_context],
)
