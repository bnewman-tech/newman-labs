"""Process-local request rate limiting."""

import math
import time
from collections import OrderedDict
from dataclasses import dataclass

from fastapi import status
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

RATE_LIMIT_MAX_ENTRIES = 10_000


@dataclass(frozen=True, slots=True)
class RateLimitPolicy:
    """One fixed-window request policy."""

    max_requests: int
    window_seconds: int
    detail: str


DEFAULT_RATE_LIMIT = RateLimitPolicy(
    max_requests=120,
    window_seconds=60,
    detail="Too many requests. Try again shortly.",
)
HOUSTON_MAP_RATE_LIMIT = RateLimitPolicy(
    max_requests=30,
    window_seconds=60,
    detail="Too many map data requests. Try again shortly.",
)
INVOICE_SUBMISSION_RATE_LIMIT = RateLimitPolicy(
    max_requests=5,
    window_seconds=15 * 60,
    detail="Too many invoice submissions. Try again in a few minutes.",
)
INVOICE_POLL_RATE_LIMIT = RateLimitPolicy(
    max_requests=60,
    window_seconds=60,
    detail="Too many invoice status requests. Wait a moment before trying again.",
)


@dataclass(slots=True)
class _RateLimitCounter:
    count: int
    reset_at: float


class InMemoryRateLimiter:
    """Bounded process-local fixed-window counters."""

    def __init__(self) -> None:
        """Start with an empty request ledger."""
        self._counters: OrderedDict[tuple[RateLimitPolicy, str], _RateLimitCounter] = OrderedDict()
        self._next_prune_at = 0.0

    def retry_after_seconds(self, *, client_id: str, policy: RateLimitPolicy) -> int | None:
        """Count one request and return its wait when the policy is exceeded."""
        now = time.monotonic()
        self._prune(now=now)
        key = (policy, client_id)
        counter = self._counters.get(key)
        if counter is None or counter.reset_at <= now:
            if counter is None and len(self._counters) >= RATE_LIMIT_MAX_ENTRIES:
                self._counters.popitem(last=False)
            self._counters[key] = _RateLimitCounter(
                count=1,
                reset_at=now + policy.window_seconds,
            )
            self._counters.move_to_end(key)
            return None

        self._counters.move_to_end(key)
        if counter.count >= policy.max_requests:
            return max(1, math.ceil(counter.reset_at - now))
        counter.count += 1
        return None

    def _prune(self, *, now: float) -> None:
        """Periodically discard expired windows."""
        if now < self._next_prune_at:
            return
        self._counters = OrderedDict(
            (key, counter) for key, counter in self._counters.items() if counter.reset_at > now
        )
        self._next_prune_at = now + 60


def request_rate_limit_policy(*, method: str, path: str) -> RateLimitPolicy | None:
    """Return the policy for one normalized application path."""
    if path == "/health" or path.startswith(("/health/", "/static/")):
        return None
    if method == "POST" and path == "/invoice-parser/api/extractions":
        return INVOICE_SUBMISSION_RATE_LIMIT
    if method == "GET" and path.startswith("/invoice-parser/api/extractions/"):
        return INVOICE_POLL_RATE_LIMIT
    if method == "GET" and path == "/houston-signal/data/map":
        return HOUSTON_MAP_RATE_LIMIT
    return DEFAULT_RATE_LIMIT


class RateLimitMiddleware:
    """Apply per-client request policies before reading request bodies."""

    def __init__(self, app: ASGIApp) -> None:
        """Wrap the downstream ASGI application."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Reject requests that exceed their selected fixed-window policy."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"].rstrip("/") or "/"
        policy = request_rate_limit_policy(method=scope["method"], path=path)
        if policy is None:
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        if client is None:
            response = JSONResponse(
                {"detail": "Request protection is temporarily unavailable."},
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
            await response(scope, receive, send)
            return

        limiter = scope["app"].state.rate_limiter
        retry_after = limiter.retry_after_seconds(client_id=client[0], policy=policy)
        if retry_after is None:
            await self.app(scope, receive, send)
            return

        response = JSONResponse(
            {"detail": policy.detail},
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(retry_after)},
        )
        await response(scope, receive, send)
