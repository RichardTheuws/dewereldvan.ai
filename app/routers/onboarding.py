"""Onboarding-router (E4b) — cinematische eerste-login op /welkom.

GET ``/welkom`` (``require_member``): rendert de "Welkom in de wereld van…"-
aankomst — de constellatie onthult de eigen ster — en vloeit gechoreografeerd door
naar ``/profiel/ai/bouwen``. ``prefers-reduced-motion`` krijgt een directe knop.

De ``verify``-redirect die nieuwe leden hierheen stuurt zit in ``auth.py``
(SERVICES) via ``onboarding_service.first_login_redirect_path``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_member
from app.models import Member
from app.services import profile_service

router = APIRouter(tags=["onboarding"])


@router.get("/welkom", response_class=HTMLResponse)
def welcome(
    request: Request,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """De cinematische aankomst. Toont de naam van het lid als ontluikende ster."""
    profile = profile_service.get_or_create_profile(db, member)
    db.commit()
    first_name = (member.name or "").strip().split(" ")[0] or member.name
    return request.app.state.templates.TemplateResponse(
        request,
        "onboarding/welcome.html",
        {
            "member": member,
            "profile": profile,
            "first_name": first_name,
            "next_url": "/profiel/ai/bouwen",
        },
    )
