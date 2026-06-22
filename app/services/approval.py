"""Approval service — member state machine with audit logging.

State machine (admin actions):
    pending   --approve--> approved   (+ approved_at, + admin role if in admin set)
    pending   --reject-->  rejected
    approved  --suspend--> suspended

Every transition writes exactly one ``AuditLog`` row (actor = admin, target =
member). Illegal transitions raise ``IllegalTransition`` and write nothing.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.config import settings
from app.email import EmailMessage, get_email_sender
from app.email import templates as email_templates
from app.email.base import EmailSendError
from app.models import (
    AuditAction,
    AuditLog,
    Member,
    MemberRole,
    MemberStatus,
)
from app.security import naive_utc, utcnow

logger = logging.getLogger(__name__)


class IllegalTransition(RuntimeError):
    """Raised when a status transition is not allowed from the current state."""


def _send_approval_email(member: Member) -> None:
    """Stuur de welkomst-/login-mail naar een zojuist goedgekeurd lid.

    Best-effort en fail-safe: een hapering in de mail-laag mag de goedkeuring
    NOOIT breken (de status-transitie is al geflusht). Bij falen loggen we en
    keren stil terug — de admin kan altijd opnieuw porren / het lid kan zelf
    via ``/login`` een verse magic-link aanvragen.
    """
    login_url = f"{settings.base_url.rstrip('/')}/login"
    try:
        get_email_sender().send(
            EmailMessage(
                to=member.email,
                subject="Welkom bij dewereldvan.ai — je aanmelding is goedgekeurd",
                text_body=(
                    f"Hoi {member.name},\n\n"
                    "Je aanmelding is goedgekeurd. Je kunt nu inloggen en je plek "
                    "in de wereld opbouwen.\n\n"
                    f"Inloggen: {login_url}\n"
                ),
                html_body=email_templates.render_approval(member.name, login_url),
            )
        )
    except EmailSendError:
        logger.warning("Goedkeurings-mail faalde voor lid %s", member.id)
    except Exception:  # noqa: BLE001 — mail mag de approval nooit breken
        logger.exception("Onverwachte fout bij goedkeurings-mail voor lid %s", member.id)


def _audit(
    db: Session,
    *,
    action: AuditAction,
    actor: Member | None,
    target: Member,
    detail: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        action=action,
        actor_member_id=actor.id if actor is not None else None,
        target_member_id=target.id,
        detail=detail,
    )
    db.add(entry)
    return entry


def approve_member(
    db: Session,
    member: Member,
    *,
    actor: Member | None = None,
    now: datetime | None = None,
) -> Member:
    """pending -> approved. Grants admin role if the e-mail is in the admin set."""
    if member.status != MemberStatus.pending:
        raise IllegalTransition(
            f"Kan alleen een 'pending' lid goedkeuren (huidige status: {member.status.value})."
        )
    now = naive_utc(now or utcnow())
    member.status = MemberStatus.approved
    member.approved_at = now
    member.pending_expires_at = None
    if member.email.lower() in settings.admin_email_set:
        member.role = MemberRole.admin
    _audit(
        db,
        action=AuditAction.member_approved,
        actor=actor,
        target=member,
        detail="pending->approved",
    )
    db.flush()
    _send_approval_email(member)
    return member


def reject_member(
    db: Session,
    member: Member,
    *,
    actor: Member | None = None,
) -> Member:
    """pending -> rejected."""
    if member.status != MemberStatus.pending:
        raise IllegalTransition(
            f"Kan alleen een 'pending' lid weigeren (huidige status: {member.status.value})."
        )
    member.status = MemberStatus.rejected
    member.pending_expires_at = None
    _audit(
        db,
        action=AuditAction.member_rejected,
        actor=actor,
        target=member,
        detail="pending->rejected",
    )
    db.flush()
    return member


def suspend_member(
    db: Session,
    member: Member,
    *,
    actor: Member | None = None,
) -> Member:
    """approved -> suspended."""
    if member.status != MemberStatus.approved:
        raise IllegalTransition(
            f"Kan alleen een 'approved' lid schorsen (huidige status: {member.status.value})."
        )
    member.status = MemberStatus.suspended
    _audit(
        db,
        action=AuditAction.member_suspended,
        actor=actor,
        target=member,
        detail="approved->suspended",
    )
    db.flush()
    return member
