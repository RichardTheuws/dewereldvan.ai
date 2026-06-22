"""Openness-service — "waar ik voor opensta" (engagement-beschikbaarheid).

Een derde as naast ``Offering`` ("wat ik maak") en ``Need`` ("wat ik zoek"): waar
een lid voor benaderbaar is — klantwerk, trainingen, spreken, interviews,
samenwerkingen. Een lid-gekozen set canonieke slugs in ``Profile.open_to`` (JSON).

De catalogus is hier de enige waarheid: label (chip), icoon, blurb (microcopy op de
publieke beacon) en een intro-prompt (voor de actionable concierge-prefill). Zo blijft
de UI overal consistent en hoeft een nieuwe categorie alleen hier toegevoegd te worden.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models import OfferingKind, Profile

__all__ = [
    "OPENNESS",
    "options",
    "labels_for",
    "normalize",
    "infer_suggested",
    "intro_for",
    "is_valid",
]


@dataclass(frozen=True)
class Openness:
    slug: str
    label: str
    icon: str
    blurb: str  # korte microcopy op de publieke beacon
    intro: str  # zin die de concierge-prefill vult ("Ik wil {naam} …")


# Vaste volgorde = de chip-/beacon-volgorde overal. {naam} wordt in ``intro_for``
# ingevuld met de voornaam van de maker.
OPENNESS: list[Openness] = [
    Openness("klantwerk", "Klantwerk", "💼", "open voor opdrachten",
             "Ik heb een opdracht waarvoor ik {naam} wil benaderen"),
    Openness("trainingen", "Trainingen", "🎓", "geeft trainingen & workshops",
             "Ik wil {naam} vragen voor een training of workshop"),
    Openness("spreken", "Spreken", "🎤", "beschikbaar als spreker",
             "Ik wil {naam} uitnodigen om te spreken"),
    Openness("interviews", "Interviews", "🎙", "open voor interviews",
             "Ik wil {naam} interviewen"),
    Openness("samenwerkingen", "Samenwerkingen", "🤝", "zoekt samenwerkingen",
             "Ik wil met {naam} samenwerken"),
]
_BY_SLUG: dict[str, Openness] = {o.slug: o for o in OPENNESS}


def is_valid(slug: str) -> bool:
    return slug in _BY_SLUG


def options() -> list[Openness]:
    """De volledige catalogus (voor de editor-chips + de /leden-filter)."""
    return list(OPENNESS)


def normalize(raw: list[str] | None) -> list[str]:
    """Maak een opgeslagen waarde schoon: alleen geldige slugs, ontdubbeld, in de
    canonieke volgorde. Lege lijst → ``[]`` (de caller mag dat als ``None`` opslaan)."""
    if not raw:
        return []
    chosen = {s.strip().lower() for s in raw}
    return [o.slug for o in OPENNESS if o.slug in chosen]


def labels_for(open_to: list[str] | None) -> list[Openness]:
    """De gekozen openness-items van een profiel, in canonieke volgorde (voor render)."""
    if not open_to:
        return []
    chosen = set(open_to)
    return [o for o in OPENNESS if o.slug in chosen]


def intro_for(slug: str, name: str) -> str:
    """De concierge-prefill-zin voor een beacon (voornaam ingevuld; nette fallback)."""
    o = _BY_SLUG.get(slug)
    if o is None:
        return ""
    first = (name or "").split(" ")[0] or "dit lid"
    return o.intro.replace("{naam}", first)


# --------------------------------------------------------------------------- #
# Gegronde suggestie (zero-AI) — leid uit iemands werk af waar 't op wijst.    #
# De editor toont deze als "voorgesteld" zodat het lid niet vanaf nul begint.  #
# --------------------------------------------------------------------------- #

# Welke openness een werk-soort impliceert (puur heuristisch, gegrond op echte data).
_KIND_HINTS: dict[OfferingKind, tuple[str, ...]] = {
    OfferingKind.workshop: ("trainingen", "spreken"),
    OfferingKind.writing: ("interviews", "spreken"),
    OfferingKind.video: ("samenwerkingen",),
    OfferingKind.audio: ("samenwerkingen",),
    OfferingKind.gallery: ("klantwerk", "samenwerkingen"),
    OfferingKind.project: ("klantwerk", "samenwerkingen"),
}


def infer_suggested(profile: Profile) -> list[str]:
    """Voorgestelde openness-slugs uit de werk-items van het profiel (zero-AI).

    Puur in-memory op de al-geladen ``offerings``; in canonieke volgorde. Een maker
    met workshops → trainingen/spreken, met publicaties → interviews, enz. Bedoeld
    als zachte hint in de editor (jij beslist), niet als automatische keuze.
    """
    hinted: set[str] = set()
    for off in profile.offerings:
        hinted.update(_KIND_HINTS.get(off.kind, ()))
    if profile.needs:
        hinted.add("samenwerkingen")
    return [o.slug for o in OPENNESS if o.slug in hinted]
