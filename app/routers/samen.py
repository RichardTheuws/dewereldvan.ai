"""Samen-router — de datumprikker ("Samenkomen", PRD-samenkomen fase 1).

Routes (allemaal login-gated, noindex — het besloten deel):
- GET  ``/samen``                 — kosmisch overzicht van open prikkers + starten.
- GET  ``/samen/nieuw``           — het prik-formulier (kandidaat-datums).
- POST ``/samen``                 — start een prikker; seintje naar uitgenodigden.
- GET  ``/samen/{id}``            — de constellatie: datums + stem-strip + (maker) auto-selectie.
- POST ``/samen/{id}/stem``       — stem ja/misschien/nee op één datum; swap de constellatie.
- POST ``/samen/{id}/kies``       — (maker) kies de winnende datum → agenda-event.
- POST ``/samen/{id}/annuleer``   — (maker) blaas de prikker af.

Stem-uniekheid is HARD via ``uq_gathering_vote_date_member`` en wordt in de service
race-veilig (savepoint) afgehandeld. CSRF: htmx erft ``X-CSRF-Token`` via de body-
``hx-headers``; het start-formulier draagt een ``csrf_token``-veld.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_member
from app.models import (
    Gathering,
    GatheringState,
    GatheringVoteChoice,
    Member,
    Profile,
    Visibility,
)
from app.services import (
    connection_service,
    gathering_service,
    location_service,
    notification_service,
)

router = APIRouter(tags=["samen"])


def _render(request: Request, name: str, ctx: dict | None = None, **kw) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, name, ctx or {}, **kw)


def _parse_datetimes(values: list[str]) -> list[datetime]:
    """Parse ``datetime-local``-strings ('2026-07-20T19:00') naar datetimes; sla
    lege/onparsebare stil over (de service capt/ontdubbelt/valideert verder)."""
    out: list[datetime] = []
    for raw in values or []:
        raw = (raw or "").strip()
        if not raw:
            continue
        try:
            out.append(datetime.fromisoformat(raw))
        except ValueError:
            continue
    return out


def _is_creator(gathering: Gathering, member: Member) -> bool:
    return gathering.creator_member_id == member.id


# --------------------------------------------------------------------------- #
# Overzicht + starten                                                          #
# --------------------------------------------------------------------------- #


@router.get("/samen", response_class=HTMLResponse)
def samen_index(
    request: Request,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Kosmisch overzicht van open prikkers (nieuwste eerst) + de start-CTA."""
    gatherings = gathering_service.list_active(db)
    tallies = {g.id: gathering_service.tally(db, g, viewer=member) for g in gatherings}
    return _render(
        request,
        "samen/index.html",
        {"gatherings": gatherings, "tallies": tallies, "member": member},
    )


