"""Ideeen-router (E2) — /ideeen lijst/indienen/stemmen + admin-moderatie.

Routes (zie bouwcontract §3 E2):
- GET  ``/ideeen``                    — kosmische lijst + indien-formulier + lege staat.
- POST ``/ideeen``                    — dien in (rate-limit), swap de lijst.
- POST ``/ideeen/{id}/stem``          — upvote (uniek, idempotent), swap de stemknop.
- POST ``/admin/ideeen/{id}/verberg`` — toggle hidden + AuditLog, swap de kaart.
- POST ``/admin/ideeen/{id}/status``  — zet status, swap de kaart.
- POST ``/admin/ideeen/{id}/promoot`` — maak RoadmapItem + status gepland, swap de kaart.

Auth: lid-routes ``require_member`` (login-gated, noindex); moderatie/promotie
``require_admin``. Stem-uniekheid is HARD via ``uq_idea_vote`` en wordt in de
service netjes (idempotent) afgehandeld. CSRF via ``hx-headers``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_admin, require_member
from app.models import Idea, IdeaStatus, Member
from app.schemas.idea import IdeaForm
from app.services import idea_service

router = APIRouter(tags=["ideas"])


def _render(request: Request, name: str, ctx: dict | None = None, **kw) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, name, ctx or {}, **kw)


def _list_context(db: Session, member: Member) -> dict:
    """Bouw de context voor de lijst: ideeen + stemtotalen + of dit lid al stemde."""
    ideas = idea_service.list_visible(db)
    ids = [i.id for i in ideas]
    counts = idea_service.vote_counts(db, ids)
    voted = idea_service.voted_idea_ids(db, member, ids)
    return {
        "ideas": ideas,
        "counts": counts,
        "voted": voted,
        "member": member,
        "is_admin": member.role.value == "admin",
        "statuses": list(IdeaStatus),
    }


def _card_context(db: Session, idea: Idea, member: Member) -> dict:
    """Context voor één idee-kaart (na een swap)."""
    return {
        "idea": idea,
        "count": idea_service.count_votes(db, idea.id),
        "voted": idea_service.has_voted(db, member, idea.id),
        "member": member,
        "is_admin": member.role.value == "admin",
        "statuses": list(IdeaStatus),
    }


# --------------------------------------------------------------------------- #
# Lijst + indienen                                                            #
# --------------------------------------------------------------------------- #


@router.get("/ideeen", response_class=HTMLResponse)
def index(
    request: Request,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """De kosmische ideeenbus: volledige pagina, of het lijst-fragment bij htmx."""
    ctx = _list_context(db, member)
    if request.headers.get("HX-Request"):
        return _render(request, "ideas/_list.html", ctx)
    return _render(request, "ideas/index.html", ctx)


@router.post("/ideeen", response_class=HTMLResponse)
def submit(
    request: Request,
    title: str = Form(""),
    body: str = Form(""),
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Dien een idee in (rate-limit per lid) en geef de verse lijst terug."""
    try:
        data = IdeaForm(title=title, body=body)
    except ValueError:
        ctx = _list_context(db, member)
        ctx["error"] = "Geef je idee een titel én een beschrijving."
        ctx["form_title"] = title
        ctx["form_body"] = body
        return _render(request, "ideas/_list.html", ctx, status_code=400)

    try:
        idea_service.check_idea_rate_limit(db, member)
    except idea_service.IdeaRateLimited:
        ctx = _list_context(db, member)
        ctx["error"] = (
            "Je deelde net al een paar ideeen — geef ons even tijd. Probeer het "
            "over een uur opnieuw."
        )
        return _render(request, "ideas/_list.html", ctx, status_code=429)

    idea_service.create(db, member=member, title=data.title, body=data.body)
    db.commit()
    return _render(request, "ideas/_list.html", _list_context(db, member))


# --------------------------------------------------------------------------- #
# Stemmen                                                                     #
# --------------------------------------------------------------------------- #


@router.post("/ideeen/{idea_id}/stem", response_class=HTMLResponse)
def vote(
    request: Request,
    idea_id: int,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Voeg een upvote toe (uniek per lid); swap de stemknop met de actuele telling."""
    idea = idea_service.get_visible(db, idea_id)
    if idea is None:
        return HTMLResponse("", status_code=status.HTTP_404_NOT_FOUND)
    result = idea_service.vote(db, idea, member)
    db.commit()
    return _render(
        request,
        "ideas/_vote.html",
        {"idea": idea, "count": result.count, "voted": True},
    )


# --------------------------------------------------------------------------- #
# Admin moderatie + promotie                                                  #
# --------------------------------------------------------------------------- #


@router.post("/admin/ideeen/{idea_id}/verberg", response_class=HTMLResponse)
def admin_hide(
    request: Request,
    idea_id: int,
    admin: Member = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Toggle ``hidden`` op een idee (met AuditLog bij verbergen); swap de kaart."""
    idea = db.get(Idea, idea_id)
    if idea is None:
        return HTMLResponse("", status_code=status.HTTP_404_NOT_FOUND)
    idea_service.set_hidden(db, idea, hidden=not idea.hidden, actor=admin)
    db.commit()
    db.refresh(idea)
    return _render(request, "ideas/_card.html", _card_context(db, idea, admin))


@router.post("/admin/ideeen/{idea_id}/status", response_class=HTMLResponse)
def admin_status(
    request: Request,
    idea_id: int,
    status_value: str = Form("", alias="status"),
    admin: Member = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Zet de idee-status (open/gepland/gedaan/afgewezen); swap de kaart."""
    idea = db.get(Idea, idea_id)
    if idea is None:
        return HTMLResponse("", status_code=status.HTTP_404_NOT_FOUND)
    try:
        new_status = IdeaStatus(status_value.strip().lower())
    except ValueError:
        new_status = idea.status
    idea_service.set_status(db, idea, new_status)
    db.commit()
    db.refresh(idea)
    return _render(request, "ideas/_card.html", _card_context(db, idea, admin))


@router.post("/admin/ideeen/{idea_id}/promoot", response_class=HTMLResponse)
def admin_promote(
    request: Request,
    idea_id: int,
    admin: Member = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Promoot een idee naar de roadmap (status -> gepland, AuditLog); swap de kaart."""
    idea = db.get(Idea, idea_id)
    if idea is None:
        return HTMLResponse("", status_code=status.HTTP_404_NOT_FOUND)
    idea_service.promote(db, idea, actor=admin)
    db.commit()
    db.refresh(idea)
    return _render(request, "ideas/_card.html", _card_context(db, idea, admin))
