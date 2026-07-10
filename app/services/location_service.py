"""location_service — opt-in grof locatie-gebied op een profiel ("Dichtbij").

Dun laagje bovenop ``geo_service``: een lid zet z'n gebied (uit vrije postcode-
invoer, gereduceerd tot PC2 + middelpunt) of wist het weer. Bewaart NOOIT het
exacte adres — alleen ``area_code``/``area_label``/``area_lat``/``area_lng``.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Profile
from app.services import geo_service

__all__ = ["set_area", "clear_area", "has_area"]


def set_area(db: Session, profile: Profile, raw: str) -> geo_service.Area | None:
    """Zet het grove gebied van ``profile`` uit vrije postcode-invoer.

    Herkent de invoer niet als een NL-postcode(-begin)? Dan raken we niets aan en
    geven ``None`` terug (de router toont een nette hint). Anders schrijven we
    alleen het 2-cijferige gebied + het middelpunt."""
    area = geo_service.resolve(raw)
    if area is None:
        return None
    profile.area_code = area.code
    profile.area_label = area.label
    profile.area_lat = area.lat
    profile.area_lng = area.lng
    db.flush()
    return area


def clear_area(db: Session, profile: Profile) -> None:
    """Wis het locatie-gebied volledig (opt-out, idempotent)."""
    profile.area_code = None
    profile.area_label = None
    profile.area_lat = None
    profile.area_lng = None
    db.flush()


def has_area(profile: Profile | None) -> bool:
    return bool(profile is not None and profile.area_lat is not None and profile.area_lng is not None)
