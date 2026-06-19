"""Projectdetailpagina (L3) — rijke kosmische pagina per offering.

``GET /projecten/{slug}``: naam, omschrijving, beeld, externe link (via
``safe_url``) en de maker. Zichtbaarheidspoort via het eigenaar-profiel: tonen
iff ``can_view(offering.profile, viewer)``; ``is_noindex`` van de eigenaar
bepaalt de robots-directive (besloten/geschorst → noindex én niet publiek).

Onbekende huidige slug → kijk in ``offering_slug_history`` (rename-redirect) →
**301** naar de huidige slug; geen historie → echte 404 (linkwaarde-behoud).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_member
from app.models import Member
from app.services import offering_slug, project_enrich_service, seo_service
from app.services import visibility as visibility_service

router = APIRouter(tags=["projects"])


def _render(request: Request, name: str, ctx: dict | None = None, **kw) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, name, ctx or {}, **kw)


@router.get("/projecten/{slug}", response_class=HTMLResponse)
def view_project(
    request: Request,
    slug: str,
    viewer: Member | None = Depends(current_member),
    db: Session = Depends(get_db),
):
    offering = offering_slug.find_by_slug(db, slug)

    def _denied():
        # Verberg het bestaan: anoniem → login, ingelogd-niet-toegestaan → 404.
        if viewer is None:
            return RedirectResponse(
                url="/login", status_code=status.HTTP_303_SEE_OTHER
            )
        return _render(request, "404.html", status_code=404)

    # Onbekende slug → historische slug? 301 naar de huidige URL (linkwaarde).
    # Maar pas dezelfde zichtbaarheidspoort toe als de directe tak: anders
    # verraadt het 301-statusverschil (vs. 404) het bestaan + de huidige slug
    # van een project van een besloten/geschorst lid aan een anonieme bezoeker.
    if offering is None:
        target_offering = offering_slug.redirect_offering(db, slug)
        if target_offering is not None and target_offering.slug:
            target_profile = target_offering.profile
            if target_profile is None or not visibility_service.can_view(
                target_profile, viewer
            ):
                return _denied()
            return RedirectResponse(
                url=f"/projecten/{target_offering.slug}",
                status_code=status.HTTP_301_MOVED_PERMANENTLY,
            )
        return _render(request, "404.html", status_code=404)

    profile = offering.profile
    # Poort via de eigenaar: een project van een besloten/geschorst lid bestaat
    # publiek niet (verberg het bestaan → 404 / login zoals de profielpagina).
    if profile is None or not visibility_service.can_view(profile, viewer):
        return _denied()

    # Lazy-on-view (universeel vangnet): mist dit project nog een screenshot of
    # samenvatting maar heeft het wél een link, start dan de verrijking in de
    # achtergrond. Dekt projecten uit álle aanmaakpaden (concierge-draft,
    # AI-bouwer, MCP) die de directe na-opslaan-trigger niet raakten. No-op zonder
    # Cloudflare-creds + dubbel-werk-guard zitten in trigger_async.
    if offering.url and (offering.screenshot_url is None or offering.summary is None):
        project_enrich_service.trigger_async(offering.id)

    noindex = visibility_service.is_noindex(profile)
    return _render(
        request,
        "projects/view.html",
        {
            "offering": offering,
            "profile": profile,
            "noindex": noindex,
            "is_owner": viewer is not None and viewer.id == profile.member_id,
            "canonical": seo_service.canonical_url(f"/projecten/{offering.slug}"),
            # JSON-LD alleen voor publiek-indexeerbare projecten (geen datalek in
            # unfurls van besloten content).
            "jsonld": None if noindex else seo_service.jsonld_project(offering),
            "og_image": (
                None
                if noindex
                else seo_service.absolute_url(
                    offering.screenshot_url or offering.image_url
                )
            ),
        },
    )
