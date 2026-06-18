"""Profielfoto + emphasis (L1) — magische upload, AVG-verwijder, prominentie.

Alle routes: ``require_member`` (ingelogd + approved), eigen profiel, CSRF via
``hx-headers`` in de cosmic-pagina. De zware pijplijn (validatie, Pillow-resize,
EXIF-strip, opslag, rate-limit, AVG-spoor) leeft in ``photo_service``; deze
router orkestreert alleen en rendert het juiste htmx-fragment terug.

- ``POST /profiel/foto``             upload (multipart) → ``_photo_ring.html``
- ``POST /profiel/foto/verwijderen``  foto wissen (AVG) → fallback-staat
- ``POST /profiel/emphasis``          emphasis zetten → herrenderde keuze-staat
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException

from app.config import settings
from app.db import get_db
from app.deps import require_member
from app.models import Member
from app.services import emphasis_service, photo_service, profile_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["photo"])


def _render(request: Request, name: str, ctx: dict | None = None, **kw) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, name, ctx or {}, **kw)


def _ring_ctx(profile, **extra) -> dict:
    ctx = {
        "profile": profile,
        "photo": photo_service.photo_or_initials(profile),
    }
    ctx.update(extra)
    return ctx


# --------------------------------------------------------------------------- #
# Foto-upload (magisch)                                                        #
# --------------------------------------------------------------------------- #


@router.post("/profiel/foto", response_class=HTMLResponse)
async def upload_photo(
    request: Request,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Ontvang een afbeelding, verwerk hem server-side en materialiseer 'm.

    De multipart-body wordt expliciet geparsed met ``max_part_size`` op de eigen
    ``max_upload_bytes`` (6 MB). Zou anders Starlette's impliciete 1 MB-default de
    upload al kappen vóór de route draait — waardoor de gedocumenteerde server-cap
    onbereikbaar is en een normale telefoonfoto (>1 MB) een rauwe framework-fout
    geeft i.p.v. de vriendelijke NL-melding. ``store_member_photo`` blijft de echte
    poort: her-valideert type + grootte, dropt EXIF/GPS en herresizet. Rate-limit
    per lid hangt op ``AuditLog``.
    """
    profile = profile_service.get_or_create_profile(db, member)

    # Eigen multipart-parse zodat de 6 MB-cap (en niet Starlette's 1 MB-default)
    # de grens is; een te grote part valt in dezelfde vriendelijke 400 als andere
    # upload-fouten i.p.v. een lekkende framework-exception.
    try:
        form = await request.form(max_part_size=settings.max_upload_bytes)
    except MultiPartException:
        return _render(
            request,
            "profiles/_photo_ring.html",
            _ring_ctx(
                profile,
                error="De afbeelding is te groot. Kies er een tot 6 MB.",
            ),
            status_code=400,
        )

    file = form.get("file")
    if not isinstance(file, UploadFile):
        return _render(
            request,
            "profiles/_photo_ring.html",
            _ring_ctx(profile, error="Geen afbeelding ontvangen. Probeer opnieuw."),
            status_code=400,
        )
    raw = await file.read()

    try:
        new_url = photo_service.store_member_photo(
            db,
            member_id=member.id,
            raw=raw,
            filename=file.filename or "",
            content_type=file.content_type or "",
            old_photo_url=profile.photo_url,
        )
    except photo_service.PhotoRateLimited:
        db.rollback()
        return _render(
            request,
            "profiles/_photo_ring.html",
            _ring_ctx(
                profile,
                error=(
                    "Je hebt zojuist al veel foto's geprobeerd. Even een uurtje "
                    "wachten en het lukt weer."
                ),
            ),
            status_code=429,
        )
    except photo_service.UploadError as exc:
        db.rollback()
        return _render(
            request,
            "profiles/_photo_ring.html",
            _ring_ctx(profile, error=str(exc)),
            status_code=400,
        )

    profile.photo_url = new_url
    db.commit()
    db.refresh(profile)
    return _render(
        request,
        "profiles/_photo_ring.html",
        _ring_ctx(profile, materialized=True),
    )


@router.post("/profiel/foto/verwijderen", response_class=HTMLResponse)
def delete_photo(
    request: Request,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Wis de profielfoto (AVG: verwijderbaar) en val terug op cover/initialen."""
    profile = profile_service.get_or_create_profile(db, member)
    old = profile.photo_url
    if old:
        photo_service.delete_photo(old)
        profile.photo_url = None
        db.commit()
        db.refresh(profile)
    return _render(
        request,
        "profiles/_photo_ring.html",
        _ring_ctx(profile, removed=bool(old)),
    )


# --------------------------------------------------------------------------- #
# Emphasis (prominentie persoon ↔ projecten)                                  #
# --------------------------------------------------------------------------- #


@router.post("/profiel/emphasis", response_class=HTMLResponse)
def set_emphasis(
    request: Request,
    emphasis: str = Form(""),
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Zet de layout-prominentie (person|projects|balanced) en herrender de keuze.

    Eén endpoint, gedeeld door de AI-bouwflow én de bewerkpagina. Onbekende/lege
    waarden vallen veilig terug op ``balanced`` (in de service).
    """
    profile = profile_service.get_or_create_profile(db, member)
    emphasis_service.set_emphasis(db, profile, emphasis)
    db.commit()
    db.refresh(profile)
    return _render(
        request,
        "profiles/_emphasis_choice.html",
        {"profile": profile, "saved": True},
    )
