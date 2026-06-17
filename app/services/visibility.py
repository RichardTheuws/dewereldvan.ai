"""Visibility service — change profile visibility, audit it, enforce reads.

Edge cases handled here (PRD §4):
- public -> members: the profile is delisted (login-gated) and gets ``noindex``
  immediately on the read path. The change is audited.
- Enforcement (``can_view`` / ``is_noindex``) is applied on every read of
  ``/leden/{slug}`` — never cached, so a flip takes effect at once.
"""

from __future__ import annotations

from app.models import (
    AuditAction,
    AuditLog,
    Member,
    MemberStatus,
    Profile,
    Visibility,
)
from app.security import naive_utc, utcnow


class ConsentRequired(RuntimeError):
    """Raised when a profile is set to public without explicit consent (AVG)."""


def change_visibility(
    db,
    profile: Profile,
    new_visibility: Visibility,
    *,
    actor: Member | None = None,
    consent: bool = False,
) -> bool:
    """Set ``profile.visibility`` and audit the change.

    Going ``public`` publishes personal data of a natural person, so the AVG
    requires explicit consent (PRD §4). The public transition is refused with
    ``ConsentRequired`` unless ``consent`` is true; on success we persist
    ``consented_public_at`` as proof and record ``consent=true`` in the audit.

    Returns True when the value actually changed (and an audit row was written),
    False when it was already at ``new_visibility`` (no-op, no audit).
    """
    old = profile.visibility
    if old == new_visibility:
        return False

    if new_visibility == Visibility.public and not consent:
        raise ConsentRequired()

    profile.visibility = new_visibility
    detail = f"{old.value}->{new_visibility.value}"
    if new_visibility == Visibility.public:
        profile.consented_public_at = naive_utc(utcnow())
        detail += " consent=true"

    db.add(
        AuditLog(
            action=AuditAction.visibility_changed,
            actor_member_id=actor.id if actor is not None else None,
            target_member_id=profile.member_id,
            detail=detail,
        )
    )
    db.flush()
    return True


def _owner_is_approved(profile: Profile) -> bool:
    """Whether the profile's owning member is currently an approved member.

    A suspended/rejected owner's profile must not be treated as publicly
    viewable or indexable, even if its ``visibility`` is still ``public`` — a
    removed member's personal data has to go offline (PRD §4, AVG).
    """
    return profile.member is not None and profile.member.status == MemberStatus.approved


def can_view(profile: Profile, viewer: Member | None) -> bool:
    """Whether ``viewer`` may see ``profile`` on its public slug page.

    - public profile (owner approved): anyone (incl. anonymous).
    - members profile: requires an authenticated, approved member.
    - the owner always sees their own profile regardless of visibility.
    - a public profile of a suspended/rejected owner is delisted: it is no
      longer world-readable (only the owner themselves still sees it).
    """
    if viewer is not None and viewer.id == profile.member_id:
        return True
    if profile.visibility == Visibility.public and _owner_is_approved(profile):
        return True
    return viewer is not None and viewer.status == MemberStatus.approved


def is_noindex(profile: Profile) -> bool:
    """True when the profile page must carry a ``noindex`` robots directive.

    Only genuinely public profiles of an approved owner are indexable;
    members-only profiles and profiles of suspended/rejected owners are not.
    """
    return not (profile.visibility == Visibility.public and _owner_is_approved(profile))
