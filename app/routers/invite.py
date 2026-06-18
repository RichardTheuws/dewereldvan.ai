"""Groep-invite-routes — één deelbare WhatsApp-link → direct profiel bouwen.

PRD-verificatie-links §0 (vereenvoudigde richting):
- ``GET  /uitnodiging/{token}``  : kosmische landing (noindex) met register-form,
  of een nette "verlopen/ongeldig"-pagina. Geen stacktrace bij een dood token.
- ``POST /uitnodiging/{token}``  : valideer token + CSRF + IP-rate-limit, registreer
  het lid DIRECT als ``approved`` (geen admin-queue), log 'm in → /welkom.
- ``GET/POST /admin/uitnodiging`` : admin ziet/roteert de actieve link.

Security: het token is high-entropy + 24u TTL + regenereerbaar (admin doodt een
gelekte link). CSRF is globaal (POST). IP-rate-limit tegen massa-fake-accounts.
De grant is uitsluitend "word approved lid + bouw profiel" — nooit role-escalatie.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import SESSION_MEMBER_KEY, require_admin
from app.models import (
    AuditAction,
    AuditLog,
    Member,
    MemberRole,
    MemberStatus,
)
from app.schemas.auth import RegisterForm
from app.security import naive_utc, utcnow
from app.services import group_invite as group_invite_service
from app.services import registration as registration_service

router = APIRouter(tags=["invite"])


def _render(request: Request, name: str, ctx: dict | None = None, **kw) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, name, ctx or {}, **kw)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _set_session(request: Request, member: Member) -> None:
    request.session[SESSION_MEMBER_KEY] = member.id
    request.session["is_admin"] = member.role == MemberRole.admin


def _invite_url(token: str) -> str:
    return f"{settings.base_url.rstrip('/')}/uitnodiging/{token}"


# --------------------------------------------------------------------------- #
# Publieke landing + registratie                                              #
# --------------------------------------------------------------------------- #


@router.get("/uitnodiging/{token}", response_class=HTMLResponse)
def invite_landing(
    request: Request,
    token: str,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    invite = group_invite_service.validate(db, token)
    if invite is None:
        return _render(request, "invite/expired.html", status_code=410)
    return _render(request, "invite/landing.html", {"token": token})


@router.post("/uitnodiging/{token}", response_class=HTMLResponse)
def invite_register(
    request: Request,
    token: str,
    name: str = Form(""),
    email: str = Form(""),
    db: Session = Depends(get_db),
):
    invite = group_invite_service.validate(db, token)
    if invite is None:
        return _render(request, "invite/expired.html", status_code=410)

    try:
        data = RegisterForm(name=name, email=email)
    except ValidationError:
        return _render(
            request,
            "invite/landing.html",
            {
                "token": token,
                "error": "Controleer je naam en e-mailadres.",
                "name": name,
                "email": email,
            },
            status_code=400,
        )

    now = utcnow()
    email_norm = data.email.strip().lower()
    existing = registration_service.get_member_by_email(db, email_norm)

    if existing is not None:
        # Bestaand lid: niet dupliceren. Promoveer een wachtend lid naar approved
        # (de link IS de goedkeuring) en log gewoon in. Een geschorst/geweigerd
        # lid wordt NIET stilletjes heropend — dat is een admin-beslissing.
        member = existing
        if member.status == MemberStatus.pending:
            member.status = MemberStatus.approved
            member.approved_at = naive_utc(now)
            member.pending_expires_at = None
    else:
        # IP-rate-limit alleen op de écht-nieuwe inschrijving (massa-fake-accounts).
        ip = _client_ip(request)
        if (
            ip is not None
            and registration_service._recent_registrations_from_ip(db, ip, now)
            >= settings.rate_limit_register_per_hour
        ):
            db.rollback()
            return _render(
                request,
                "invite/landing.html",
                {
                    "token": token,
                    "error": (
                        "Te veel aanmeldingen vanaf dit adres in korte tijd. "
                        "Wacht even en probeer het straks opnieuw."
                    ),
                    "name": name,
                    "email": email,
                },
                status_code=429,
            )
        # DIRECT TOELATEN (PRD §0): status=approved, geen admin-queue. Een
        # geconfigureerd ADMIN_EMAILS-adres krijgt zoals overal de admin-rol;
        # de invite-link zélf verleent nooit admin.
        is_admin = email_norm in settings.admin_email_set
        member = Member(
            name=data.name.strip(),
            email=email_norm,
            status=MemberStatus.approved,
            role=MemberRole.admin if is_admin else MemberRole.member,
            approved_at=naive_utc(now),
            pending_expires_at=None,
            registration_ip=_client_ip(request),
            is_founder=registration_service.is_founder_name(data.name),
        )
        db.add(member)
        db.flush()

    db.add(
        AuditLog(
            action=AuditAction.invite_registration,
            actor_member_id=None,
            target_member_id=member.id,
            detail="via groep-invite (direct approved)",
        )
    )
    db.commit()
    _set_session(request, member)
    return RedirectResponse(url="/welkom", status_code=303)


# --------------------------------------------------------------------------- #
# Admin: actieve link tonen + roteren                                         #
# --------------------------------------------------------------------------- #


@router.get("/admin/uitnodiging", response_class=HTMLResponse)
def admin_invite(
    request: Request,
    admin: Member = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    invite = group_invite_service.active_invite(db)
    return _render(
        request,
        "admin/uitnodiging.html",
        {
            "invite": invite,
            "invite_url": _invite_url(invite.token) if invite else None,
        },
    )


@router.post("/admin/uitnodiging", response_class=HTMLResponse)
def admin_invite_generate(
    request: Request,
    admin: Member = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    invite = group_invite_service.generate(db, admin)
    db.commit()
    return _render(
        request,
        "admin/uitnodiging.html",
        {
            "invite": invite,
            "invite_url": _invite_url(invite.token),
            "just_generated": True,
        },
    )
