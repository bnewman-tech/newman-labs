"""Application security policy."""

import hashlib
import hmac
from collections.abc import Awaitable, Callable
from uuid import UUID

from fastapi import Request, Response, status
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from libs.core.dependencies import EnvironmentMode, settings

ALLOWED_HOSTS = [
    "labs.briannewman.info",
    "*.fastapicloud.dev",
    "localhost",
    "127.0.0.1",
    "test",
    "testserver",
]


def create_passcode_token(*, passcode: str) -> str:
    """Derive an opaque comparison token without retaining the raw passcode."""
    return hmac.new(
        passcode.encode(),
        b"newman-labs-invoice-access-v1",
        hashlib.sha256,
    ).hexdigest()


def create_job_access_token(
    *,
    invoice_access_token: str,
    document_id: UUID,
    flow_run_id: UUID,
) -> str:
    """Bind polling authority to one document and managed flow run."""
    return hmac.new(
        invoice_access_token.encode(),
        f"{document_id}:{flow_run_id}".encode(),
        hashlib.sha256,
    ).hexdigest()


def has_valid_invoice_access(*, request: Request, passcode: str) -> bool:
    """Validate the invoice-processing passcode in constant time."""
    supplied_token = create_passcode_token(passcode=passcode)
    return hmac.compare_digest(
        supplied_token,
        request.app.state.invoice_parser_access_token,
    )


def has_valid_job_access(
    *,
    request: Request,
    document_id: UUID,
    flow_run_id: UUID,
    access_token: str,
) -> bool:
    """Validate a polling capability before any Prefect API request."""
    expected = create_job_access_token(
        invoice_access_token=request.app.state.invoice_parser_access_token,
        document_id=document_id,
        flow_run_id=flow_run_id,
    )
    return hmac.compare_digest(access_token, expected)


class RequestBodyLimitMiddleware:
    """Reject oversized HTTP bodies before form or multipart parsing."""

    def __init__(self, app: ASGIApp, *, max_body_bytes: int) -> None:
        """Configure one application-wide request-body ceiling."""
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Buffer a bounded body and replay it to the downstream application."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        content_length = Headers(scope=scope).get("content-length")
        if content_length is not None:
            try:
                declared_bytes = int(content_length)
            except ValueError:
                await self._send_too_large(send)
                return
            if declared_bytes < 0 or declared_bytes > self.max_body_bytes:
                await self._send_too_large(send)
                return

        body = bytearray()
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > self.max_body_bytes:
                await self._send_too_large(send)
                return
            body.extend(chunk)
            more_body = message.get("more_body", False)

        sent = False

        async def replay_body() -> Message:  # ruff: ignore[unused-async] - ASGI Receive must be async.
            nonlocal sent
            if sent:
                return {"type": "http.request", "body": b"", "more_body": False}
            sent = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, replay_body, send)

    @staticmethod
    async def _send_too_large(send: Send) -> None:
        body = b'{"detail":"The request body is too large."}'
        await send({
            "type": "http.response.start",
            "status": status.HTTP_413_CONTENT_TOO_LARGE,
            "headers": [
                (b"content-length", str(len(body)).encode()),
                (b"content-type", b"application/json"),
            ],
        })
        await send({"type": "http.response.body", "body": body})


async def add_security_headers(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Apply browser security headers to every application response."""
    response = await call_next(request)
    path = request.url.path.rstrip("/")
    if path.startswith("/static/demos/") and path.endswith(".pdf"):
        response.headers["Content-Security-Policy"] = "base-uri 'self'; frame-ancestors 'self'; object-src 'none'"
    elif path == "/invoice-parser/presentation":
        response.headers["Content-Security-Policy"] = (
            "base-uri 'self'; frame-ancestors 'self' https://briannewman.info "
            "https://www.briannewman.info; object-src 'none'"
        )
    else:
        response.headers["Content-Security-Policy"] = "base-uri 'self'; frame-ancestors 'none'; object-src 'none'"
        response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(), geolocation=(), microphone=()"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Content-Type-Options"] = "nosniff"
    if settings.environment is EnvironmentMode.PROD:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response
