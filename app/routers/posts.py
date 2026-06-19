"""Posts-router — /agenda (events) + /nieuws (artikelen) + admin-moderatie.

Twee presentaties op één entiteit (``Post``). Elk goedgekeurd lid plaatst direct
zichtbaar; admin kan verbergen. Spiegelt het ideeën-stramien (lijst + formulier +
swap + rate-limit + admin-hide), maar met type-specifieke velden.

Routes:
- GET  ``/agenda``                     — kosmische agenda + toevoeg-formulier.
- POST ``/agenda``                     — plaats een event, swap de lijst.
- GET  ``/nieuws``                     — kosmisch nieuws + toevoeg-formulier.
- POST ``/nieuws``                     — plaats een artikel, swap de lijst.
- POST ``/admin/posts/{id}/verberg``   — toggle hidden + AuditLog, swap de kaart.

Auth: lid-routes ``require_member`` (login-gated, noindex); moderatie
``require_admin``. CSRF via ``hx-headers``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_admin, require_member
from app.models import EventFrequency, Member, NewsRole, Post, PostKind
from app.schemas.post import EventForm, NewsForm
from app.services import post_service

router = APIRouter(tags=["posts"])


def _render(request: Request, name: str, ctx: dict | None = None, **kw) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, name, ctx or {}, **kw)


def _is_admin(member: Member) -> bool:
    return member.role.value == "admin"


# --------------------------------------------------------------------------- #
# Contexts                                                                    #
# --------------------------------------------------------------------------- #


def _agenda_context(db: Session, member: Member) -> dict:
    return {
        "events": post_service.list_events(db),
        "member": member,
        "is_admin": _is_admin(member),
        "frequencies": list(EventFrequency),
    }


def _nieuws_context(db: Session, member: Member) -> dict:
    return {
        "items": post_service.list_news(db),
        "member": member,
        "is_admin": _is_admin(member),
        "roles": list(NewsRole),
    }


def _card_context(db: Session, post: Post, member: Member) -> dict:
    return {"post": post, "member": member, "is_admin": _is_admin(member)}


# --------------------------------------------------------------------------- #
# Agenda                                                                       #
# --------------------------------------------------------------------------- #


@router.get("/agenda", response_class=HTMLResponse)
def agenda_index(
    request: Request,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """De kosmische agenda: volledige pagina, of het lijst-fragment bij htmx."""
    ctx = _agenda_context(db, member)
    if request.headers.get("HX-Request"):
        return _render(request, "agenda/_list.html", ctx)
    return _render(request, "agenda/index.html", ctx)


@router.post("/agenda", response_class=HTMLResponse)
def agenda_submit(
    request: Request,
    title: str = Form(""),
    frequency: str = Form("eenmalig"),
    next_at: str = Form(""),
    location: str = Form(""),
    cadence_note: str = Form(""),
    url: str = Form(""),
    description: str = Form(""),
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Plaats een event (rate-limit per lid) en geef de verse lijst terug."""
    try:
        data = EventForm(
            title=title,
            frequency=frequency,
            next_at=next_at or None,
            location=location,
            cadence_note=cadence_note,
            url=url,
            description=description,
        )
    except ValueError as exc:
        ctx = _agenda_context(db, member)
        ctx["error"] = _first_error(exc, "Controleer het event: een titel en een geldige frequentie zijn nodig.")
        ctx["form"] = {
            "title": title, "frequency": frequency, "next_at": next_at,
            "location": location, "cadence_note": cadence_note, "url": url,
            "description": description,
        }
        return _render(request, "agenda/_list.html", ctx, status_code=400)

    try:
        post_service.check_post_rate_limit(db, member)
    except post_service.PostRateLimited:
        ctx = _agenda_context(db, member)
        ctx["error"] = (
            "Je voegde net al een paar dingen toe — geef ons even tijd. "
            "Probeer het over een uur opnieuw."
        )
        return _render(request, "agenda/_list.html", ctx, status_code=429)

    post_service.create_event(
        db,
        member=member,
        title=data.title,
        frequency=data.frequency,
        description=data.description,
        url=data.url,
        location=data.location,
        cadence_note=data.cadence_note,
        next_at=data.next_at,
    )
    db.commit()
    return _render(request, "agenda/_list.html", _agenda_context(db, member))


# --------------------------------------------------------------------------- #
# Nieuws                                                                       #
# --------------------------------------------------------------------------- #


@router.get("/nieuws", response_class=HTMLResponse)
def nieuws_index(
    request: Request,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Het kosmische nieuws: volledige pagina, of het lijst-fragment bij htmx."""
    ctx = _nieuws_context(db, member)
    if request.headers.get("HX-Request"):
        return _render(request, "nieuws/_list.html", ctx)
    return _render(request, "nieuws/index.html", ctx)


@router.post("/nieuws", response_class=HTMLResponse)
def nieuws_submit(
    request: Request,
    title: str = Form(""),
    url: str = Form(""),
    role: str = Form("gedeeld"),
    source: str = Form(""),
    published_at: str = Form(""),
    description: str = Form(""),
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Plaats een nieuwsartikel (rate-limit per lid) en geef de verse lijst terug."""
    try:
        data = NewsForm(
            title=title,
            url=url,
            role=role,
            source=source,
            published_at=published_at or None,
            description=description,
        )
    except ValueError as exc:
        ctx = _nieuws_context(db, member)
        ctx["error"] = _first_error(exc, "Controleer het artikel: een titel én een geldige link zijn nodig.")
        ctx["form"] = {
            "title": title, "url": url, "role": role, "source": source,
            "published_at": published_at, "description": description,
        }
        return _render(request, "nieuws/_list.html", ctx, status_code=400)

    try:
        post_service.check_post_rate_limit(db, member)
    except post_service.PostRateLimited:
        ctx = _nieuws_context(db, member)
        ctx["error"] = (
            "Je voegde net al een paar dingen toe — geef ons even tijd. "
            "Probeer het over een uur opnieuw."
        )
        return _render(request, "nieuws/_list.html", ctx, status_code=429)

    post_service.create_news(
        db,
        member=member,
        title=data.title,
        url=data.url,
        role=data.role,
        source=data.source,
        description=data.description,
        published_at=data.published_at,
    )
    db.commit()
    return _render(request, "nieuws/_list.html", _nieuws_context(db, member))


# --------------------------------------------------------------------------- #
# Admin moderatie (één endpoint, swap de juiste kaart per kind)               #
# --------------------------------------------------------------------------- #


@router.post("/admin/posts/{post_id}/verberg", response_class=HTMLResponse)
def admin_hide(
    request: Request,
    post_id: int,
    admin: Member = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Toggle ``hidden`` op een bijdrage (AuditLog bij verbergen); swap de kaart."""
    post = db.get(Post, post_id)
    if post is None:
        return HTMLResponse("", status_code=status.HTTP_404_NOT_FOUND)
    post_service.set_hidden(db, post, hidden=not post.hidden, actor=admin)
    db.commit()
    db.refresh(post)
    template = (
        "agenda/_card.html" if post.kind == PostKind.event else "nieuws/_card.html"
    )
    return _render(request, template, _card_context(db, post, admin))


def _first_error(exc: Exception, fallback: str) -> str:
    """Haal een leesbare reden uit een Pydantic-ValidationError, of val terug."""
    try:
        errors = exc.errors()  # type: ignore[attr-defined]
        if errors:
            msg = errors[0].get("msg", "")
            # Pydantic prefixt custom messages met "Value error, ".
            return msg.replace("Value error, ", "") or fallback
    except (AttributeError, IndexError, TypeError):
        pass
    return fallback
