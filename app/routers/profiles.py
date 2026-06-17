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
from app.services import profile_service
from app.services import visibility as visibility_service

router = APIRouter(tags=["profiles"])


def _render(request: Request, name: str, ctx: dict | None = None, **kw) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, name, ctx or {}, **kw)


def _tags_string(profile: Profile) -> str:
    return ", ".join(tag.name for tag in profile.tags)


def _edit_context(request: Request, profile: Profile, **extra) -> dict:
    ctx = {
        "profile": profile,
        "tags_string": _tags_string(profile),
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
    )
    db.commit()
    return _render(
        request,
        "profiles/edit.html",
        _edit_context(request, profile, saved=True),
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

    return _render(
        request,
        "profiles/view.html",
        {
            "profile": profile,
            "noindex": visibility_service.is_noindex(profile),
            "is_owner": viewer is not None and viewer.id == profile.member_id,
        },
    )
