"""directory_service — de openbare gids als data (PRD hub §4.2).

Eén bron voor álles wat de hub naar buiten toont als gestructureerde data:
``/makers.json``, ``/llms.txt``, de anonieme MCP-zoektool en de overzichtspagina's.
Elk veld gaat door de poort in ``visibility.py`` met ``viewer=None`` — wat een
bezoeker niet op het profiel ziet, staat hier ook niet in. Nul AI.

Bewust NIET opgenomen: e-mail, regio (``area_*`` is opt-in voor Dichtbij, niet
voor publieke weergave) en alles uit besloten blokken.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Profile
from app.services import members_service, openness_service, seo_service
from app.services.visibility import can_view, public_section_visible

__all__ = ["maker_record", "public_makers", "search_public", "discipline_counts"]


def _disciplines(profile: Profile) -> list[str]:
    # Disciplines worden afgeleid uit de werk-items → alleen als 'wat ik maak' publiek is.
    if not public_section_visible(profile, "makes", None):
        return []
    return members_service.derive_disciplines(profile)


def maker_record(profile: Profile) -> dict:
    """De publieke, machine-leesbare vermelding van één maker."""
    url = seo_service.canonical_url(f"/leden/{profile.slug}")
    rec: dict = {
        "naam": profile.display_name,
        "url": url,
        "kopregel": profile.headline or "",
        "disciplines": _disciplines(profile),
        "tags": [t.name for t in profile.tags],
        "tools": [t.name for t in getattr(profile, "tools", [])],
        "contact": f"{url}/vraag",
    }
    if public_section_visible(profile, "open_to", None):
        rec["open_voor"] = [o.label for o in openness_service.labels_for(profile.open_to)]
    if public_section_visible(profile, "makes", None):
        rec["werk"] = [
            {
                "titel": o.title,
                "url": seo_service.canonical_url(f"/projecten/{o.slug}") if o.slug else None,
                "site": o.url or None,
            }
            for o in sorted(profile.offerings, key=lambda o: o.position)
        ]
    return rec


def public_makers(db: Session, **filters) -> list[Profile]:
    """Alle openbaar zichtbare profielen (defensief nog eens door ``can_view``)."""
    profiles = members_service.list_public_profiles(db, for_visitor=True, **filters)
    return [p for p in profiles if can_view(p, None)]


def search_public(db: Session, term: str, limit: int = 20) -> list[dict]:
    """Zoek in de openbare gids (voor de anonieme MCP-tool): eerst op wat iemand
    maakt, valt dat leeg dan op tag."""
    term = (term or "").strip()
    found = public_makers(db, maakt=term) if term else public_makers(db)
    if term and not found:
        found = public_makers(db, tag=term)
    return [maker_record(p) for p in found[:limit]]


def discipline_counts(profiles: list[Profile]) -> list[tuple[str, str, int]]:
    """(slug, meervoud-label, aantal) per discipline over openbare profielen, in de
    vaste volgorde; disciplines zonder openbare maker vallen weg."""
    out: list[tuple[str, str, int]] = []
    for slug, plural, singular, _kind in members_service.DISCIPLINES:
        n = sum(1 for p in profiles if singular in _disciplines(p))
        if n:
            out.append((slug, plural, n))
    return out
