"""Hero-studio-service — rate-limit, AVG-spoor en URL-validatie voor covers.

De studio laat een lid cover-VARIANTEN genereren (fal.ai), er één kiezen en die
vastzetten. Deze module voegt de niet-AI-orchestratie toe rond ``cover_art_service``
(de prompt) en de ``ImageGenerator`` (het beeld):

- ``check_cover_rate_limit`` / ``record_cover_generation`` : per-lid uur-budget +
  audit-spoor bovenop ``AuditLog`` (``AuditAction.cover_generated``) — exact het
  ``photo_service``-patroon. Telt **per generatie-klik**, niet per beeld. Budget =
  ``rate_limit_ai_enrich_per_hour`` (hergebruikt; covers zijn AI-enrich-werk).
- ``is_trusted_cover_url`` : een gekozen variant-URL moet een https-URL op een
  fal-host zijn (de varianten zijn transient → we slaan alleen vertrouwde URLs op).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AuditAction, AuditLog
from app.security import naive_utc, utcnow

__all__ = [
    "CoverRateLimited",
    "VARIANT_COUNT",
    "check_cover_rate_limit",
    "record_cover_generation",
    "is_trusted_cover_url",
]

# Aantal varianten per generatie-klik (kostencap + fal num_images-grens).
VARIANT_COUNT = 4

# Hosts die fal.ai voor gegenereerde beelden gebruikt. Een gekozen cover-URL moet
# hiervandaan komen (de varianten zijn transient; dit voorkomt dat een lid een
# willekeurige externe URL als cover laat opslaan).
_TRUSTED_HOST_SUFFIXES = (".fal.media", ".fal.ai", ".fal.run")


class CoverRateLimited(RuntimeError):
    """Te veel cover-generaties voor dit lid binnen het glijdende uur-venster."""


def check_cover_rate_limit(
    db: Session, member_id: int, *, now: datetime | None = None
) -> None:
    """Raise ``CoverRateLimited`` als het lid het uur-budget heeft verbruikt.

    Telt ``AuditLog``-rijen (``action=cover_generated``, ``target_member_id``)
    binnen het laatste uur — exact het ``photo_service``-patroon.
    """
    now = now or utcnow()
    window_start = naive_utc(now) - timedelta(hours=1)
    count = (
        db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.action == AuditAction.cover_generated,
                AuditLog.target_member_id == member_id,
                AuditLog.created_at >= window_start,
            )
        )
        or 0
    )
    if count >= settings.rate_limit_ai_enrich_per_hour:
        raise CoverRateLimited()


def record_cover_generation(db: Session, member_id: int) -> None:
    """Schrijf één audit-/rate-limit-rij per cover-generatie-klik."""
    db.add(
        AuditLog(
            action=AuditAction.cover_generated,
            actor_member_id=member_id,
            target_member_id=member_id,
            detail="cover_generated",
        )
    )
    db.flush()


def is_trusted_cover_url(url: str | None) -> bool:
    """True als ``url`` een https-URL op een vertrouwde fal-host is."""
    if not url or not isinstance(url, str):
        return False
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return False
    if parts.scheme != "https" or not parts.hostname:
        return False
    host = parts.hostname.lower()
    return any(
        host == suffix.lstrip(".") or host.endswith(suffix)
        for suffix in _TRUSTED_HOST_SUFFIXES
    )
