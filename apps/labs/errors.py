"""Common application error responses."""

from fastapi import Request, status
from fastapi.responses import JSONResponse

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
