"""Application health endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from libs.core.dependencies import settings
from libs.database.functions import get_api_session

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def health_live() -> dict[str, str]:
    """Report that the application process is running."""
    return {"status": "ok", "environment": settings.environment}


@router.get("/ready")
async def health_ready(
    session: Annotated[AsyncSession, Depends(get_api_session)],
) -> dict[str, str]:
    """Report that the application can reach PostgreSQL."""
    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError as exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        ) from exception
    return {"status": "ok", "database": "connected"}
