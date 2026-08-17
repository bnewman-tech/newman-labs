"""Newman Labs home page."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from apps.labs.templating import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse, name="labs_index")
async def labs_index(request: Request) -> HTMLResponse:
    """Render the Newman Labs project index."""
    return templates.TemplateResponse(
        request=request,
        name="pages/home.html",
        context={"active_page": "labs"},
    )
