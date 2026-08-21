"""Application rate-limit policy tests."""

from types import SimpleNamespace

import pytest
from starlette.types import Message, Receive, Scope, Send

from apps.labs import rate_limiting
from apps.labs.rate_limiting import (
    DEFAULT_RATE_LIMIT,
    HOUSTON_MAP_RATE_LIMIT,
    INVOICE_POLL_RATE_LIMIT,
    INVOICE_SUBMISSION_RATE_LIMIT,
    InMemoryRateLimiter,
    RateLimitMiddleware,
    RateLimitPolicy,
    request_rate_limit_policy,
)


@pytest.fixture
def freeze_monotonic(monkeypatch: pytest.MonkeyPatch) -> dict[str, float]:
    """Drive fixed windows from a deterministic clock."""
    clock = {"now": 1_000.0}
    monkeypatch.setattr(rate_limiting.time, "monotonic", lambda: clock["now"])
    return clock


def test_rate_limit_policy_covers_the_application() -> None:
    """Shared defaults, route overrides, and infrastructure exemptions stay explicit."""
    assert request_rate_limit_policy(method="GET", path="/") is DEFAULT_RATE_LIMIT
    assert (
        request_rate_limit_policy(method="POST", path="/invoice-parser/api/extractions")
        is INVOICE_SUBMISSION_RATE_LIMIT
    )
    assert (
        request_rate_limit_policy(method="GET", path="/invoice-parser/api/extractions/newman-run")
        is INVOICE_POLL_RATE_LIMIT
    )
    assert request_rate_limit_policy(method="GET", path="/houston-signal/data/map") is HOUSTON_MAP_RATE_LIMIT
    assert request_rate_limit_policy(method="GET", path="/health/live") is None
    assert request_rate_limit_policy(method="GET", path="/static/css/site.css") is None


def test_rate_limiter_is_per_client_and_resets_after_the_window(
    freeze_monotonic: dict[str, float],
) -> None:
    """One busy client cannot block a peer and expired windows admit traffic."""
    policy = RateLimitPolicy(max_requests=2, window_seconds=30, detail="Slow down.")
    limiter = InMemoryRateLimiter()

    assert limiter.retry_after_seconds(client_id="192.0.2.10", policy=policy) is None
    assert limiter.retry_after_seconds(client_id="192.0.2.10", policy=policy) is None
    assert limiter.retry_after_seconds(client_id="192.0.2.10", policy=policy) == 30
    assert limiter.retry_after_seconds(client_id="192.0.2.11", policy=policy) is None

    freeze_monotonic["now"] += 31
    assert limiter.retry_after_seconds(client_id="192.0.2.10", policy=policy) is None


def test_rate_limiter_bounds_and_prunes_client_state(
    freeze_monotonic: dict[str, float],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Untrusted client identifiers cannot grow the process ledger without bound."""
    monkeypatch.setattr(rate_limiting, "RATE_LIMIT_MAX_ENTRIES", 2)
    policy = RateLimitPolicy(max_requests=2, window_seconds=30, detail="Slow down.")
    limiter = InMemoryRateLimiter()

    for client_id in ("192.0.2.1", "192.0.2.2", "192.0.2.3"):
        assert limiter.retry_after_seconds(client_id=client_id, policy=policy) is None
    assert len(limiter._counters) == 2

    freeze_monotonic["now"] += 61
    assert limiter.retry_after_seconds(client_id="192.0.2.4", policy=policy) is None
    assert len(limiter._counters) == 1


async def test_rate_limit_middleware_rejects_before_reading_the_body() -> None:
    """A limited upload receives its custom response without multipart buffering."""
    receive_calls = 0
    limiter = InMemoryRateLimiter()
    for _ in range(INVOICE_SUBMISSION_RATE_LIMIT.max_requests):
        assert (
            limiter.retry_after_seconds(
                client_id="192.0.2.10",
                policy=INVOICE_SUBMISSION_RATE_LIMIT,
            )
            is None
        )

    async def downstream(  # ruff: ignore[unused-async] - ASGI application must be async.
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        raise AssertionError("request must not reach the application")

    middleware = RateLimitMiddleware(downstream)
    scope: Scope = {
        "type": "http",
        "method": "POST",
        "path": "/invoice-parser/api/extractions",
        "headers": [(b"x-forwarded-for", b"198.51.100.20")],
        "client": ("192.0.2.10", 12345),
        "app": SimpleNamespace(state=SimpleNamespace(rate_limiter=limiter)),
    }
    sent: list[Message] = []

    async def receive() -> Message:  # ruff: ignore[unused-async] - ASGI Receive must be async.
        nonlocal receive_calls
        receive_calls += 1
        return {"type": "http.request", "body": b"%PDF-1.7\n", "more_body": False}

    async def send(message: Message) -> None:  # ruff: ignore[unused-async] - ASGI Send must be async.
        sent.append(message)

    await middleware(scope, receive, send)

    assert receive_calls == 0
    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 429
    headers = sent[0]["headers"]
    assert isinstance(headers, list)
    assert next(value for key, value in headers if key == b"retry-after").isdigit()
    assert sent[1] == {
        "type": "http.response.body",
        "body": f'{{"detail":"{INVOICE_SUBMISSION_RATE_LIMIT.detail}"}}'.encode(),
    }


async def test_rate_limit_middleware_rejects_missing_client_identity() -> None:
    """A missing server-derived client identity never collapses into a shared bucket."""

    async def downstream(  # ruff: ignore[unused-async] - ASGI application must be async.
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        raise AssertionError("request must not reach the application")

    middleware = RateLimitMiddleware(downstream)
    scope: Scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "client": None,
        "app": SimpleNamespace(state=SimpleNamespace(rate_limiter=InMemoryRateLimiter())),
    }
    sent: list[Message] = []

    async def receive() -> Message:  # ruff: ignore[unused-async] - ASGI Receive must be async.
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:  # ruff: ignore[unused-async] - ASGI Send must be async.
        sent.append(message)

    await middleware(scope, receive, send)

    assert sent[0]["status"] == 503
    assert sent[1] == {
        "type": "http.response.body",
        "body": b'{"detail":"Request protection is temporarily unavailable."}',
    }
