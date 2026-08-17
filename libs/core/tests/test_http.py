"""HTTP retry policy tests."""

from collections.abc import AsyncIterator
from typing import override
from unittest.mock import Mock

import httpx
import pytest

from libs.core.http import WaitRetryAfterOrExponential, read_bounded_json_response


class ChunkedResponse(httpx.AsyncByteStream):
    """Yield a response without a declared Content-Length."""

    @override
    async def __aiter__(self) -> AsyncIterator[bytes]:
        """Yield multiple chunks like a streaming source."""
        yield b'{"value":'
        yield b'"too-large"}'


def test_retry_wait_honors_retry_after() -> None:
    """A server throttle extends the normal exponential delay."""
    request = httpx.Request("GET", "https://example.com/data")
    response = httpx.Response(429, headers={"Retry-After": "30"}, request=request)
    retry_state = Mock(attempt_number=2)
    retry_state.outcome.exception.return_value = httpx.HTTPStatusError(
        "throttled",
        request=request,
        response=response,
    )

    assert WaitRetryAfterOrExponential(max_wait_time=60)(retry_state) == 30


async def test_bounded_json_rejects_a_large_declared_response() -> None:
    """A source cannot force allocation beyond its declared byte budget."""
    response = httpx.Response(200, content=b'{"value":1}')

    with pytest.raises(ValueError, match="exceeds"):
        await read_bounded_json_response(response=response, max_bytes=5)


async def test_bounded_json_rejects_a_large_chunked_response() -> None:
    """The byte budget still applies when a source omits Content-Length."""
    response = httpx.Response(200, stream=ChunkedResponse())

    with pytest.raises(ValueError, match="exceeds"):
        await read_bounded_json_response(response=response, max_bytes=12)
