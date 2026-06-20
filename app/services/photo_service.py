"""Profielfoto-service (L1) — orchestratie, rate-limit, AVG-spoor, fallback.

De low-level pijplijn (validatie, Pillow-resize/EXIF-strip, opslag, verwijder)
leeft in ``app/storage/photos.py`` en wordt hier her-geëxporteerd zodat
aanroepers één importpunt hebben. Deze module voegt toe:

- ``store_member_photo``  : volledige upload-pijplijn voor één lid.
- ``check_photo_rate_limit``/``record_photo_upload`` : per-lid uur-budget +
  AVG-spoor bovenop ``AuditLog`` (``AuditAction.photo_uploaded``), exact het
  ``magic_link._recent_count``-patroon (geen aparte upload-tabel).
- ``photo_or_initials``   : fallback-keten foto → AI-cover → initialen.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AuditAction, AuditLog
from app.security import naive_utc, utcnow

# Her-export van de low-level FOUNDATION/storage-laag (één importpunt).
from app.storage.photos import (
    UPLOAD_DIR,
    UploadError,
    delete_photo,
    process_image,
    save_logo,
    save_photo,
    save_screenshot,
    storage_name,
    validate_upload,
)

__all__ = [
    "UPLOAD_DIR",
    "UploadError",
    "PhotoRateLimited",
    "validate_upload",
    "process_image",
    "save_photo",
    "save_screenshot",
    "save_logo",
    "delete_photo",
    "storage_name",
    "store_member_photo",
    "check_photo_rate_limit",
    "record_photo_upload",
    "photo_or_initials",
]


class PhotoRateLimited(RuntimeError):
    """Te veel foto-uploads voor dit lid binnen het glijdende uur-venster."""


# --- Rate-limit (op AuditLog, geen aparte tabel) --------------------------


def check_photo_rate_limit(
    db: Session, member_id: int, *, now: datetime | None = None
) -> None:
    """Raise ``PhotoRateLimited`` als het lid het uur-budget heeft verbruikt.

    Telt ``AuditLog``-rijen (``action=photo_uploaded``, ``target_member_id``)
    binnen het laatste uur — exact het ``magic_link._recent_count``-patroon.
    """
    now = now or utcnow()
    window_start = naive_utc(now) - timedelta(hours=1)
    count = (
        db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.action == AuditAction.photo_uploaded,
                AuditLog.target_member_id == member_id,
                AuditLog.created_at >= window_start,
            )
        )
        or 0
    )
    if count >= settings.rate_limit_photo_per_hour:
        raise PhotoRateLimited()


def record_photo_upload(
    db: Session, member_id: int, *, actor_member_id: int | None = None
) -> None:
    """Schrijf het AVG-spoor van een geslaagde foto-upload (+ rate-limit-rij).

    ``actor_member_id`` defaultt naar ``member_id`` (het lid wijzigt zijn eigen
    foto). De rij voedt tegelijk ``check_photo_rate_limit``.
    """
    db.add(
        AuditLog(
            action=AuditAction.photo_uploaded,
            actor_member_id=(
                actor_member_id if actor_member_id is not None else member_id
            ),
            target_member_id=member_id,
            detail="photo_uploaded",
        )
    )
    db.flush()


# --- Volledige upload-pijplijn --------------------------------------------


def store_member_photo(
    db: Session,
    *,
    member_id: int,
    raw: bytes,
    filename: str,
    content_type: str,
    old_photo_url: str | None = None,
    now: datetime | None = None,
) -> str:
    """Volledige upload-pijplijn voor één lid; retourneert de nieuwe ``photo_url``.

    Volgorde: rate-limit → pre-validatie → Pillow-verwerking + opslag → oude
    foto opruimen (geen wees-bestanden) → AVG-spoor schrijven. Raisen:
    ``PhotoRateLimited`` (budget op), ``UploadError`` (ongeldig type/grootte/
    afbeelding). De caller (route) zet ``profile.photo_url`` op de teruggegeven
    waarde en commit.
    """
    check_photo_rate_limit(db, member_id, now=now)
    validate_upload(filename, content_type, len(raw))
    new_url = save_photo(raw, member_id)
    # Pas ná een geslaagde nieuwe save de oude verwijderen (idempotent).
    if old_photo_url and old_photo_url != new_url:
        delete_photo(old_photo_url)
    record_photo_upload(db, member_id)
    return new_url


# --- Fallback-helper ------------------------------------------------------


def photo_or_initials(profile) -> dict:
    """Lever de weergavebron voor een profielfoto met fallback-keten.

    Volgorde (§3.8): geüploade ``photo_url`` → AI-``cover_image_url`` →
    initialen. Retourneert een dict die de template direct kan gebruiken:
    ``{"kind": "photo"|"cover"|"initials", "url": str|None, "initials": str}``.
    """
    initials = _initials(getattr(profile, "display_name", "") or "")
    if getattr(profile, "photo_url", None):
        return {"kind": "photo", "url": profile.photo_url, "initials": initials}
    if getattr(profile, "cover_image_url", None):
        return {"kind": "cover", "url": profile.cover_image_url, "initials": initials}
    return {"kind": "initials", "url": None, "initials": initials}


def _initials(name: str) -> str:
    """Tot twee hoofdletters uit ``name`` (kosmische initialen-fallback)."""
    parts = [p for p in name.strip().split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()
