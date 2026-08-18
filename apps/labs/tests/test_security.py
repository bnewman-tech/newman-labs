"""Application security policy tests."""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import SecretStr

from apps.labs import main
from apps.labs.main import app, lifespan
from apps.labs.security import RequestBodyLimitMiddleware, create_passcode_token
from libs.core.dependencies import EnvironmentMode, settings
from libs.database.functions import DatabaseRole


async def test_application_rejects_unknown_hosts() -> None:
    """Untrusted Host headers cannot influence generated absolute URLs."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://untrusted.example",
    ) as client:
        response = await client.get("/health/live")

    assert response.status_code == 400


async def test_application_sets_browser_security_headers() -> None:
    """Every response carries the shared browser hardening policy."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/live")

    assert response.headers["content-security-policy"] == ("base-uri 'self'; frame-ancestors 'none'; object-src 'none'")
    assert response.headers["permissions-policy"] == ("camera=(), geolocation=(), microphone=()")
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "strict-transport-security" not in response.headers


async def test_public_demo_pdfs_allow_same_origin_viewer() -> None:
    """Committed demo PDFs can render in the Lab's native browser frame."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/static/demos/invoice-supplier-match.pdf")

    assert response.status_code == 200
    assert response.headers["content-security-policy"] == ("base-uri 'self'; frame-ancestors 'self'; object-src 'none'")
    assert "x-frame-options" not in response.headers


async def test_production_application_sets_hsts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The HTTPS deployment instructs browsers to retain secure transport."""
    monkeypatch.setattr(settings, "environment", EnvironmentMode.PROD)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
        response = await client.get("/health/live")

    assert response.headers["strict-transport-security"] == ("max-age=31536000; includeSubDomains")


async def test_development_startup_loads_and_releases_the_managed_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Development startup uses the attested pooled web URL."""
    pooled_database_url = SecretStr("postgresql://newman_labs_web:newman-secret@ep-dev-pooler.example/newman-labs")
    api_engine = Mock()
    configure_logfire = AsyncMock()
    route_database = AsyncMock(return_value=pooled_database_url)
    create_pool = Mock(return_value=api_engine)
    dispose_pool = AsyncMock()
    shutdown_security = Mock()
    instrument_database = Mock()
    instrument_web = Mock()
    load_secret = AsyncMock(return_value=SecretStr("newman-test-passcode"))

    monkeypatch.setattr(settings, "environment", EnvironmentMode.DEV)
    monkeypatch.setattr(main, "configure_logfire", configure_logfire)
    monkeypatch.setattr(main, "get_managed_database_url", route_database)
    monkeypatch.setattr(main, "get_api_db_engine", create_pool)
    monkeypatch.setattr(main, "dispose_api_engine", dispose_pool)
    monkeypatch.setattr(main, "shutdown_document_security", shutdown_security)
    monkeypatch.setattr(main, "get_secret", load_secret)
    monkeypatch.setattr(main.logfire, "instrument_sqlalchemy", instrument_database)
    monkeypatch.setattr(main.logfire, "instrument_fastapi", instrument_web)

    with pytest.raises(RuntimeError, match="request failed"):
        async with lifespan(app):
            raise RuntimeError("request failed")

    configure_logfire.assert_awaited_once_with()
    route_database.assert_awaited_once_with(
        environment=EnvironmentMode.DEV,
        role=DatabaseRole.WEB,
    )
    create_pool.assert_called_once_with(database_url=pooled_database_url)
    instrument_database.assert_called_once_with(engine=api_engine)
    instrument_web.assert_called_once_with(
        app,
        capture_headers=False,
        excluded_urls="/health/live",
    )
    dispose_pool.assert_awaited_once_with()
    shutdown_security.assert_called_once_with()
    load_secret.assert_awaited_once_with(name=main.PrefectSecret.INVOICE_PARSER_PASSCODE)
    assert app.state.invoice_parser_access_token == create_passcode_token(passcode="newman-test-passcode")


async def test_production_startup_initializes_the_managed_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production startup uses and instruments the attested database."""
    pooled_database_url = SecretStr("postgresql://newman_labs_web:newman-secret@ep-prod-pooler.example/newman-labs")
    api_engine = Mock()
    configure_logfire = AsyncMock()
    route_database = AsyncMock(return_value=pooled_database_url)
    create_pool = Mock(return_value=api_engine)
    instrument_database = Mock()
    instrument_web = Mock()
    load_secret = AsyncMock(return_value=SecretStr("newman-test-passcode"))

    monkeypatch.setattr(settings, "environment", EnvironmentMode.PROD)
    monkeypatch.setattr(main, "configure_logfire", configure_logfire)
    monkeypatch.setattr(main, "get_managed_database_url", route_database)
    monkeypatch.setattr(main, "get_api_db_engine", create_pool)
    monkeypatch.setattr(main, "dispose_api_engine", AsyncMock())
    monkeypatch.setattr(main, "get_secret", load_secret)
    monkeypatch.setattr(main.logfire, "instrument_sqlalchemy", instrument_database)
    monkeypatch.setattr(main.logfire, "instrument_fastapi", instrument_web)

    async with lifespan(app):
        pass

    configure_logfire.assert_awaited_once_with()
    route_database.assert_awaited_once_with(
        environment=EnvironmentMode.PROD,
        role=DatabaseRole.WEB,
    )
    create_pool.assert_called_once_with(database_url=pooled_database_url)
    instrument_database.assert_called_once_with(engine=api_engine)
    instrument_web.assert_called_once_with(
        app,
        capture_headers=False,
        excluded_urls="/health/live",
    )
    load_secret.assert_awaited_once_with(name=main.PrefectSecret.INVOICE_PARSER_PASSCODE)
    assert app.state.invoice_parser_access_token == create_passcode_token(passcode="newman-test-passcode")


async def test_request_body_limit_rejects_declared_oversize_before_routing() -> None:
    """Oversized multipart requests fail before FastAPI parses an upload."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/invoice-parser/api/extractions",
            content=b"",
            headers={"Content-Length": str(main.MAX_REQUEST_BODY_BYTES + 1)},
        )

    assert response.status_code == 413
    assert response.json() == {"detail": "The request body is too large."}


async def test_request_body_limit_rejects_oversize_chunked_content() -> None:
    """Streaming clients cannot bypass the limit by omitting Content-Length."""
    downstream = FastAPI()

    @downstream.post("/")
    async def read_request(request: Request) -> JSONResponse:
        """Return only after the downstream handler consumes the body."""
        return JSONResponse({"size": len(await request.body())})

    async def request_chunks() -> AsyncIterator[bytes]:  # ruff: ignore[unused-async] - HTTPX requires async chunks.
        """Yield a body larger than the small test boundary."""
        yield b"new"
        yield b"man"

    limited_application = RequestBodyLimitMiddleware(downstream, max_body_bytes=5)
    transport = httpx.ASGITransport(app=limited_application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/", content=request_chunks())

    assert response.status_code == 413
