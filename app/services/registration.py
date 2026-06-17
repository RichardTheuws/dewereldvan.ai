"""Registration service — idempotent open registration + pending expiry.

Edge cases handled here (PRD §4):
- Duplicate registration (same e-mail, case-insensitive): idempotent. We never
  create a second row and never leak whether the account already existed.
- Pending account expiry: new pending members get ``pending_expires_at`` and
  ``purge_expired_pending`` cleans up only stale *pending* accounts.
- First-admin bootstrap: a configured ADMIN_EMAILS address registers straight
  as approved + admin, so a fresh deployment has an admin who can reach the
  approval queue without a chicken-and-egg deadlock.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    AuditAction,
    AuditLog,
    Member,
    MemberRole,
    MemberStatus,
)
from app.security import naive_utc, pending_expiry, utcnow


@dataclass(frozen=True)
class RegistrationResult:
    member: Member
    created: bool  # True only when a fresh pending member was inserted.


class RegistrationRateLimited(RuntimeError):
    """Raised when one source IP submits too many registrations in an hour."""


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _recent_registrations_from_ip(
    db: Session, requested_ip: str, now: datetime
) -> int:
    window_start = naive_utc(now) - timedelta(hours=1)
    return (
        db.scalar(
            select(func.count())
            .select_from(Member)
            .where(
                Member.registration_ip == requested_ip,
                Member.created_at >= window_start,
            )
        )
        or 0
    )


def get_member_by_email(db: Session, email: str) -> Member | None:
    """Case-insensitive lookup (e-mails are stored lowercased)."""
    return db.scalar(select(Member).where(Member.email == _normalize_email(email)))


def register_member(
    db: Session,
    *,
    name: str,
    email: str,
    requested_ip: str | None = None,
    now: datetime | None = None,
) -> RegistrationResult:
    """Idempotently register a member as ``pending``.

    If the e-mail already exists (any status), return the existing member
    unchanged with ``created=False`` — the caller shows the same friendly
    "we hebben je aanvraag ontvangen" message either way, leaking nothing.

    Anonymous registration is rate-limited per source IP
    (``rate_limit_register_per_hour``) to stop e-mail-bombing / unbounded
    pending-row growth; exceeding it raises ``RegistrationRateLimited``. The
    limit is checked only for genuinely new e-mails (idempotent repeats and the
    trusted admin-bootstrap address are never throttled).
    """
    now = now or utcnow()
    email = _normalize_email(email)

    existing = get_member_by_email(db, email)
    if existing is not None:
        return RegistrationResult(member=existing, created=False)

    # Bootstrap: a configured admin e-mail is created already approved + admin,
    # so a fresh deployment is never deadlocked waiting for an approver.
    is_admin = email in settings.admin_email_set

    if (
        not is_admin
        and requested_ip is not None
        and _recent_registrations_from_ip(db, requested_ip, now)
        >= settings.rate_limit_register_per_hour
    ):
        raise RegistrationRateLimited()

    member = Member(
        name=name.strip(),
        email=email,
        status=MemberStatus.approved if is_admin else MemberStatus.pending,
        role=MemberRole.admin if is_admin else MemberRole.member,
        approved_at=naive_utc(now) if is_admin else None,
        pending_expires_at=None if is_admin else naive_utc(pending_expiry(now)),
        registration_ip=requested_ip,
    )
    db.add(member)
    db.flush()
    if is_admin:
        db.add(
            AuditLog(
                action=AuditAction.member_approved,
                actor_member_id=None,
                target_member_id=member.id,
                detail="bootstrap admin (ADMIN_EMAILS)",
            )
        )
        db.flush()
    return RegistrationResult(member=member, created=True)


def purge_expired_pending(db: Session, now: datetime | None = None) -> int:
    """Delete pending members whose ``pending_expires_at`` has passed.

    Only ``pending`` accounts are removed — approved/suspended/rejected are
    never touched. Returns the number of rows deleted.
    """
    now = naive_utc(now or utcnow())
    stale = db.scalars(
        select(Member).where(
            Member.status == MemberStatus.pending,
            Member.pending_expires_at.is_not(None),
            Member.pending_expires_at < now,
        )
    ).all()
    for member in stale:
        db.delete(member)
    db.flush()
    return len(stale)
