"""Connections-router (Tier 1 Fase 2) — intro's verzilveren + accept/decline.

Verzilvert een match: "stel me voor" → voorgevuld intro-bericht → bevestigen →
``Connection`` gepersisteerd + een seintje naar de ontvanger via diens
voorkeurskanaal (in-app pull-chip + optioneel Telegram-push; **geen e-mail**). De
ontvanger accepteert/wijst af; bij accept opent de contact-poort (consent).

Routes:
- GET  ``/intro/nieuw?match={id}``  — voorgevuld intro-formulier (require_member).
- POST ``/intro``                   — maak intro + seintje (rate-limit).
- POST ``/intro/{id}/accept``       — ontvanger accepteert (contact ontsloten).
- POST ``/intro/{id}/decline``      — ontvanger wijst af.

Het seintje is best-effort (faalt nooit hard); de intro staat hoe dan ook klaar
(``chip_intros`` bij binnenkomst). CSRF via ``hx-headers``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_member
from app.models import ConnectionStatus, Member, MemberStatus, Profile
from app.models.match_suggestion import MatchSuggestion
from app.services import connection_service, notification_service

router = APIRouter(tags=["connections"])


def _render(request: Request, name: str, ctx: dict | None = None, **kw) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, name, ctx or {}, **kw)


def _member_by_slug(db: Session, slug: str) -> Member | None:
    """Goedgekeurd lid achter een profiel-slug (matchbereik = alle approved)."""
    return db.scalar(
        select(Member)
        .join(Profile, Profile.member_id == Member.id)
        .where(Profile.slug == slug, Member.status == MemberStatus.approved)
    )


def _suggested_message(match: MatchSuggestion, viewer: Member, to_member: Member) -> str:
    """Een voorgevuld, gegrond intro-bericht op basis van de match."""
    to_name = to_member.name
    if match.seeker_member_id == viewer.id:
        return (
            f"Hoi {to_name}, ik zag op dewereldvan.ai dat jouw "
            f"“{match.offering.title}” aansluit op waar ik naar zoek "
            f"(“{match.need.title}”). Zullen we kennismaken?"
        )
    return (
        f"Hoi {to_name}, ik zag op dewereldvan.ai dat je “{match.need.title}” "
        f"zoekt — daar kan ik met “{match.offering.title}” misschien bij helpen. "
        f"Zullen we kennismaken?"
    )


# --------------------------------------------------------------------------- #
# Intro starten                                                               #
# --------------------------------------------------------------------------- #


@router.get("/intro/nieuw", response_class=HTMLResponse)
def intro_form(
    request: Request,
    match: int,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Voorgevuld intro-formulier vanuit een match (de 'stel me voor'-knop)."""
    ms = db.get(MatchSuggestion, match)
    if ms is None:
        return HTMLResponse("", status_code=status.HTTP_404_NOT_FOUND)
    counterpart_id = connection_service.counterpart_for_match(ms, member)
    if counterpart_id is None:  # het lid is geen partij in deze match
        return HTMLResponse("", status_code=status.HTTP_403_FORBIDDEN)
    to_member = db.get(Member, counterpart_id)
    if to_member is None:
        return HTMLResponse("", status_code=status.HTTP_404_NOT_FOUND)
    return _render(
        request,
        "connections/_intro_form.html",
        {
            "match_id": ms.id,
            "to_name": to_member.name,
            "suggested": _suggested_message(ms, member, to_member),
        },
    )


@router.post("/intro", response_class=HTMLResponse)
def create_intro(
    request: Request,
    message: str = Form(""),
    match_id: int = Form(0),
    naar: str = Form(""),
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Maak de intro, zet de match op ``acted``, seintje naar de ontvanger."""
    text = (message or "").strip()
    if not text:
        return HTMLResponse("Schrijf even een kort bericht.", status_code=400)

    # Bepaal de ontvanger: via de match (primair) of via een profiel-slug (agent).
    ms: MatchSuggestion | None = None
    to_member: Member | None = None
    if match_id:
        ms = db.get(MatchSuggestion, match_id)
        if ms is None:
            return HTMLResponse("", status_code=404)
        counterpart_id = connection_service.counterpart_for_match(ms, member)
        if counterpart_id is None:
            return HTMLResponse("", status_code=403)
        to_member = db.get(Member, counterpart_id)
    elif naar:
        to_member = _member_by_slug(db, naar)
    if to_member is None or to_member.id == member.id:
        return HTMLResponse("Die maker kon ik niet vinden.", status_code=400)

    try:
        connection_service.check_intro_rate_limit(db, member)
    except connection_service.IntroRateLimited:
        return HTMLResponse(
            "Je stuurde net al een paar intro's — geef het even tijd.",
            status_code=429,
        )

    conn = connection_service.create_intro(
        db, from_member=member, to_member=to_member, message=text, match=ms
    )
    db.commit()

    # Seintje naar de ontvanger via diens voorkeurskanaal (geen e-mail). De intro
    # staat hoe dan ook klaar: de ontvanger ziet 'm bij binnenkomst (chip_intros);
    # koos die Telegram, dan pusht ``notify`` ook daarheen. Best-effort.
    notification_service.notify(
        db, to_member, notification_service.Notification(
            kind="intro_received",
            title=f"{member.name} wil kennismaken",
            body=text,
            url="/",
        )
    )

    return _render(
        request,
        "connections/_intro_done.html",
        {"to_name": to_member.name, "already": conn.status != ConnectionStatus.pending},
    )


# --------------------------------------------------------------------------- #
# Reageren (ontvanger)                                                        #
# --------------------------------------------------------------------------- #


def _respond(request: Request, db: Session, member: Member, conn_id: int, accept: bool) -> HTMLResponse:
    conn = connection_service.get(db, conn_id)
    if conn is None:
        return HTMLResponse("", status_code=404)
    if conn.to_member_id != member.id:  # alleen de ontvanger beslist
        return HTMLResponse("", status_code=403)
    if accept:
        connection_service.accept(db, conn)
    else:
        connection_service.decline(db, conn)
    db.commit()
    db.refresh(conn)
    return _render(
        request, "connections/_card.html", {"conn": conn, "member_id": member.id}
    )


@router.post("/intro/{conn_id}/accept", response_class=HTMLResponse)
def accept_intro(
    request: Request,
    conn_id: int,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    return _respond(request, db, member, conn_id, accept=True)


@router.post("/intro/{conn_id}/decline", response_class=HTMLResponse)
def decline_intro(
    request: Request,
    conn_id: int,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    return _respond(request, db, member, conn_id, accept=False)
