"""Concept-profiel uit de snelle ontdekkingsronde (PRD-profiel-vanzelf §3.2–3.3).

Twee stappen die de achtergrond-job op de server zet, zodat een lid dat wegklikt
toch terugkomt bij een gevuld profiel:

- ``apply_concept``: schrijft kopregel, bio en rollen in de LEGE velden. Een gevuld
  veld raakt hij nooit aan; onder ``CONCEPT_CONFIDENCE`` (naamgenoot-risico) vult hij
  niets. Het profiel blijft besloten: zichtbaarheid verandert hier nooit.
- ``auto_crystallize``: koppelt een vondst met confidence ≥ ``HIGH_CONFIDENCE``
  (project → werk-item, talk/media/blog → nieuws) via dezelfde, idempotente
  ``footprint_service.crystallize`` als de browser. Presence koppelt nooit.

Geen commit; de caller (de job) commit. Self-only: de job werkt alleen op het eigen
profiel van het lid dat de ontdekking startte.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models import Member, Profile, ProfileLinkKind
from app.services import footprint_service, profile_link_service, profile_service

logger = logging.getLogger(__name__)

__all__ = ["apply_concept", "auto_crystallize", "has_content"]


def _blank(value: str | None) -> bool:
    return not (value or "").strip()


def has_content(profile: Profile) -> bool:
    """Python-spiegel van ``members_service.has_content_clause`` voor één profiel."""
    return bool(
        not _blank(profile.headline)
        or not _blank(profile.bio)
        or not _blank(profile.makes_summary)
        or profile.offerings
    )


def apply_concept(
    db: Session, profile: Profile, concept: footprint_service.ProfileConcept | None
) -> list[str]:
    """Vul de lege velden uit het concept; returnt de namen van de gevulde velden."""
    if concept is None or not concept.usable:
        return []
    filled: list[str] = []
    if concept.headline and _blank(profile.headline):
        profile.headline = concept.headline
        filled.append("headline")
    if concept.bio and _blank(profile.bio):
        profile.bio = concept.bio
        filled.append("bio")
    has_roles = any(
        link.kind is ProfileLinkKind.affiliation for link in profile.profile_links
    )
    if concept.roles and not has_roles:
        for label, url in concept.roles:
            profile_link_service.add(db, profile, label=label, url=url)
        filled.append("roles")
    if filled:
        # De "klopt het?"-markering op AI-afgeleide velden (bestaande vlag).
        profile.ai_enriched = True
        profile_service.recompute_completeness(profile)
        db.flush()
    return filled


def auto_crystallize(
    db: Session, profile: Profile, member: Member, finding: dict
) -> footprint_service.Crystallized | None:
    """Koppel één vondst op de server als hij zeker genoeg is (anders ``None``).

    Draait in een savepoint: een fout bij één vondst laat de rest van de run heel.
    """
    if not isinstance(finding, dict):
        return None
    ftype = str(finding.get("type", "") or "")
    if footprint_service.is_presence(ftype) or not footprint_service.is_high_confidence(
        finding.get("confidence")
    ):
        return None
    title = str(finding.get("title", "") or "").strip()
    url = str(finding.get("url", "") or "").strip()
    if not title or not url.lower().startswith(("http://", "https://")):
        return None
    try:
        with db.begin_nested():
            result = footprint_service.crystallize(
                db, profile, member, title=title, url=url, ftype=ftype
            )
    except Exception:  # noqa: BLE001 — één vondst mag de run nooit breken
        logger.exception("auto_crystallize faalde voor profiel %s (%s)", profile.id, url)
        return None
    # De caller start de screenshot/samenvatting-verrijking pas NA zijn commit.
    return result
