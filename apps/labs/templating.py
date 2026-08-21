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
VERSIONED_ASSET_PATHS = (
    "/css/site.css",
    "/css/invoice-parser.css",
    "/css/invoice-presentation.css",
    "/js/site.js",
    "/js/houston-signal.js",
    "/js/invoice-parser.js",
    "/js/invoice-presentation.js",
    "/fonts/manrope-latin-wght-normal.woff2",
    "/fonts/newsreader-latin-wght-normal.woff2",
)
ASSET_VERSION = sha256(
    b"".join((STATIC_DIRECTORY / path.removeprefix("/")).read_bytes() for path in VERSIONED_ASSET_PATHS)
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
