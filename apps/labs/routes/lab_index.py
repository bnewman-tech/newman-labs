"""Public Newman Labs lab-index API."""

from operator import itemgetter

from fastapi import APIRouter

from apps.labs.catalog import LABS
from apps.labs.schemas import PublicLab, PublicLabIndex

router = APIRouter(prefix="/api/labs", tags=["labs"])
PUBLIC_LABS_URL = "https://labs.briannewman.info"


@router.get("")
async def public_lab_index() -> PublicLabIndex:
    """Return published Labs newest first for public site integrations."""
    released = [(lab, lab.published_at) for lab in LABS if lab.published_at is not None]
    released.sort(key=itemgetter(1), reverse=True)
    return PublicLabIndex(
        items=[
            PublicLab(
                slug=lab.slug,
                name=lab.name,
                summary=lab.summary,
                url=f"{PUBLIC_LABS_URL}/{lab.slug}/",
                source_url=lab.source_url,
                published_at=published_at,
            )
            for lab, published_at in released
        ]
    )
