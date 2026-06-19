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

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Need,
    Offering,
    Profile,
    ProfileLink,
    ProfileLinkKind,
    Tag,
)
from app.security import slugify, unique_slug
from app.services import offering_slug

if TYPE_CHECKING:  # pragma: no cover — typing only, avoids a runtime import cycle
    from app.services.ai_profile import DraftProfile


def _safe_url(value: str | None) -> str | None:
    """Mirror ``app.main.safe_url`` without importing the app (no import cycle).

    Returns the URL only when it is an ``http(s)``/relative URL, else ``None``.
    Blocks ``javascript:``/``data:``/``vbscript:`` schemes from reaching an
    ``href``/``src`` sink, exactly like the template ``safe_url`` filter. Unlike
    the filter (which returns ``""`` for templates), this returns ``None`` so a
    rejected URL clears the column instead of storing an empty string.
    """
    if not value:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    head = stripped.split("/", 1)[0]
    if ":" in head:
        scheme = head.split(":", 1)[0].strip().lower()
        if scheme not in ("http", "https"):
            return None
    return stripped

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


# --------------------------------------------------------------------------- #
# Per-veld inline-edit helpers (levende profielbouw — SPEC §A.2/§A.4)          #
# --------------------------------------------------------------------------- #


def update_offering(
    db: Session,
    profile: Profile,
    offering_id: int,
    *,
    title: str | None = None,
    description: str | None = None,
    url: str | None = None,
    image_url: str | None = None,
) -> Offering | None:
    """Patch one offering iff it belongs to ``profile``; ``None`` → route 404.

    A title change runs through ``offering_slug.rename_to`` (records the old slug
    for a 301 so an indexed ``/projecten/{slug}`` keeps working) and always
    ``ensure_slug`` (guarantees a stable slug). ``url``/``image_url`` are passed
    through the same ``safe_url`` guard as the public view, so a ``javascript:``
    URL is rejected (stored as ``None``) and never reaches an ``href``/``src``.
    Only provided (non-``None``) fields are touched.
    """
    offering = db.get(Offering, offering_id)
    if offering is None or offering.profile_id != profile.id:
        return None

    if title is not None:
        new_title = title.strip()[:160]
        if new_title and new_title != (offering.title or ""):
            offering_slug.rename_to(db, offering, new_title)
        elif new_title:
            offering.title = new_title
        # An empty title is ignored (title is NOT NULL); keep the existing one.
    if description is not None:
        offering.description = description.strip() or None
    if url is not None:
        new_url = _safe_url(url)
        if new_url != offering.url:
            # De link veranderde → de auto-verrijking (screenshot-hero + AI-
            # samenvatting) hoort bij de óúde URL. Ruim het oude screenshot-bestand
            # op (geen wees-bestand) en null beide velden zodat ze opnieuw
            # genereren voor de nieuwe link (geen verouderde hero/tekst).
            if offering.screenshot_url:
                from app.services import photo_service

                photo_service.delete_photo(offering.screenshot_url)
            offering.screenshot_url = None
            offering.summary = None
        offering.url = new_url
    if image_url is not None:
        offering.image_url = _safe_url(image_url)

    offering_slug.ensure_slug(db, offering)
    recompute_completeness(profile)
    db.flush()
    return offering


# --------------------------------------------------------------------------- #
# Draft persistence (verhuisd uit ai_profile-router — SPEC §F.1, één bron)     #
# --------------------------------------------------------------------------- #


def _extract_text(content) -> str:
    """Trek de zichtbare tekst uit een content-blok (string of blok-lijst)."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts).strip()
    return ""


def _make_need(seeking: str, position: int) -> Need:
    return Need(title=seeking[:160], description=None, position=position)


def _reconcile_offerings(db: Session, profile: Profile, projects: list) -> None:
    """Match bestaande offerings op positie met de nieuwe draft-projecten.

    Per index *i*: hergebruik de bestaande rij (behoud id + slug-historie). Is de
    titel gewijzigd → ``offering_slug.rename_to`` (legt de oude slug vast voor de
    301). Is de titel gelijk → de slug blijft onveranderd. Extra projecten worden
    nieuw aangemaakt; weggevallen projecten worden verwijderd (delete-orphan).
    """
    existing = sorted(profile.offerings, key=lambda o: (o.position, o.id or 0))

    for i, project in enumerate(projects):
        if i < len(existing):
            offering = existing[i]
            if (offering.title or "") != project.name:
                offering_slug.rename_to(db, offering, project.name)
            offering.description = project.description
            offering.url = project.url
            offering.image_url = project.image_url
            offering.position = i
        else:
            offering = Offering(
                title=project.name,
                description=project.description,
                url=project.url,
                image_url=project.image_url,
                position=i,
            )
            profile.offerings.append(offering)

    for offering in existing[len(projects):]:
        profile.offerings.remove(offering)

    db.flush()
    for offering in profile.offerings:
        offering_slug.ensure_slug(db, offering)


def persist_draft(
    db: Session,
    profile: Profile,
    draft: DraftProfile,
    *,
    source_messages: list[dict],
) -> None:
    """Map ``DraftProfile`` onto the data model as a DRAFT (visibility ONGEWIJZIGD).

    Single source of truth shared by the levende-flow stream (Fase 2) and the
    transitional ``maak-draft`` route (SPEC §F.1). Identical logic to the old
    ``ai_profile._persist_draft``:

    - ``headline``/``bio`` -> profile columns.
    - ``projects``        -> Offering (gereconcilieerd op positie; slug-historie
      blijft behouden → geen kapotte ``/projecten/{slug}`` na regenerate).
    - ``roles``           -> ProfileLink kind=affiliation (clear + rebuild).
    - ``seeking``         -> a single Need (append iff non-empty, geen dubbele).
    - ``tags``            -> profile tags.

    ``visibility`` blijft ongemoeid (auto-publiceren gebeurt NOOIT).
    """
    profile.headline = draft.headline
    if draft.bio:
        profile.bio = draft.bio
    profile.ai_enriched = True

    user_texts = [
        _extract_text(m.get("content"))
        for m in source_messages
        if m.get("role") == "user"
    ]
    profile.ai_source_text = "\n\n".join(t for t in user_texts if t) or None

    _reconcile_offerings(db, profile, draft.projects)

    profile.profile_links.clear()
    db.flush()
    for i, role in enumerate(draft.roles):
        profile.profile_links.append(
            ProfileLink(
                label=role.label,
                url=role.url,
                description=role.description,
                image_url=role.image_url,
                kind=ProfileLinkKind.affiliation,
                position=i,
            )
        )

    if draft.seeking:
        existing = {(n.title or "").strip() for n in profile.needs}
        if draft.seeking.strip() not in existing:
            profile.needs.append(_make_need(draft.seeking, len(profile.needs)))

    if draft.tags:
        set_tags(db, profile, ", ".join(draft.tags))

    recompute_completeness(profile)
    db.flush()
