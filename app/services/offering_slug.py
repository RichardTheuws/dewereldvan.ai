"""Offering-slug-service (L3/L4) — stabiele, unieke project-slugs + 301-redirects.

Elke offering ("project") krijgt een schone, stabiele slug voor
``/projecten/{slug}`` (linkwaarde). Regels:

- ``ensure_slug``  : geef een offering een slug als die ontbreekt (uniek; botsing
  → ``-2``-suffix via ``security.unique_slug``). Idempotent.
- ``rename_to``    : hernoem het project → nieuwe slug; de óude slug wordt in
  ``OfferingSlugHistory`` vastgelegd zodat ``/projecten/{oude-slug}``
  301-redirect naar de nieuwe URL (behoud van linkwaarde).
- ``find_by_slug`` / ``redirect_target`` : opzoek-helpers voor de route
  (huidige slug → offering; historische slug → huidige slug voor 301).

FOUNDATION bezit het ``OfferingSlugHistory``-model + de DDL/backfill (migratie
0004); deze service schrijft/ leest alleen de rijen.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Offering, OfferingSlugHistory
from app.security import slugify, unique_slug

__all__ = [
    "ensure_slug",
    "rename_to",
    "find_by_slug",
    "redirect_target",
    "redirect_offering",
]


def _slug_taken(db: Session, candidate: str, *, exclude_id: int | None = None) -> bool:
    """True als ``candidate`` al een (andere) offering-slug of historische slug is.

    Botst zowel tegen de actieve ``offering.slug`` als tegen
    ``offering_slug_history.old_slug`` — zo kan een nieuwe slug nooit een
    bestaande redirect overschaduwen (deterministische 301's blijven kloppen).
    """
    q = select(Offering.id).where(Offering.slug == candidate)
    if exclude_id is not None:
        q = q.where(Offering.id != exclude_id)
    if db.scalar(q) is not None:
        return True
    return (
        db.scalar(
            select(OfferingSlugHistory.id).where(
                OfferingSlugHistory.old_slug == candidate
            )
        )
        is not None
    )


def ensure_slug(db: Session, offering: Offering) -> str:
    """Garandeer dat ``offering`` een stabiele, unieke slug heeft.

    Bestaat er al een slug, dan blijft die ongemoeid (stabiliteit/linkwaarde).
    Ontbreekt hij, dan wordt hij afgeleid van de titel (botsing → suffix) en
    geflusht. Retourneert de (gegarandeerd gezette) slug.
    """
    if offering.slug:
        return offering.slug

    base = offering.title or (
        f"project-{offering.id}" if offering.id is not None else "project"
    )
    slug = unique_slug(base, lambda c: _slug_taken(db, c, exclude_id=offering.id))
    offering.slug = slug
    db.flush()
    return slug


def rename_to(db: Session, offering: Offering, new_title: str) -> str:
    """Hernoem het project en herbereken de slug; registreer de oude slug (301).

    Wijzigt ``offering.title`` naar ``new_title``. Als de daaruit afgeleide slug
    afwijkt van de huidige, wordt de oude slug in ``OfferingSlugHistory``
    vastgelegd (tenzij die er al staat) en de nieuwe slug gezet. Bestaande
    inkomende links op de oude slug blijven zo werken via een 301.

    Retourneert de (mogelijk ongewijzigde) huidige slug. Een lege/slug-loze
    nieuwe titel valt terug op ``ensure_slug``-gedrag.
    """
    offering.title = new_title
    old_slug = offering.slug
    new_root = slugify(new_title or "")

    # Geen zinvolle nieuwe slug, of de slug verandert niet → laat 'm staan
    # (stabiliteit). Wel een slug garanderen als die nog ontbrak.
    if not old_slug:
        return ensure_slug(db, offering)
    if new_root == "lid" or new_root == old_slug:
        return old_slug

    new_slug = unique_slug(
        new_title, lambda c: _slug_taken(db, c, exclude_id=offering.id)
    )
    if new_slug == old_slug:
        return old_slug

    # Leg de oude slug vast voor de 301 (idempotent — niet dubbel toevoegen).
    already = db.scalar(
        select(OfferingSlugHistory.id).where(
            OfferingSlugHistory.old_slug == old_slug
        )
    )
    if already is None:
        db.add(
            OfferingSlugHistory(offering_id=offering.id, old_slug=old_slug)
        )
    offering.slug = new_slug
    db.flush()
    return new_slug


def find_by_slug(db: Session, slug: str) -> Offering | None:
    """Vind de offering met exact deze huidige slug (of ``None``)."""
    if not slug:
        return None
    return db.scalar(select(Offering).where(Offering.slug == slug))


def redirect_offering(db: Session, slug: str) -> Offering | None:
    """Geef de offering terug waarheen een historische ``slug`` moet 301'en.

    Zoekt de oude slug in de history-tabel en levert de bijbehorende offering, zodat
    de route de zichtbaarheidspoort (``can_view`` op de eigenaar) kan toepassen
    vóór het 301-statusverschil het bestaan van besloten content prijsgeeft.
    ``None`` → geen historie (echte 404).
    """
    if not slug:
        return None
    hist = db.scalar(
        select(OfferingSlugHistory).where(OfferingSlugHistory.old_slug == slug)
    )
    if hist is None:
        return None
    return db.get(Offering, hist.offering_id)


def redirect_target(db: Session, slug: str) -> str | None:
    """Geef de huidige slug terug waarnaar een historische ``slug`` moet 301'en.

    Dunne wrapper rond ``redirect_offering`` (slug-only). ``None`` → echte 404.
    """
    offering = redirect_offering(db, slug)
    if offering is None or not offering.slug:
        return None
    return offering.slug
