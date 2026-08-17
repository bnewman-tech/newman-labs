"""HTTP retry policy shared by source integrations."""

import json
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import override

import httpx
from tenacity import RetryCallState
from tenacity.wait import wait_base


class WaitRetryAfterOrExponential(wait_base):
    """Honor Retry-After for throttling and otherwise use exponential backoff."""

    def __init__(self, *, max_wait_time: int) -> None:
        """Set the maximum exponential wait between attempts."""
        self.max_wait_time = max_wait_time

    @override
    def __call__(self, retry_state: RetryCallState) -> float:
        """Return the Retry-After or exponential delay for this attempt."""
        exponential_wait = min(5 * 2 ** (retry_state.attempt_number - 1), self.max_wait_time)
        if retry_state.outcome is None:
            return float(exponential_wait)

        exception = retry_state.outcome.exception()
        if not isinstance(exception, httpx.HTTPStatusError):
            return float(exponential_wait)
        if exception.response.status_code not in {429, 503}:
            return float(exponential_wait)

        retry_after = exception.response.headers.get("Retry-After")
        if retry_after is None:
            return float(exponential_wait)
        try:
            retry_after_seconds = int(retry_after)
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(retry_after)
            except (TypeError, ValueError):
                return float(exponential_wait)
            retry_after_seconds = max(
                0,
                int((retry_at - datetime.now(UTC)).total_seconds()),
            )
        return float(max(exponential_wait, retry_after_seconds))


async def read_bounded_json_response(
    *,
    response: httpx.Response,
    max_bytes: int,
) -> tuple[object, int]:
    """Read one streaming JSON response without exceeding the caller's byte budget."""
    content_length = response.headers.get("Content-Length")
    if content_length is not None:
        try:
            declared_bytes = int(content_length)
        except ValueError as exc:
            raise ValueError("HTTP response has an invalid Content-Length") from exc
        if declared_bytes < 0 or declared_bytes > max_bytes:
            raise ValueError("HTTP response exceeds the configured byte limit")

    body = bytearray()
    async for chunk in response.aiter_bytes():
        if len(body) + len(chunk) > max_bytes:
            raise ValueError("HTTP response exceeds the configured byte limit")
        body.extend(chunk)
    return json.loads(body), len(body)
