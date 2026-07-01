"""Profielfoto-pijplijn (L1) — validatie, Pillow-resize/EXIF-strip, opslag, rate-limit.

Volledig in-memory: afbeeldingen worden met Pillow gegenereerd (geen fixtures op
schijf, geen netwerk), opslag gaat naar de wegwerp-``UPLOAD_DIR`` uit conftest.
De echte poort is de server-hervalidatie (Content-Type is spoofbaar) + de
EXIF/GPS-strip (AVG); beide worden hier hard bewezen.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from app.config import settings
from app.models import AuditAction, AuditLog
from app.services import photo_service
from app.storage import photos
from PIL import Image
from PIL.ExifTags import Base as ExifBase


# --------------------------------------------------------------------------- #
# Helpers — in-memory afbeeldingen                                            #
# --------------------------------------------------------------------------- #
def _png_bytes(size=(800, 600), color=(10, 120, 200)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_with_exif(size=(640, 480)) -> bytes:
    """Een JPEG mét EXIF (oriëntatie + camera-make), om de privacy-strip te bewijzen.

    De aanwezigheid van willekeurige EXIF-tags volstaat: ``process_image`` moet
    álle metadata droppen (AVG — camera/locatie/oriëntatie verdwijnen), dus na
    verwerking mag het EXIF-blok volledig leeg zijn.
    """
    img = Image.new("RGB", size, (200, 60, 60))
    exif = img.getexif()
    exif[ExifBase.Orientation.value] = 6  # 90° rotatie-vlag
    exif[ExifBase.Make.value] = "TestCam"  # herkenbare, identificerende tag
    buf = BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# validate_upload — goedkope pre-checks                                       #
# --------------------------------------------------------------------------- #
def test_validate_rejects_non_image_content_type():
    with pytest.raises(photo_service.UploadError):
        photos.validate_upload("x.txt", "text/plain", 100)


def test_validate_rejects_empty_file():
    with pytest.raises(photo_service.UploadError):
        photos.validate_upload("x.png", "image/png", 0)


def test_validate_rejects_oversized():
    too_big = settings.max_upload_bytes + 1
    with pytest.raises(photo_service.UploadError):
        photos.validate_upload("x.jpg", "image/jpeg", too_big)


def test_validate_accepts_allowed_type_and_size():
    # Geen exception = geslaagd.
    photos.validate_upload("x.webp", "image/webp", 1234)


# --------------------------------------------------------------------------- #
# process_image — de echte poort: Pillow-verify + resize + EXIF-strip         #
# --------------------------------------------------------------------------- #
def test_process_rejects_corrupt_bytes():
    """Gespoofte Content-Type maar geen geldige afbeelding → UploadError."""
    with pytest.raises(photo_service.UploadError):
        photos.process_image(b"this is not an image at all")


def test_process_outputs_square_webp_at_configured_size():
    out = photos.process_image(_png_bytes(size=(800, 600)))
    img = Image.open(BytesIO(out))
    assert img.format == "WEBP"
    px = settings.photo_output_px
    assert img.size == (px, px)  # vierkante center-crop


def test_process_strips_all_exif():
    """AVG: geen EXIF in de output (camera/oriëntatie/locatie weg)."""
    out = photos.process_image(_jpeg_with_exif())
    img = Image.open(BytesIO(out))
    # WEBP-output mag geen EXIF-blok dragen na convert("RGB") + verse save.
    assert img.getexif().get(ExifBase.Make.value) is None
    assert not dict(img.getexif())  # volledig leeg EXIF


# --------------------------------------------------------------------------- #
# storage_name + _abs_path — anti-traversal                                   #
# --------------------------------------------------------------------------- #
def test_storage_name_is_traversal_safe_and_webp():
    name = photos.storage_name(42)
    assert "/" not in name and ".." not in name
    assert name.startswith("42-")
    assert name.endswith(".webp")


def test_storage_name_is_random_per_call():
    assert photos.storage_name(7) != photos.storage_name(7)


def test_abs_path_blocks_traversal():
    with pytest.raises(photo_service.UploadError):
        photos._abs_path("../etc/passwd")


# --------------------------------------------------------------------------- #
# save_photo / delete_photo — round-trip op de tmpdir                         #
# --------------------------------------------------------------------------- #
def test_save_and_delete_photo_round_trip():
    url = photos.save_photo(_png_bytes(), member_id=99)
    assert url.startswith(settings.upload_url_prefix + "/")
    name = url.rsplit("/", 1)[-1]
    path = photos._abs_path(name)
    assert path.exists()
    # Het weggeschreven bestand is geldige WEBP.
    assert Image.open(path).format == "WEBP"

    photos.delete_photo(url)
    assert not path.exists()


def test_delete_photo_is_idempotent_and_noop_on_none():
    # None / lege / onbekende URL = no-op, geen exception.
    photos.delete_photo(None)
    photos.delete_photo("")
    photos.delete_photo("/uploads/does-not-exist.webp")


def test_delete_photo_ignores_paths_outside_upload_dir():
    # Een URL die buiten UPLOAD_DIR zou wijzen raken we niet aan (geen crash).
    photos.delete_photo("/uploads/../../etc/passwd")


# --------------------------------------------------------------------------- #
# Rate-limit — op AuditLog (geen aparte tabel)                                #
# --------------------------------------------------------------------------- #
def test_rate_limit_passes_below_budget(db, make_member):
    member = make_member(email="shutter@example.com")
    # Onder het uur-budget → geen exception.
    photo_service.check_photo_rate_limit(db, member.id)


def test_rate_limit_trips_after_budget(db, make_member, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_photo_per_hour", 2)
    member = make_member(email="burst@example.com")
    for _ in range(2):
        photo_service.record_photo_upload(db, member.id)
    with pytest.raises(photo_service.PhotoRateLimited):
        photo_service.check_photo_rate_limit(db, member.id)


def test_record_photo_upload_writes_avg_audit_row(db, make_member):
    from sqlalchemy import func, select

    member = make_member(email="trace@example.com")
    photo_service.record_photo_upload(db, member.id)
    count = db.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(
            AuditLog.action == AuditAction.photo_uploaded,
            AuditLog.target_member_id == member.id,
        )
    )
    assert count == 1


def test_store_member_photo_full_pipeline(db, make_member):
    """rate-limit → validatie → resize/opslag → AVG-spoor, end-to-end."""
    member = make_member(email="full@example.com")
    url = photo_service.store_member_photo(
        db,
        member_id=member.id,
        raw=_png_bytes(),
        filename="vakantie.png",
        content_type="image/png",
        old_photo_url=None,
    )
    assert url.startswith(settings.upload_url_prefix + "/")
    name = url.rsplit("/", 1)[-1]
    assert Image.open(photos._abs_path(name)).format == "WEBP"
    # AVG-spoor geschreven → rate-limit-grondslag bestaat.
    from sqlalchemy import func, select

    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == AuditAction.photo_uploaded)
        )
        == 1
    )


def test_store_member_photo_rejects_non_image(db, make_member):
    member = make_member(email="bad@example.com")
    with pytest.raises(photo_service.UploadError):
        photo_service.store_member_photo(
            db,
            member_id=member.id,
            raw=b"not-an-image",
            filename="evil.png",
            content_type="image/png",
        )


# --------------------------------------------------------------------------- #
# photo_or_initials — fallback-keten                                          #
# --------------------------------------------------------------------------- #
def test_fallback_prefers_photo_over_cover(db, make_member, make_profile):
    member = make_member(email="hero@example.com", name="Sterre Licht")
    profile = make_profile(member)
    profile.cover_image_url = "/uploads/cover.webp"
    profile.photo_url = "/uploads/face.webp"
    out = photo_service.photo_or_initials(profile)
    assert out["kind"] == "photo"
    assert out["url"] == "/uploads/face.webp"


def test_fallback_uses_cover_when_no_photo(db, make_member, make_profile):
    member = make_member(email="cov@example.com", name="Maan Schijn")
    profile = make_profile(member)
    profile.cover_image_url = "/uploads/cover.webp"
    out = photo_service.photo_or_initials(profile)
    assert out["kind"] == "cover"


def test_fallback_initials_when_nothing(db, make_member, make_profile):
    member = make_member(email="ini@example.com", name="Nova Bright")
    profile = make_profile(member)
    out = photo_service.photo_or_initials(profile)
    assert out["kind"] == "initials"
    assert out["initials"] == "NB"


# --------------------------------------------------------------------------- #
# Video-hero (mp4) — validatie + opslag                                        #
# --------------------------------------------------------------------------- #
_MP4 = b"\x00\x00\x00\x18ftypmp42isom" + b"\x00" * 40


def test_validate_video_ok():
    photos.validate_video_upload("video/mp4", len(_MP4), _MP4)  # geen exception


def test_validate_video_rejects_wrong_type():
    with pytest.raises(photos.UploadError):
        photos.validate_video_upload("video/quicktime", len(_MP4), _MP4)


def test_validate_video_rejects_missing_ftyp():
    bad = b"\x00" * 40
    with pytest.raises(photos.UploadError):
        photos.validate_video_upload("video/mp4", len(bad), bad)


def test_validate_video_rejects_too_large():
    big = settings.max_video_bytes + 1
    with pytest.raises(photos.UploadError):
        photos.validate_video_upload("video/mp4", big, _MP4)


def test_save_cover_video_writes_and_returns_url():
    url = photos.save_cover_video(_MP4, member_id=99)
    assert url.endswith(".mp4") and url.startswith(settings.upload_url_prefix)
    # Bestand staat er echt (in de wegwerp-UPLOAD_DIR).
    name = url.rsplit("/", 1)[-1]
    assert (photos.UPLOAD_DIR / name).read_bytes() == _MP4
