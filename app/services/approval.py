"""Approval service — member state machine with audit logging.

State machine (admin actions):
    pending   --approve--> approved   (+ approved_at, + admin role if in admin set)
    pending   --reject-->  rejected
    approved  --suspend--> suspended

Every transition writes exactly one ``AuditLog`` row (actor = admin, target =
member). Illegal transitions raise ``IllegalTransition`` and write nothing.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    AuditAction,
    AuditLog,
    Member,
    MemberRole,
    MemberStatus,
)
from app.security import naive_utc, utcnow


class IllegalTransition(RuntimeError):
    """Raised when a status transition is not allowed from the current state."""


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
