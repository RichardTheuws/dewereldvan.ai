"""Profile routes: edit own profile, manage offerings/needs, visibility, view.

htmx is used for the interactive bits (add/remove offering & need, visibility
toggle) so saves happen without a full page reload.

Visibility enforcement on ``/leden/{slug}`` (PRD §4):
- public profile  -> viewable by anyone, indexable (no noindex).
- members profile -> requires login (303 to /login when anonymous), noindex.
- owner always sees their own profile.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_member, require_member
from app.models import Member, Profile
from app.schemas.profile import NeedForm, OfferingForm, ProfileForm, VisibilityForm
from app.services import (
    account_deletion,
    emphasis_service,
    graph_service,
    offering_slug,
    openness_service,
    photo_service,
    profile_service,
    seo_service,
    tool_review_note_service,
)
from app.services import visibility as visibility_service

router = APIRouter(tags=["profiles"])


def _render(request: Request, name: str, ctx: dict | None = None, **kw) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, name, ctx or {}, **kw)


def _tags_string(profile: Profile) -> str:
    return ", ".join(tag.name for tag in profile.tags)


def _tool_notes_context(db: Session, profile: Profile, viewer: Member | None) -> dict:
    """Mens-naast-AI-context (doc 03 §4.3) voor de tool-dossiers van een profiel.

    Bouwt een map ``tool_notes`` (tool_id -> zichtbare aanvullingen) voor elke tool
    van het profiel, plus ``can_note`` (ingelogd lid mag aanvullen) en ``is_admin``
    (verberg-knop + "ververs nu"). Geen viewer → geen formulier/notes (publieke
    pagina blijft schoon). De notes overschrijven de AI-review NOOIT; ze worden er
    apart naast getoond door ``_tool_review_notes.html``.
    """
    if viewer is None:
        return {"tool_notes": {}, "can_note": False, "is_admin": False}
    tool_notes = {
        tool.id: tool_review_note_service.list_notes(db, tool)
        for tool in profile.tools
    }
    return {
        "tool_notes": tool_notes,
        "can_note": True,
        "is_admin": viewer.role.value == "admin",
    }


def _openness_items(profile: Profile) -> list[dict]:
    """De publieke 'Open voor'-beacons: per gekozen openness het icoon/label/blurb +
    de kant-en-klare concierge-prefill-intro (voornaam ingevuld). Lege lijst → geen
    sectie. Gedeeld door de publieke view én de eigenaar-preview."""
    return [
        {
            "slug": o.slug,
            "icon": o.icon,
            "label": o.label,
            "blurb": o.blurb,
            "intro": openness_service.intro_for(o.slug, profile.display_name),
        }
        for o in openness_service.labels_for(profile.open_to)
    ]


def _edit_context(request: Request, profile: Profile, **extra) -> dict:
    ctx = {
        "profile": profile,
        "tags_string": _tags_string(profile),
        "photo": photo_service.photo_or_initials(profile),
        # "Waar ik voor opensta": de catalogus + de al-gekozen set + een gegronde
        # suggestie uit de werk-items (zachte hint in de editor, nul AI-kosten).
        "openness_options": openness_service.options(),
        "openness_selected": set(profile.open_to or []),
        "openness_suggested": set(openness_service.infer_suggested(profile)),
    }
    ctx.update(extra)
    return ctx


# --------------------------------------------------------------------------- #
# Edit own profile                                                            #
# --------------------------------------------------------------------------- #


@router.get("/profiel/bewerken", response_class=HTMLResponse)
def edit_form(
    request: Request,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    profile = profile_service.get_or_create_profile(db, member)
    db.commit()
    return _render(request, "profiles/edit.html", _edit_context(request, profile))


@router.post("/profiel/bewerken", response_class=HTMLResponse)
def edit_submit(
    request: Request,
    display_name: str = Form(""),
    bio: str = Form(""),
    makes_summary: str = Form(""),
    tags: str = Form(""),
    open_to: list[str] = Form(default=[]),
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    profile = profile_service.get_or_create_profile(db, member)
    try:
        data = ProfileForm(
            display_name=display_name,
            bio=bio,
            makes_summary=makes_summary,
            tags=tags,
            open_to=open_to,
        )
    except ValidationError:
        db.rollback()
        return _render(
            request,
            "profiles/edit.html",
            _edit_context(
                request,
                profile,
                error="Controleer je gegevens; een naam is verplicht.",
            ),
            status_code=400,
        )

    profile_service.update_profile(
        db,
        profile,
        display_name=data.display_name,
        bio=data.bio,
        makes_summary=data.makes_summary,
        raw_tags=data.tags,
        open_to=data.open_to,
    )
    db.commit()
    return _render(
        request,
        "profiles/edit.html",
        _edit_context(request, profile, saved=True),
    )


# --------------------------------------------------------------------------- #
# "Bekijk als bezoeker" — publieke preview vóór publicatie                    #
# --------------------------------------------------------------------------- #


@router.get("/profiel/voorbeeld", response_class=HTMLResponse)
def preview_profile(
    request: Request,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Toon de eigenaar exact wat een bezoeker ziet — vóór publiceren.

    Rendert dezelfde ``profiles/view.html`` als de publieke pagina, maar met
    ``is_owner=False`` (de bezoekers-ervaring, niet de eigenaar-nav) en
    ``preview=True`` (de preview-chrome). Dit werkt óók als het profiel nog
    ``members``-only is: we omzeilen ``can_view`` bewust (het is de eigen route
    van de eigenaar). De pagina is altijd ``noindex`` en emit nooit OG/JSON-LD —
    een preview mag nooit in zoekmachines of link-unfurls lekken, ongeacht de
    live-zichtbaarheid.
    """
    profile = profile_service.get_or_create_profile(db, member)
    # Stabiele project-slugs voor de detail-links (idempotent), net als de
    # publieke view — anders breken de "wat ik maak"-kaarten in de preview.
    for off in profile.offerings:
        if not off.slug:
            offering_slug.ensure_slug(db, off)
    db.commit()
    return _render(
        request,
        "profiles/view.html",
        {
            "profile": profile,
            "noindex": True,  # preview is nooit indexeerbaar
            "is_owner": False,  # toon exact de bezoekers-ervaring
            "preview": True,  # activeer de preview-chrome
            "photo": photo_service.photo_or_initials(profile),
            "emphasis_cls": emphasis_service.emphasis_class(profile),
            "canonical": seo_service.canonical_url(f"/leden/{profile.slug}"),
            "open_to_items": _openness_items(profile),
            "jsonld": None,
            "og_image": None,
        },
    )


