"""Newman Labs FastAPI application entrypoint."""

import asyncio
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import logfire
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from apps.labs.errors import database_unavailable
from apps.labs.routes import (
    health,
    home,
    houston_signal,
    invoice_parser,
    lab_index,
    privacy,
)
from apps.labs.security import (
    ALLOWED_HOSTS,
    RequestBodyLimitMiddleware,
    add_security_headers,
    create_passcode_token,
)
from apps.labs.templating import STATIC_DIRECTORY
from libs.core.dependencies import EnvironmentMode, settings
from libs.database.functions import (
    DatabaseRole,
    dispose_api_engine,
    get_api_db_engine,
    get_managed_database_url,
)
from libs.docling.settings import PDF_MAX_FILE_SIZE_BYTES
from libs.document_intelligence.security import shutdown_document_security
from libs.prefect_utils.secrets.functions import PrefectSecret, get_secret
from libs.pydantic_ai_core.observability import configure_logfire

MAX_REQUEST_BODY_BYTES = PDF_MAX_FILE_SIZE_BYTES + 64 * 1024


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Validate managed configuration and release the pool on shutdown."""
    await configure_logfire()
    database_url = await get_managed_database_url(
        environment=settings.environment,
        role=DatabaseRole.WEB,
    )
    engine = get_api_db_engine(database_url=database_url)
    logfire.instrument_sqlalchemy(engine=engine)
    logfire.instrument_fastapi(
        _app,
        capture_headers=False,
        excluded_urls="/health/live",
    )
    if settings.environment is EnvironmentMode.PROD:
        access_passcode = await get_secret(name=PrefectSecret.INVOICE_PARSER_PASSCODE)
        _app.state.invoice_parser_access_token = create_passcode_token(passcode=access_passcode.get_secret_value())
    try:
        yield
    finally:
        try:
            await asyncio.to_thread(shutdown_document_security)
        finally:
            await dispose_api_engine()


app = FastAPI(title="Newman Labs", lifespan=lifespan)
app.state.invoice_parser_access_token = secrets.token_hex(32)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
app.add_middleware(GZipMiddleware, minimum_size=1_000, compresslevel=6)
app.add_middleware(RequestBodyLimitMiddleware, max_body_bytes=MAX_REQUEST_BODY_BYTES)
app.middleware("http")(add_security_headers)
app.add_exception_handler(SQLAlchemyError, database_unavailable)
app.mount(
    "/static",
    StaticFiles(directory=STATIC_DIRECTORY),
    name="static",
)
app.include_router(home.router)
app.include_router(lab_index.router)
app.include_router(privacy.router)
app.include_router(health.router)
app.include_router(houston_signal.router)
app.include_router(invoice_parser.router)
