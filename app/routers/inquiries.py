"""Aanvragen van bezoekers (PRD hub §4.1) — "Stel een vraag aan X".

Publiek: ``GET/POST /leden/{slug}/vraag`` (het formulier staat ook ingebed op het
openbare profiel en post via htmx naar dezelfde route). Besloten: de inbox
``/aanvragen`` van het lid. Nul AI; Turnstile + honeypot + limieten in
``inquiry_service``. Zonder Turnstile-keys staat het formulier uit (veilige default,
net als ``/proef``).
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Form, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import current_member, require_member
from app.models import InquiryStatus, Member, Profile
from app.security import client_ip
from app.services import inquiry_service, turnstile_service

router = APIRouter(tags=["inquiries"])


def _render(request: Request, name: str, ctx: dict | None = None, **kw) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, name, ctx or {}, **kw)


def form_context(profile: Profile, viewer: Member | None, **extra) -> dict:
    """Gedeelde context voor het formulier-fragment (profiel + losse pagina)."""
    return {
        "profile": profile,
        "inquiry_open": inquiry_service.accepts_inquiries(profile)
        and turnstile_service.configured(),
        "inquiry_topics": inquiry_service.topics_for(profile),
        "turnstile_site_key": settings.turnstile_site_key,
        "form_started": int(time.time()),
        "form": {
            "name": viewer.name if viewer else "",
            "email": viewer.email if viewer else "",
        },
        "errors": {},
        **extra,
    }


def _profile_or_none(db: Session, slug: str) -> Profile | None:
    return db.scalar(select(Profile).where(Profile.slug == slug))


@router.get("/leden/{slug}/vraag", response_class=HTMLResponse)
def inquiry_page(
    request: Request,
    slug: str,
    viewer: Member | None = Depends(current_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Losse pagina (deelbare contact-link, noindex). Alleen voor openbare profielen."""
    profile = _profile_or_none(db, slug)
    if profile is None or not inquiry_service.accepts_inquiries(profile):
        return _render(request, "404.html", status_code=404)
    if viewer is not None and viewer.id == profile.member_id:
        return RedirectResponse(url="/aanvragen", status_code=303)
    return _render(request, "inquiries/page.html", form_context(profile, viewer))


@router.post("/leden/{slug}/vraag", response_class=HTMLResponse)
async def inquiry_submit(
    request: Request,
    slug: str,
    name: str = Form(default=""),
    email: str = Form(default=""),
    org: str = Form(default=""),
    topic: str = Form(default=""),
    message: str = Form(default=""),
    consent: str | None = Form(default=None),
    website: str = Form(default=""),  # honeypot — mensen zien dit veld niet
    started: str = Form(default=""),
    cf_turnstile_response: str | None = Form(default=None, alias="cf-turnstile-response"),
    viewer: Member | None = Depends(current_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    profile = _profile_or_none(db, slug)
    if profile is None or not inquiry_service.accepts_inquiries(profile):
        return _render(request, "404.html", status_code=404)

    is_htmx = request.headers.get("hx-request") == "true"
    template = "inquiries/_form.html" if is_htmx else "inquiries/page.html"
    form = {"name": name, "email": email, "org": org, "topic": topic, "message": message}

    def _again(errors: dict[str, str], status_code: int = 422) -> HTMLResponse:
        ctx = form_context(profile, viewer, errors=errors)
        ctx["form"] = form
        return _render(request, template, ctx, status_code=status_code)

    if not turnstile_service.configured():
        return _again({"_": "Vragen stellen kan even niet. Probeer het later opnieuw."}, 503)

    try:
        started_at = float(started) if started else None
    except ValueError:
        started_at = None

    # Bot-signalen eerst (goedkoop, geen netwerk); daarna pas Turnstile.
    if website.strip() or (
        started_at is not None and time.time() - started_at < inquiry_service.MIN_FILL_SECONDS
    ):
        return _render(request, template, form_context(profile, viewer, sent=True))

    ok = await run_in_threadpool(
        turnstile_service.verify, cf_turnstile_response or "", client_ip(request)
    )
    if not ok:
        return _again({"_": "We konden niet bevestigen dat je een mens bent. Probeer het opnieuw."})

    result = inquiry_service.submit(
        db,
        profile,
        name=name,
        email=email,
        org=org,
        topic=topic,
        message=message,
        consent=consent is not None,
        ip=client_ip(request),
    )
    if result.status == "invalid":
        return _again(result.errors)
    if result.status == "limit":
        return _again(
            {"_": "Er zijn vandaag al veel vragen verstuurd. Probeer het morgen opnieuw."}, 429
        )
    if result.status == "closed":
        return _render(request, "404.html", status_code=404)
    db.commit()
    return _render(request, template, form_context(profile, viewer, sent=True))


# --------------------------------------------------------------------------- #
# Inbox van het lid                                                            #
# --------------------------------------------------------------------------- #
@router.get("/aanvragen", response_class=HTMLResponse)
def inbox(
    request: Request,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    profile = db.scalar(select(Profile).where(Profile.member_id == member.id))
    return _render(
        request,
        "inquiries/inbox.html",
        {
            "inquiries": inquiry_service.list_for_member(db, member),
            "profile": profile,
            "accepts": profile is not None and inquiry_service.accepts_inquiries(profile),
            "topic_label": inquiry_service.topic_label,
        },
    )


@router.get("/aanvragen/{inquiry_id}", response_class=HTMLResponse)
def inquiry_detail(
    request: Request,
    inquiry_id: int,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    inquiry = inquiry_service.get_for_member(db, member, inquiry_id)
    if inquiry is None:
        return _render(request, "404.html", status_code=404)
    inquiry_service.mark_read(db, inquiry)
    db.commit()
    return _render(
        request,
        "inquiries/detail.html",
        {"inquiry": inquiry, "topic_label": inquiry_service.topic_label(inquiry.topic)},
    )


@router.post("/aanvragen/{inquiry_id}/status")
def inquiry_set_status(
    inquiry_id: int,
    status: str = Form(...),
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
):
    inquiry = inquiry_service.get_for_member(db, member, inquiry_id)
    if inquiry is None:
        return RedirectResponse(url="/aanvragen", status_code=303)
    try:
        new_status = InquiryStatus(status)
    except ValueError:
        return RedirectResponse(url=f"/aanvragen/{inquiry_id}", status_code=303)
    inquiry_service.set_status(db, inquiry, new_status)
    db.commit()
    target = "/aanvragen" if new_status == InquiryStatus.spam else f"/aanvragen/{inquiry_id}"
    return RedirectResponse(url=target, status_code=303)
