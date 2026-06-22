"""Auth routes: open registration, passwordless magic-link login, logout.

Edge cases (PRD §4) surfaced here:
- Duplicate registration -> idempotent, same friendly confirmation either way.
- Magic-link request for unknown/not-yet-approved e-mail -> same neutral
  "als dit adres bekend is, is er een link verstuurd" message (no enumeration).
- Magic-link send failure -> EmailSendError caught and shown, never swallowed.
- Expired / reused / invalid token -> clean login_error page with re-request.
- Rate limit -> friendly "te veel aanvragen" message, no link issued.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import (
    SESSION_MEMBER_KEY,
    current_member,
    email_sender,
)
from app.email import EmailMessage, EmailSender, EmailSendError
from app.email import templates as email_templates
from app.models import Member, MemberRole, MemberStatus
from app.schemas.auth import MagicLinkRequest, RegisterForm
from app.services import approval as approval_service
from app.services import magic_link as magic_link_service
from app.services import notification_service
from app.services import onboarding_service
from app.services import registration as registration_service
from app.services import triage_service

router = APIRouter(tags=["auth"])

logger = logging.getLogger("dewereldvan.auth")


def _notify_admins_new_registration(db: Session, member: Member) -> None:
    """Sein de admins dat een aanmelding op een mens-blik wacht — via **Telegram**.

    Admin-communicatie loopt via Telegram, niet e-mail (operator-voorkeur). Best-
    effort: faalt nooit hard, en de queue is sowieso de bron van waarheid (een admin
    zonder gekoppelde Telegram ziet het wachtende lid daar). Alleen relevant bij een
    ``review``-verdict; auto-welkom leden hoeven geen blik.
    """
    queue_url = f"{settings.base_url.rstrip('/')}/admin/queue"
    notification_service.notify_admins(
        db,
        notification_service.Notification(
            kind="admin_new_registration",
            title="Nieuwe aanmelding wacht op je",
            body=f"{member.name} ({member.email}) — even kijken of dit een echt mens is.",
            url=queue_url,
            action_label="Naar de queue",
        ),
    )


def _templates(request: Request):
    return request.app.state.templates


def _render(request: Request, name: str, ctx: dict | None = None, **kw) -> HTMLResponse:
    return _templates(request).TemplateResponse(request, name, ctx or {}, **kw)


def _set_session(request: Request, member: Member) -> None:
    request.session[SESSION_MEMBER_KEY] = member.id
    request.session["is_admin"] = member.role == MemberRole.admin


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


# --------------------------------------------------------------------------- #
# Registration                                                                #
# --------------------------------------------------------------------------- #


@router.get("/register", response_class=HTMLResponse)
def register_form(request: Request) -> HTMLResponse:
    return _render(request, "auth/register.html")


@router.post("/register", response_class=HTMLResponse)
def register_submit(
    request: Request,
    name: str = Form(""),
    email: str = Form(""),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    try:
        data = RegisterForm(name=name, email=email)
    except ValidationError:
        return _render(
            request,
            "auth/register.html",
            {
                "error": "Controleer je naam en e-mailadres.",
                "name": name,
                "email": email,
            },
            status_code=400,
        )

    # Idempotent: existing e-mail returns the same friendly confirmation.
    try:
        result = registration_service.register_member(
            db, name=data.name, email=data.email, requested_ip=_client_ip(request)
        )
    except registration_service.RegistrationRateLimited:
        db.rollback()
        return _render(
            request,
            "auth/register.html",
            {
                "error": (
                    "Te veel aanmeldingen vanaf dit adres in korte tijd. "
                    "Wacht even en probeer het straks opnieuw."
                ),
                "name": name,
                "email": email,
            },
            status_code=429,
        )
    # Pivot Fase B: de poort filtert spam, niet mensen. Een nieuwe aanmelding wordt
    # getrieerd op spam-/bot-waarschijnlijkheid (nooit op "relevantie"). Lijkt het een
    # echt mens → auto-welkom (direct goedgekeurd + welkomst-mail). Twijfel → blijft
    # pending in de admin-queue (mens beslist). NOOIT auto-weren. Triage faalt veilig
    # naar review, dus registratie strandt nooit op de AI.
    auto_welcomed = False
    if result.created:
        verdict = triage_service.assess_registration(data.name, data.email)
        result.member.triage_note = verdict.reason
        if verdict.is_welcome:
            try:
                approval_service.approve_member(db, result.member, actor=None)
                auto_welcomed = True
            except approval_service.IllegalTransition:
                pass  # niet pending (race) → laat staan, geen auto-welkom
    db.commit()
    # Alleen admins porren (via Telegram) als een mens nog moet kijken (niet bij
    # auto-welkom). Na de commit zodat het lid echt bestaat als de push uitgaat.
    if result.created and not auto_welcomed:
        _notify_admins_new_registration(db, result.member)
    return _render(
        request,
        "auth/register_done.html",
        {"email": data.email, "auto_welcomed": auto_welcomed},
    )


# --------------------------------------------------------------------------- #
# Magic-link login request                                                    #
# --------------------------------------------------------------------------- #


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request) -> HTMLResponse:
    return _render(request, "auth/login_request.html")


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    email: str = Form(""),
    db: Session = Depends(get_db),
    sender: EmailSender = Depends(email_sender),
) -> HTMLResponse:
    try:
        data = MagicLinkRequest(email=email)
    except ValidationError:
        return _render(
            request,
            "auth/login_request.html",
            {"error": "Vul een geldig e-mailadres in.", "email": email},
            status_code=400,
        )

    member = registration_service.get_member_by_email(db, data.email)

    # Only approved members get a working link. For everyone else we still show
    # the same neutral confirmation (no account enumeration), but issue nothing.
    if member is None or member.status != MemberStatus.approved:
        return _render(request, "auth/login_sent.html", {"email": data.email})

    try:
        issued = magic_link_service.issue_link(
            db, member, requested_ip=_client_ip(request)
        )
    except magic_link_service.RateLimitExceeded:
        db.rollback()
        return _render(
            request,
            "auth/login_request.html",
            {
                "error": (
                    "Te veel inlogaanvragen in korte tijd. "
                    "Wacht even en probeer het straks opnieuw."
                ),
                "email": data.email,
            },
            status_code=429,
        )

    verify_url = f"{settings.base_url.rstrip('/')}/auth/verify?token={issued.raw_token}"
    message = EmailMessage(
        to=member.email,
        subject="Je inloglink voor dewereldvan.ai",
        text_body=(
            f"Hoi {member.name},\n\n"
            f"Klik op onderstaande link om in te loggen. De link is "
            f"{settings.magic_link_ttl_min} minuten geldig en kan één keer "
            f"gebruikt worden:\n\n{verify_url}\n\n"
            "Heb je dit niet aangevraagd? Dan kun je deze e-mail negeren.\n"
        ),
        html_body=email_templates.render_magic_link(
            member.name, verify_url, settings.magic_link_ttl_min
        ),
    )
    try:
        sender.send(message)
    except EmailSendError:
        # Surface the failure — never silent. The token row stays but is
        # harmless (unused, short TTL); the member can simply re-request.
        db.commit()
        return _render(
            request,
            "auth/login_request.html",
            {
                "error": (
                    "Het versturen van de inloglink is mislukt. "
                    "Probeer het opnieuw."
                ),
                "email": data.email,
            },
            status_code=502,
        )

    db.commit()
    return _render(request, "auth/login_sent.html", {"email": data.email})


# --------------------------------------------------------------------------- #
# Magic-link verify                                                           #
# --------------------------------------------------------------------------- #


@router.get("/auth/verify", response_class=HTMLResponse)
def verify(
    request: Request,
    token: str = "",
    db: Session = Depends(get_db),
):
    result = magic_link_service.verify_link(db, token)

    if not result.ok:
        db.rollback()
        reasons = {
            magic_link_service.VerifyStatus.expired: (
                "Deze inloglink is verlopen."
            ),
            magic_link_service.VerifyStatus.used: (
                "Deze inloglink is al gebruikt."
            ),
            magic_link_service.VerifyStatus.invalid: (
                "Deze inloglink is ongeldig."
            ),
        }
        return _render(
            request,
            "auth/login_error.html",
            {"reason": reasons.get(result.status, "Deze inloglink is ongeldig.")},
            status_code=400,
        )

    assert result.member is not None
    # Beslis de bestemming VOOR de commit, terwijl het lid nog aan de sessie hangt:
    # eerste login (geen AI-bouw-turns én geen ingevuld profiel) → de cinematische
    # /welkom-aankomst; anders het gewone /profiel/bewerken.
    redirect_path = onboarding_service.first_login_redirect_path(db, result.member)
    # Concierge founder-welkomst (PRD §5.2): herkende mede-oprichter zonder
    # vastgelegd ontstaansverhaal → zet een eenmalige sessie-flag die het
    # frontend bij de eerstvolgende paginaload leest om de Concierge proactief
    # te openen. De flag wordt door de frontend (of de /concierge/index-fetch)
    # geconsumeerd; daarna verdwijnt 'ie. Geen herhaling zolang origin_story leeg
    # is en de flag nog niet verbruikt is.
    if result.member.is_founder and result.member.origin_story is None:
        request.session["concierge_founder_welcome"] = True
    db.commit()
    _set_session(request, result.member)
    return RedirectResponse(url=redirect_path, status_code=303)


# --------------------------------------------------------------------------- #
# Logout                                                                      #
# --------------------------------------------------------------------------- #


@router.post("/logout")
def logout(
    request: Request,
    member: Member | None = Depends(current_member),
) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)
