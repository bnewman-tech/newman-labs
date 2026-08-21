"""Shared FastAPI application test isolation."""

import pytest

from apps.labs.main import app
from apps.labs.rate_limiting import InMemoryRateLimiter


@pytest.fixture(autouse=True)
def reset_rate_limiter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent process-local request counts from leaking between tests."""
    monkeypatch.setattr(app.state, "rate_limiter", InMemoryRateLimiter())