@router.get("/samen/nieuw", response_class=HTMLResponse)
def samen_new(
    request: Request,
    interesse: str = "",
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Het prik-formulier. ``interesse`` (optioneel) vult de auto-selectie-grond
    voor (bv. door de concierge doorgegeven: 'voice-agents')."""
    return _render(
        request,
        "samen/nieuw.html",
        {"member": member, "form": {"interest": interesse.strip()[:120]}},
    )


@router.post("/samen", response_class=HTMLResponse)
def samen_create(
    request: Request,
    title: str = Form(""),
    description: str = Form(""),
    location_hint: str = Form(""),
    interest: str = Form(""),
    datum: list[str] = Form(default=[]),
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
):
    """Start een prikker met de opgegeven kandidaat-datums; seintje naar de
    (interesse-gematchte) makers is optioneel en volgt uit de detailpagina."""
    dates = _parse_datetimes(datum)
    form = {
        "title": title, "description": description,
        "location_hint": location_hint, "interest": interest,
    }
    try:
        gathering_service.check_rate_limit(db, member)
    except gathering_service.GatheringRateLimited:
        return _render(
            request, "samen/nieuw.html",
            {"member": member, "form": form,
             "error": "Je startte net al iets — geef ons even. Probeer het over een uur weer."},
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    try:
        gathering = gathering_service.create(
            db,
            creator=member,
            title=title,
            date_options=dates,
            description=(description or "").strip() or None,
            location_hint=location_hint,
            interest=interest,
        )
    except ValueError as exc:
        msg = str(exc) or "Controleer het formulier."
        return _render(
            request, "samen/nieuw.html",
            {"member": member, "form": form,
             "error": f"Zo lukt het nog niet: {msg}."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    db.commit()
    target = f"/samen/{gathering.id}"
    # Komt de submit uit de concierge-canvas (htmx), navigeer dan de hele pagina
    # naar de verse prikker i.p.v. een heel document in de kaart te swappen.
    if request.headers.get("HX-Request"):
        return HTMLResponse("", headers={"HX-Redirect": target})
    return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)


# --------------------------------------------------------------------------- #
# Detail (constellatie) + stemmen                                             #
# --------------------------------------------------------------------------- #


def _detail_context(db: Session, gathering: Gathering, member: Member) -> dict:
    is_creator = _is_creator(gathering, member)
    ctx = {
        "g": gathering,
        "tally": gathering_service.tally(db, gathering, viewer=member),
        "member": member,
        "is_creator": is_creator,
    }
    # Auto-selectie tonen we alleen aan de maker van een open prikker.
    if is_creator and gathering.state == GatheringState.open:
        ctx["suggested"] = gathering_service.suggest_interested(db, gathering)
        ctx["creator_has_area"] = location_service.has_area(member.profile)
    return ctx


@router.get("/samen/{gathering_id}", response_class=HTMLResponse)
def samen_detail(
    request: Request,
    gathering_id: int,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    gathering = gathering_service.get(db, gathering_id)
    if gathering is None:
        return HTMLResponse("Deze prikker bestaat niet (meer).", status_code=404)
    return _render(request, "samen/detail.html", _detail_context(db, gathering, member))


def _constellation(request: Request, db: Session, gathering: Gathering, member: Member) -> HTMLResponse:
    """Render alléén de constellatie (htmx-swap-target na een stem)."""
    return _render(
        request,
        "samen/_constellation.html",
        {
            "g": gathering,
            "tally": gathering_service.tally(db, gathering, viewer=member),
            "member": member,
            "is_creator": _is_creator(gathering, member),
        },
    )


@router.post("/samen/{gathering_id}/stem", response_class=HTMLResponse)
def samen_vote(
    request: Request,
    gathering_id: int,
    date_id: int = Form(0),
    choice: str = Form(""),
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Stem ja/misschien/nee op één kandidaat-datum; swap de constellatie."""
    gathering = gathering_service.get(db, gathering_id)
    if gathering is None:
        return HTMLResponse("", status_code=404)
    if gathering.state != GatheringState.open:
        # Niet meer te stemmen — geef de huidige stand terug (geen fout).
        return _constellation(request, db, gathering, member)
    date = next((d for d in gathering.dates if d.id == date_id), None)
    if date is None:
        return HTMLResponse("", status_code=404)
    try:
        vote_choice = GatheringVoteChoice(choice)
    except ValueError:
        return HTMLResponse("", status_code=status.HTTP_400_BAD_REQUEST)
    gathering_service.vote(db, member=member, date=date, choice=vote_choice)
    db.commit()
    return _constellation(request, db, gathering, member)


# --------------------------------------------------------------------------- #
# Samenklappen tot een event / annuleren (alleen de maker)                    #
# --------------------------------------------------------------------------- #


@router.post("/samen/{gathering_id}/kies")
def samen_resolve(
    gathering_id: int,
    date_id: int = Form(0),
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
):
    """(Maker) kies de winnende datum → de prikker klapt samen tot een agenda-event.
    We sturen door naar de agenda, waar het verse event met z'n RSVP staat."""
    gathering = gathering_service.get(db, gathering_id)
    if gathering is None:
        return HTMLResponse("", status_code=404)
    if not _is_creator(gathering, member):
        return HTMLResponse("Alleen de starter kiest de datum.", status_code=403)
    if gathering.state != GatheringState.open:
        return RedirectResponse(f"/samen/{gathering.id}", status_code=status.HTTP_303_SEE_OTHER)
    date = next((d for d in gathering.dates if d.id == date_id), None)
    if date is None:
        return HTMLResponse("Kies een van de voorgestelde datums.", status_code=400)
    gathering_service.resolve(db, gathering=gathering, date=date, actor=member)
    db.commit()
    return RedirectResponse("/agenda", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/samen/{gathering_id}/annuleer")
def samen_cancel(
    gathering_id: int,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
):
    """(Maker) blaas een open prikker af; seintje naar de uitgenodigden."""
    gathering = gathering_service.get(db, gathering_id)
    if gathering is None:
        return HTMLResponse("", status_code=404)
    if not _is_creator(gathering, member):
        return HTMLResponse("Alleen de starter kan afblazen.", status_code=403)
    gathering_service.cancel(db, gathering=gathering)
    db.commit()
    return RedirectResponse(f"/samen/{gathering.id}", status_code=status.HTTP_303_SEE_OTHER)


# --------------------------------------------------------------------------- #
# Uitnodigen (één-klik-intro, hergebruikt het bestaande Connection-pad)        #
# --------------------------------------------------------------------------- #


@router.post("/samen/{gathering_id}/nodig", response_class=HTMLResponse)
def samen_invite(
    request: Request,
    gathering_id: int,
    naar: str = Form(""),
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """(Maker) nodig één gematchte maker uit via het bestaande intro-pad: een korte,
    voorgevulde kennismaking (intro→accept→e-mail). Geen nieuwe inbox."""
    gathering = gathering_service.get(db, gathering_id)
    if gathering is None:
        return HTMLResponse("", status_code=404)
    if not _is_creator(gathering, member):
        return HTMLResponse("", status_code=403)
    to_member = _member_by_slug(db, naar)
    if to_member is None or to_member.id == member.id:
        return HTMLResponse("Die maker kon ik niet vinden.", status_code=400)
    try:
        connection_service.check_intro_rate_limit(db, member)
    except connection_service.IntroRateLimited:
        return HTMLResponse("Je stuurde net al een paar intro's — geef het even tijd.", status_code=429)

    plek = f" ({gathering.location_hint})" if gathering.location_hint else ""
    text = (
        f"Hoi! Ik organiseer '{gathering.title}'{plek} en denk dat dit ook iets "
        f"voor jou is. Zou je erbij willen zijn? Je kunt je datum doorgeven via "
        f"de prikker."
    )
    connection_service.create_intro(db, from_member=member, to_member=to_member, message=text)
    db.commit()
    notification_service.notify(
        db, to_member,
        notification_service.Notification(
            kind="gathering_invite",
            title=f"{member.name} nodigt je uit: {gathering.title}",
            body=text,
            url=f"/samen/{gathering.id}",
            action_label="Bekijk de prikker",
        ),
    )
    return _render(request, "samen/_invited.html", {"to_name": to_member.name})


def _member_by_slug(db: Session, slug: str) -> Member | None:
    """Vind een lid via z'n publieke profiel-slug (poort: alleen publiek zichtbaar)."""
    slug = (slug or "").strip()
    if not slug:
        return None
    profile = db.scalar(
        select(Profile).where(Profile.slug == slug, Profile.visibility == Visibility.public)
    )
    return profile.member if profile is not None else None