# --------------------------------------------------------------------------- #
# Offerings ("wat ik maak") — htmx                                            #
# --------------------------------------------------------------------------- #


@router.post("/profiel/offering", response_class=HTMLResponse)
def add_offering(
    request: Request,
    title: str = Form(""),
    description: str = Form(""),
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    profile = profile_service.get_or_create_profile(db, member)
    try:
        data = OfferingForm(title=title, description=description)
    except ValidationError:
        db.rollback()
        return _render(
            request,
            "profiles/_offering_need_row.html",
            {"error": "Geef een titel op.", "kind": "offering"},
            status_code=400,
        )
    item = profile_service.add_offering(
        db, profile, title=data.title, description=data.description
    )
    # Geef het nieuwe project meteen een stabiele slug (/projecten/{slug}).
    offering_slug.ensure_slug(db, item)
    db.commit()
    return _render(
        request,
        "profiles/_offering_need_row.html",
        {"item": item, "kind": "offering", "profile": profile},
    )


@router.delete("/profiel/offering/{offering_id}", response_class=HTMLResponse)
def delete_offering(
    request: Request,
    offering_id: int,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    profile = profile_service.get_or_create_profile(db, member)
    profile_service.remove_offering(db, profile, offering_id)
    db.commit()
    # The targeted row swaps to empty; status block updates out-of-band.
    return _render(request, "profiles/_row_deleted.html", {"profile": profile})


# --------------------------------------------------------------------------- #
# Needs ("waar ik naar zoek") — htmx                                          #
# --------------------------------------------------------------------------- #


@router.post("/profiel/need", response_class=HTMLResponse)
def add_need(
    request: Request,
    title: str = Form(""),
    description: str = Form(""),
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    profile = profile_service.get_or_create_profile(db, member)
    try:
        data = NeedForm(title=title, description=description)
    except ValidationError:
        db.rollback()
        return _render(
            request,
            "profiles/_offering_need_row.html",
            {"error": "Geef een titel op.", "kind": "need"},
            status_code=400,
        )
    item = profile_service.add_need(
        db, profile, title=data.title, description=data.description
    )
    db.commit()
    return _render(
        request,
        "profiles/_offering_need_row.html",
        {"item": item, "kind": "need", "profile": profile},
    )


@router.delete("/profiel/need/{need_id}", response_class=HTMLResponse)
def delete_need(
    request: Request,
    need_id: int,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    profile = profile_service.get_or_create_profile(db, member)
    profile_service.remove_need(db, profile, need_id)
    db.commit()
    return _render(request, "profiles/_row_deleted.html", {"profile": profile})


# --------------------------------------------------------------------------- #
# Visibility toggle — htmx                                                    #
# --------------------------------------------------------------------------- #


@router.post("/profiel/zichtbaarheid", response_class=HTMLResponse)
def change_visibility(
    request: Request,
    visibility: str = Form(""),
    consent: str = Form(""),
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    profile = profile_service.get_or_create_profile(db, member)
    try:
        # A checked HTML checkbox arrives as a truthy string ("on"); unchecked
        # sends nothing (empty) -> consent stays False.
        data = VisibilityForm(visibility=visibility, consent=bool(consent))
    except ValidationError:
        db.rollback()
        return _render(
            request,
            "profiles/_completeness.html",
            {"profile": profile, "error": "Ongeldige keuze."},
            status_code=400,
        )
    try:
        visibility_service.change_visibility(
            db, profile, data.visibility, actor=member, consent=data.consent
        )
    except visibility_service.ConsentRequired:
        db.rollback()
        return _render(
            request,
            "profiles/_completeness.html",
            {
                "profile": profile,
                "error": (
                    "Vink de toestemming aan om je profiel openbaar te maken."
                ),
            },
            status_code=400,
        )
    db.commit()
    return _render(request, "profiles/_completeness.html", {"profile": profile})


# --------------------------------------------------------------------------- #
# Volledige account-/profielverwijdering (AVG — "1 druk op de knop")          #
# --------------------------------------------------------------------------- #


@router.post("/profiel/verwijderen")
def delete_account(
    request: Request,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Wis het volledige profiel + account van het ingelogde lid (definitief).

    Eén klik (na bevestiging in de UI) verwijdert ALLES wat aan dit lid hangt
    (zie ``account_deletion.delete_member_completely``), logt het lid uit, en
    stuurt naar een kosmische afscheidspagina. CSRF wordt door de middleware
    afgedwongen; ``require_member`` stuurt een anonieme aanvraag naar /login.
    """
    account_deletion.delete_member_completely(db, member)
    db.commit()
    # Uitloggen: de sessie wijst nu naar een niet-bestaand lid; volledig wissen.
    request.session.clear()
    # 303 → GET op de afscheidspagina (geen sessie/DB-reads nodig daar).
    return RedirectResponse(url="/profiel/gewist", status_code=303)


@router.get("/profiel/gewist", response_class=HTMLResponse)
def deleted_farewell(request: Request) -> HTMLResponse:
    """Kosmische afscheidspagina na een volledige wissing (noindex, sessieloos)."""
    return _render(request, "profiles/deleted.html")


# --------------------------------------------------------------------------- #
# Public / members profile view                                               #
# --------------------------------------------------------------------------- #


@router.get("/leden/{slug}", response_class=HTMLResponse)
def view_profile(
    request: Request,
    slug: str,
    viewer: Member | None = Depends(current_member),
    db: Session = Depends(get_db),
):
    profile = db.scalar(select(Profile).where(Profile.slug == slug))
    if profile is None:
        return _render(request, "404.html", status_code=404)

    if not visibility_service.can_view(profile, viewer):
        if viewer is None:
            # Members-only + anonymous -> send to login (delisted/login-gated).
            return RedirectResponse(
                url="/login", status_code=status.HTTP_303_SEE_OTHER
            )
        # Logged in but not allowed (should be rare) -> hide existence.
        return _render(request, "404.html", status_code=404)

    # Garandeer stabiele project-slugs voor de detail-links (idempotent; raakt
    # bestaande slugs niet aan). Een backfill miste de na-migratie aangemaakte
    # offerings; dit dicht dat gat op de read-zonder dubbele DDL.
    changed = False
    for off in profile.offerings:
        if not off.slug:
            offering_slug.ensure_slug(db, off)
            changed = True
    if changed:
        db.commit()

    noindex = visibility_service.is_noindex(profile)
    return _render(
        request,
        "profiles/view.html",
        {
            "profile": profile,
            "noindex": noindex,
            "is_owner": viewer is not None and viewer.id == profile.member_id,
            # Gegronde graaf-buren (strict uit DB, nul AI): het profiel is een
            # knoop in de levende kaart, niet een plat CV. Herbruikt op /leden.
            "related": graph_service.related_members(db, profile),
            "photo": photo_service.photo_or_initials(profile),
            "emphasis_cls": emphasis_service.emphasis_class(profile),
            "canonical": seo_service.canonical_url(f"/leden/{profile.slug}"),
            "open_to_items": _openness_items(profile),
            # Mens-naast-AI-correctiepad voor de tool-dossiers (doc 03 §4.3).
            **_tool_notes_context(db, profile, viewer),
            # JSON-LD + OG-beeld alleen voor publiek-indexeerbare profielen.
            "jsonld": None if noindex else seo_service.jsonld_person(profile),
            "og_image": (
                None
                if noindex
                else seo_service.absolute_url(
                    profile.photo_url or profile.cover_image_url
                )
            ),
        },
    )
