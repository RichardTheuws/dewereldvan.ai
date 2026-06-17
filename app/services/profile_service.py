"""Profile service — upsert profile, manage offerings/needs/tags, completeness.

Completeness scoring (deterministic, 0-100):
    bio present            : 25
    makes_summary present  : 15
    >= 1 offering          : 25
    >= 1 need              : 20
    >= 1 tag               : 15
A fully filled profile scores 100. ``recompute_completeness`` is called on
every save so the stored value never drifts from the data.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Need, Offering, Profile, Tag
from app.security import slugify, unique_slug

# Scoring weights — must sum to 100.
_W_BIO = 25
_W_MAKES = 15
_W_OFFERING = 25
_W_NEED = 20
_W_TAG = 15


def compute_completeness(profile: Profile) -> int:
    """Deterministic 0-100 completeness score for a profile."""
    score = 0
    if profile.bio and profile.bio.strip():
        score += _W_BIO
    if profile.makes_summary and profile.makes_summary.strip():
        score += _W_MAKES
    if profile.offerings:
        score += _W_OFFERING
    if profile.needs:
        score += _W_NEED
    if profile.tags:
        score += _W_TAG
    return score


def recompute_completeness(profile: Profile) -> int:
    """Recompute and store the completeness score; returns the new value."""
    profile.completeness = compute_completeness(profile)
    return profile.completeness


def get_or_create_profile(db: Session, member) -> Profile:
    """Return the member's profile, creating an empty one on first edit."""
    if member.profile is not None:
        return member.profile

    base = member.name or member.email.split("@", 1)[0]

    def _slug_taken(candidate: str) -> bool:
        return (
            db.scalar(select(Profile.id).where(Profile.slug == candidate))
            is not None
        )

    # visibility omitted on purpose: the column default (Visibility.members)
    # applies on flush, so new profiles are members-only by default.
    profile = Profile(
        member_id=member.id,
        slug=unique_slug(base, _slug_taken),
        display_name=member.name or base,
    )
    db.add(profile)
    db.flush()
    db.refresh(profile)
    return profile


def _parse_tags(raw: str | None) -> list[str]:
    """Split a comma-separated tag string into normalized, de-duped names."""
    if not raw:
        return []
    seen: dict[str, str] = {}
    for part in raw.split(","):
        name = part.strip()
        if not name:
            continue
        # De-dupe on the normalized slug, keep first-seen display casing.
        seen.setdefault(slugify(name), name)
    return list(seen.values())


def _get_or_create_tag(db: Session, name: str) -> Tag:
    slug = slugify(name)
    tag = db.scalar(select(Tag).where(Tag.slug == slug))
    if tag is None:
        tag = Tag(name=name, slug=slug)
        db.add(tag)
        db.flush()
    return tag


def set_tags(db: Session, profile: Profile, raw_tags: str | None) -> None:
    """Replace the profile's tag set from a comma-separated string."""
    names = _parse_tags(raw_tags)
    profile.tags = [_get_or_create_tag(db, name) for name in names]
    db.flush()


def update_profile(
    db: Session,
    profile: Profile,
    *,
    display_name: str,
    bio: str | None,
    makes_summary: str | None,
    raw_tags: str | None,
) -> Profile:
    """Apply edited profile fields, replace tags, recompute completeness."""
    profile.display_name = display_name
    profile.bio = bio
    profile.makes_summary = makes_summary
    set_tags(db, profile, raw_tags)
    recompute_completeness(profile)
    db.flush()
    return profile


def add_offering(
    db: Session, profile: Profile, *, title: str, description: str | None
) -> Offering:
    offering = Offering(
        title=title,
        description=description,
        position=len(profile.offerings),
    )
    profile.offerings.append(offering)
    recompute_completeness(profile)
    db.flush()
    return offering


def remove_offering(db: Session, profile: Profile, offering_id: int) -> bool:
    """Delete an offering iff it belongs to ``profile``. Returns True on delete."""
    offering = db.get(Offering, offering_id)
    if offering is None or offering.profile_id != profile.id:
        return False
    profile.offerings.remove(offering)
    recompute_completeness(profile)
    db.flush()
    return True


def add_need(
    db: Session, profile: Profile, *, title: str, description: str | None
) -> Need:
    need = Need(
        title=title,
        description=description,
        position=len(profile.needs),
    )
    profile.needs.append(need)
    recompute_completeness(profile)
    db.flush()
    return need


def remove_need(db: Session, profile: Profile, need_id: int) -> bool:
    """Delete a need iff it belongs to ``profile``. Returns True on delete."""
    need = db.get(Need, need_id)
    if need is None or need.profile_id != profile.id:
        return False
    profile.needs.remove(need)
    recompute_completeness(profile)
    db.flush()
    return True
