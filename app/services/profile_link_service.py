"""ProfileLink-service — volledige CRUD voor rollen/affiliaties (levende profielbouw).

Een ``ProfileLink`` met ``kind=affiliation`` is een rol/affiliatie op een profiel
("verantwoordelijk voor X"). De AI-profielbouw zette deze tot nu toe alleen via de
draft-persist; voor de inline-edit-flow (SPEC §A.3) is volledige CRUD nodig:

- ``add``    : voeg een nieuwe rol toe (``position = len(profile.profile_links)``).
- ``update`` : patch label/url/description/image_url van één rol (eigendoms-check).
- ``remove`` : verwijder één rol (eigendoms-check, delete-orphan).

URL-velden lopen door dezelfde ``safe_url``-guard als de publieke view, zodat een
``javascript:``-URL nooit een ``href``/``src`` bereikt. Elke mutatie herberekent de
completeness (geen-op voor rollen — affiliaties tellen niet mee in de score — maar
gehouden voor consistentie) en flusht.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Profile, ProfileLink, ProfileLinkKind
from app.services.profile_service import _safe_url, recompute_completeness

__all__ = ["add", "update", "remove"]


def add(
    db: Session,
    profile: Profile,
    *,
    label: str,
    url: str | None = None,
    description: str | None = None,
    image_url: str | None = None,
) -> ProfileLink:
    """Voeg een nieuwe affiliation-rol toe achteraan."""
    link = ProfileLink(
        label=(label or "").strip()[:200],
        url=_safe_url(url),
        description=(description or "").strip() or None,
        image_url=_safe_url(image_url),
        kind=ProfileLinkKind.affiliation,
        position=len(profile.profile_links),
    )
    profile.profile_links.append(link)
    recompute_completeness(profile)
    db.flush()
    return link


def update(
    db: Session,
    profile: Profile,
    link_id: int,
    *,
    label: str | None = None,
    url: str | None = None,
    description: str | None = None,
    image_url: str | None = None,
) -> ProfileLink | None:
    """Patch één rol iff die bij ``profile`` hoort; ``None`` → route 404.

    Alleen meegegeven (niet-``None``) velden worden aangeraakt. Een lege ``label``
    wordt genegeerd (``label`` is NOT NULL); lege url/image_url/description wissen
    het veld bewust.
    """
    link = db.get(ProfileLink, link_id)
    if link is None or link.profile_id != profile.id:
        return None
    if label is not None:
        new_label = label.strip()
        if new_label:
            link.label = new_label[:200]
    if url is not None:
        link.url = _safe_url(url)
    if description is not None:
        link.description = description.strip() or None
    if image_url is not None:
        link.image_url = _safe_url(image_url)
    recompute_completeness(profile)
    db.flush()
    return link


def remove(db: Session, profile: Profile, link_id: int) -> bool:
    """Verwijder één rol iff die bij ``profile`` hoort. ``True`` bij verwijderen."""
    link = db.get(ProfileLink, link_id)
    if link is None or link.profile_id != profile.id:
        return False
    profile.profile_links.remove(link)
    recompute_completeness(profile)
    db.flush()
    return True
