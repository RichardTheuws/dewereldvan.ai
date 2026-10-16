"""directory_service — de openbare gids als data (PRD hub §4.2).

Eén bron voor álles wat de hub naar buiten toont als gestructureerde data:
``/makers.json``, ``/llms.txt``, de anonieme MCP-zoektool en de overzichtspagina's.
Elk veld gaat door de poort in ``visibility.py`` met ``viewer=None`` — wat een
bezoeker niet op het profiel ziet, staat hier ook niet in. Nul AI.

Bewust NIET opgenomen: e-mail, regio (``area_*`` is opt-in voor Dichtbij, niet
voor publieke weergave) en alles uit besloten blokken.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Profile
from app.services import members_service, openness_service, seo_service
from app.services.visibility import can_view, public_section_visible

__all__ = [
    "Guide",
    "GUIDES",
    "guide_by_path",
    "maker_record",
    "public_makers",
    "search_public",
    "discipline_counts",
    "makers_for_guide",
    "jsonld_guide",
]


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


# --------------------------------------------------------------------------- #
# Overzichtspagina's per discipline (PRD hub §4.3)                             #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Guide:
    """Eén overzichtspagina ``/gids/<path>``. ``discipline`` = de slug uit
    ``members_service.DISCIPLINES``; de teksten zijn statisch (nul AI)."""

    path: str
    discipline: str
    title: str  # "AI-trainers in Nederland en België"
    short: str  # "Trainers"
    intro: str
    ask: str  # voorbeeldvraag voor de aanvraag ("een training voor ons team")
    self_label: str  # "Werk je zelf als <self_label>?"


GUIDES: list[Guide] = [
    Guide(
        "bouwers",
        "bouwer",
        "AI-bouwers en developers in Nederland en België",
        "Bouwers",
        "Developers en bureaus die AI-toepassingen bouwen: agents, RAG, koppelingen, eigen tools. "
        "Elk profiel toont echt werk dat je kunt bekijken.",
        "een AI-toepassing of koppeling",
        "bouwer of developer",
    ),
    Guide(
        "trainers",
        "trainer",
        "AI-trainers en workshops in Nederland en België",
        "Trainers",
        "Trainers die teams en organisaties leren werken met AI, van een eerste kennismaking tot "
        "verdieping per vak. Je ziet welke workshops ze geven.",
        "een training of workshop voor je team",
        "trainer",
    ),
    Guide(
        "video-ai",
        "video",
        "Makers van AI-video in Nederland en België",
        "Video-AI",
        "Makers die met AI video maken: van promo en uitleg tot film. De showreels staan op hun "
        "profiel.",
        "een video of animatie",
        "maker van AI-video",
    ),
    Guide(
        "audio-ai",
        "audio",
        "Makers van AI-audio en -muziek in Nederland en België",
        "Audio-AI",
        "Makers die met AI muziek, stemmen en geluid maken. "
        "Luister hun werk direct op het profiel.",
        "muziek, een voice-over of geluid",
        "maker van AI-audio",
    ),
    Guide(
        "publicaties",
        "publicaties",
        "Schrijvers en onderzoekers over AI in Nederland en België",
        "Publicaties",
        "Mensen die schrijven, onderzoeken of beleid maken over AI. Hun artikelen en publicaties "
        "staan op het profiel.",
        "een artikel, onderzoek of lezing",
        "schrijver of onderzoeker",
    ),
    Guide(
        "design",
        "design",
        "AI-ontwerpers in Nederland en België",
        "Design",
        "Ontwerpers die AI gebruiken in hun beeld, merk of product. Hun werk staat als galerij op "
        "het profiel.",
        "een ontwerp of beeldtaal",
        "ontwerper",
    ),
]
_BY_PATH = {g.path: g for g in GUIDES}
_SINGULAR = {slug: singular for slug, _pl, singular, _k in members_service.DISCIPLINES}


def guide_by_path(path: str) -> Guide | None:
    return _BY_PATH.get((path or "").strip().lower())


def makers_for_guide(db: Session, guide: Guide, open_to: str | None = None) -> list[Profile]:
    """Openbare makers in deze discipline (afgeleid uit hun publieke werk)."""
    profiles = public_makers(db, discipline=guide.discipline, open_to=open_to)
    return [p for p in profiles if _SINGULAR[guide.discipline] in _disciplines(p)]


def jsonld_guide(guide: Guide, profiles: list[Profile]) -> dict:
    """schema.org ``CollectionPage`` met een ``ItemList`` van de makers."""
    url = seo_service.canonical_url(f"/gids/{guide.path}")
    return {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": guide.title,
        "description": guide.intro,
        "url": url,
        "mainEntity": {
            "@type": "ItemList",
            "numberOfItems": len(profiles),
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": i,
                    "url": seo_service.canonical_url(f"/leden/{p.slug}"),
                    "name": p.display_name,
                }
                for i, p in enumerate(profiles, start=1)
            ],
        },
    }
