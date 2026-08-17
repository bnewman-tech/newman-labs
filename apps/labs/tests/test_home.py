"""Newman Labs index tests."""

from datetime import date

import httpx
import pytest

from apps.labs.catalog import LabCatalogItem, LabPublicationStatus
from apps.labs.main import app
from apps.labs.routes import lab_index
from libs.core.dependencies import EnvironmentMode, settings


async def test_labs_index_uses_shared_shell() -> None:
    """The app presents the Lab index inside the shared brand shell."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/", params={"preview": "true"})

    assert response.status_code == 200
    assert "Newman Labs" in response.text
    assert 'href="http://test/houston-signal/"' in response.text
    assert 'href="http://test/invoice-parser/"' in response.text
    assert "Houston public-service activity across 311 requests" in response.text
    assert "/static/images/brian-newman-wordmark-white-720.png" in response.text
    assert "/static/favicon.ico" in response.text
    assert '<meta name="theme-color" content="#1a4164">' in response.text
    assert '<link rel="canonical" href="http://test/">' in response.text
    assert '<meta property="og:url" content="http://test/">' in response.text
    assert '<meta name="twitter:card" content="summary">' in response.text
    assert 'property="og:image"' not in response.text
    assert '"@type": "WebSite"' in response.text
    assert 'aria-controls="labs-menu-panel"' in response.text
    assert 'aria-expanded="false"' in response.text
    assert "Explore the lab index" not in response.text
    assert "Public" in response.text
    assert "In Development" in response.text
    assert "Brian Newman portfolio" in response.text
    assert "Engineer to Zero." in response.text
    assert "not intended for emergency response" not in response.text
    assert "static.cloudflareinsights.com/beacon.min.js" not in response.text


async def test_production_pages_include_cloudflare_web_analytics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Managed deployments render the Labs-specific Cloudflare beacon."""
    site_id = "newman-labs-cloudflare-site-id"
    monkeypatch.setattr(settings, "environment", EnvironmentMode.PROD)
    monkeypatch.setattr(settings, "cloudflare_web_analytics_site_id", site_id)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert 'src="https://static.cloudflareinsights.com/beacon.min.js"' in response.text
    assert f'data-cf-beacon=\'{{"token":"{site_id}"}}\'' in response.text


async def test_public_lab_index_returns_published_labs() -> None:
    """External consumers receive published Labs and their source metadata."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/labs")

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "slug": "invoice-parser",
                "name": "Invoice Parser",
                "summary": ("Secure PDF intake and typed invoice extraction with one Pydantic AI agent."),
                "url": "https://labs.briannewman.info/invoice-parser/",
                "source_url": "https://github.com/bnewman-tech/newman-labs",
                "published_at": "2026-08-16",
            },
            {
                "slug": "houston-signal",
                "name": "Houston Signal",
                "summary": ("Houston public-service activity across 311 requests and active emergency incidents."),
                "url": "https://labs.briannewman.info/houston-signal/",
                "source_url": "https://github.com/bnewman-tech/newman-labs",
                "published_at": "2026-08-11",
            },
        ]
    }


async def test_public_lab_index_returns_newest_releases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The public contract returns every release newest first."""
    monkeypatch.setattr(
        lab_index,
        "LABS",
        (
            LabCatalogItem(
                slug="earlier-lab",
                name="Earlier Lab",
                summary="Earlier public work.",
                route_name="labs_index",
                status=LabPublicationStatus.IN_DEVELOPMENT,
                published_at=date(2026, 1, 1),
            ),
            LabCatalogItem(
                slug="newer-lab",
                name="Newer Lab",
                summary="Newer public work.",
                route_name="labs_index",
                status=LabPublicationStatus.PUBLIC,
                published_at=date(2026, 2, 1),
            ),
        ),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/labs")

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "slug": "newer-lab",
                "name": "Newer Lab",
                "summary": "Newer public work.",
                "url": "https://labs.briannewman.info/newer-lab/",
                "source_url": None,
                "published_at": "2026-02-01",
            },
            {
                "slug": "earlier-lab",
                "name": "Earlier Lab",
                "summary": "Earlier public work.",
                "url": "https://labs.briannewman.info/earlier-lab/",
                "source_url": None,
                "published_at": "2026-01-01",
            },
        ]
    }


async def test_privacy_notice_discloses_site_and_document_processing() -> None:
    """The public notice describes current telemetry and document uploads."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/privacy")
        removed_route = await client.get("/document-data-use")

    assert response.status_code == 200
    assert removed_route.status_code == 404
    assert "Privacy and data use" in response.text
    assert "Request headers are not captured" in response.text
    assert "Only submit content you own or have permission to process" in response.text
    assert "Full AI observability" in response.text
    assert "binary AI content" in response.text
    assert "The Invoice Parser accepts PDF uploads" in response.text
    assert "scheduled for deletion after 30 days" in response.text
    assert "A separate consent checkbox is not required" in response.text
    assert "Cloudflare Web Analytics" in response.text
    assert "does not set analytics cookies" in response.text
    assert "strictly functional, 30-day browser cookie" not in response.text
    assert "Storage and retention" not in response.text
    assert "30-day default retention" not in response.text
