"""geo_service — grof + opt-in locatie ("Dichtbij", PRD-samenkomen fase 2).

On-platform, nul externe geocoding: een in-repo tabel (``app/geodata/pc2_centroids.json``
— bewust NIET onder ``app/data``, want dat pad wordt in productie door het
``outbox``-volume overschaduwd) mapt het 2-cijferige postcode-gebied (PC2, bv. "35")
naar een benaderd middelpunt +
regio-label. Een lid geeft optioneel z'n postcode(-begin) op; wij bewaren ALLEEN het
2-cijferige gebied + het middelpunt — nooit het exacte adres. Afstand is haversine in
pure Python (geen dependency) en wordt uitsluitend in grove BANDEN getoond, nooit als
exacte km of coördinaat.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

__all__ = ["Area", "resolve", "lookup", "haversine_km", "band", "MAX_NEARBY_KM"]

_DATA = Path(__file__).resolve().parent.parent / "geodata" / "pc2_centroids.json"

# Voorbij deze afstand noemen we het niet meer "dichtbij" (geen band).
MAX_NEARBY_KM = 50.0


@dataclass(frozen=True)
class Area:
    """Een grof locatie-gebied: het 2-cijferige postcode-gebied + middelpunt."""

    code: str  # "35"
    label: str  # "Utrecht e.o."
    lat: float
    lng: float


@lru_cache(maxsize=1)
def _table() -> dict[str, dict]:
    """De PC2-tabel (lazy geladen + gecachet). Sla de ``_comment``-sleutel over."""
    with _DATA.open(encoding="utf-8") as fh:
        raw = json.load(fh)
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def _to_pc2(raw: str | None) -> str | None:
    """Reduceer een postcode-achtige invoer tot het 2-cijferige gebied.

    "3511 AB" / "3511" / "35" / " 35 " → "35". Minder dan 2 cijfers → ``None``.
    We negeren alles behalve de eerste twee cijfers (grof + privacy: het exacte
    adres bereikt de opslag nooit)."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)[:2]
    return digits if len(digits) == 2 else None


def lookup(code: str | None) -> Area | None:
    """Zoek een gebied op z'n 2-cijferige code, of ``None`` als het niet bestaat."""
    if not code or len(code) != 2:
        return None
    row = _table().get(code)
    if row is None:
        return None
    return Area(code=code, label=row["label"], lat=row["lat"], lng=row["lng"])


def resolve(raw: str | None) -> Area | None:
    """Interpreteer vrije postcode-invoer als een grof gebied (of ``None``)."""
    return lookup(_to_pc2(raw))


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Groot-cirkel-afstand in kilometers tussen twee punten (pure Python)."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def band(km: float | None) -> str | None:
    """Grove afstandsband (nooit exacte km): '<25 km' / '~25–50 km' / ``None`` (verder).

    ``None`` bij een niet-berekenbare of te-verre afstand → dan tonen we geen
    dichtbij-label (het lid doet volwaardig mee via de interesse-graaf)."""
    if km is None:
        return None
    if km < 25:
        return "<25 km"
    if km <= MAX_NEARBY_KM:
        return "~25–50 km"
    return None
