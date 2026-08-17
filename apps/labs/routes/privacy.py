"""Newman Labs privacy notice."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from apps.labs.templating import templates

router = APIRouter()


@router.get("/privacy", response_class=HTMLResponse, name="privacy")
async def privacy(request: Request) -> HTMLResponse:
    """Render the current privacy and data-use notice."""
    return templates.TemplateResponse(
        request=request,
        name="pages/privacy.html",
        context={"active_page": "privacy"},
    )
