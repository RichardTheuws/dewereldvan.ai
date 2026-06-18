"""SEO-laag (L4) — sitemap + robots voor de publieke buitenkant.

- ``GET /sitemap.xml``  alle PUBLIEKE personen + projecten (besloten/geschorst
  uitgesloten via ``seo_service.sitemap_entries`` — dezelfde poort als
  ``can_view(anon)``).
- ``GET /robots.txt``   ``Sitemap:``-verwijzing + ``Disallow`` van de besloten/
  ingelogde paden.

Beide server-rendered; geen DB-write. De ``base_url`` voor absolute loc's komt
uit ``seo_service`` (settings.base_url).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.services import seo_service

router = APIRouter(tags=["seo"])


@router.get("/sitemap.xml")
def sitemap(request: Request, db: Session = Depends(get_db)) -> Response:
    """Alle publieke personen + projecten als ``application/xml`` sitemap."""
    entries = seo_service.sitemap_entries(db)
    body = request.app.state.templates.get_template("sitemap.xml").render(
        {"request": request, "entries": entries}
    )
    return Response(content=body, media_type="application/xml")


@router.get("/robots.txt")
def robots(request: Request) -> Response:
    """Robots-policy: alleen publieke content indexeerbaar; sitemap-verwijzing."""
    body = request.app.state.templates.get_template("robots.txt").render(
        {"request": request, "base_url": settings.base_url.rstrip("/")}
    )
    return Response(content=body, media_type="text/plain")
