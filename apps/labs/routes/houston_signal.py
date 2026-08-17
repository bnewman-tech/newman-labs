"""Houston Signal web and data routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.labs.templating import templates
from labs.houston_signal.schemas import HoustonSignalMapData, HoustonSignalMapFilters
from labs.houston_signal.services import (
    get_houston_signal_map_data,
    get_houston_signal_overview,
    get_houston_signal_platform_status,
)
from libs.database.functions import get_api_session

router = APIRouter(prefix="/houston-signal", tags=["houston-signal"])


@router.get("/", response_class=HTMLResponse, name="houston_signal_overview")
async def overview(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_api_session)],
) -> HTMLResponse:
    """Render the Houston Signal dashboard from governed database views."""
    overview_data = await get_houston_signal_overview(session=session)
    platform_data = await get_houston_signal_platform_status(session=session)
    return templates.TemplateResponse(
        request=request,
        name="labs/houston_signal.html",
        context={
            "active_page": "houston-signal",
            "data": overview_data,
            "platform": platform_data,
            "trend_json": [activity.model_dump(mode="json") for activity in overview_data.daily_activity],
        },
    )


@router.get("/data/map", name="houston_signal_map_data")
async def map_data(
    filters: Annotated[HoustonSignalMapFilters, Query()],
    session: Annotated[AsyncSession, Depends(get_api_session)],
    response: Response,
) -> HoustonSignalMapData:
    """Return bounded Houston 311 map cells for the requested filters."""
    response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=60"
    return await get_houston_signal_map_data(
        session=session,
        days=filters.days,
        status=filters.status,
        district=filters.district,
        case_type=filters.case_type,
    )
