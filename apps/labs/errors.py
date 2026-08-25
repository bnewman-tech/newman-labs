"""Common application error responses."""

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse

from apps.labs.security import apply_security_headers
from libs.core.logger import get_logger

logger = get_logger(__name__)


def database_unavailable(
    _request: Request,
    exception: Exception,
) -> JSONResponse:
    """Return a safe response when PostgreSQL cannot serve a request."""
    logger.error(
        f"Database request failed: {type(exception).__name__}",
        exc_info=exception,
    )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Database is unavailable"},
    )


def unexpected_error(
    request: Request,
    exception: Exception,
) -> Response:
    """Return a safe, hardened response for an unhandled application error."""
    logger.error(
        f"Unhandled request failed: {type(exception).__name__}",
        exc_info=exception,
    )
    return apply_security_headers(
        request=request,
        response=JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        ),
    )
