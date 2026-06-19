"""Profielfoto-opslag (L1) — validatie, Pillow-verwerking, opslag (SERVICES-gevuld).

FOUNDATION leverde de publieke signatures, de pad-helpers (anti-traversal) en
``UploadError``; SERVICES vult hier de bodies met Pillow (decode → EXIF-strip →
square-crop → resize → WEBP). De rate-limit + AVG-spoor + orchestratie leeft in
``app/services/photo_service.py`` (bovenop ``AuditLog``).

Echte poort = de server-hervalidatie hier (Content-Type is spoofbaar). Het
client-filename wordt volledig genegeerd: de opslagnaam is willekeurig
(``<member_id>-<token_hex>.webp``) zodat path-traversal onmogelijk is.

Serving: de app mount ``UPLOAD_DIR`` op ``settings.upload_url_prefix`` als
StaticFiles (zie ``app/main.py``); ``photo_url`` is relatief (``/uploads/<naam>``).
"""

from __future__ import annotations

import secrets
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import settings


class UploadError(ValueError):
    """Nette 400-melding richting de UI (ongeldig type/grootte/afbeelding)."""


# Absolute basis-dir voor opslag; resolved zodat de anti-traversal-guard
# (`is_relative_to`) tegen een stabiel pad vergelijkt.
UPLOAD_DIR: Path = Path(settings.upload_dir).resolve()


def _abs_path(name: str) -> Path:
    """Join ``name`` op ``UPLOAD_DIR`` en garandeer dat het binnen blijft.

    Harde anti-traversal-guard: ``(UPLOAD_DIR / name).resolve()`` moet onder
    ``UPLOAD_DIR`` liggen, anders ``UploadError``. Voorkomt ``../etc/x`` e.d.,
    ook als een aanroeper per ongeluk een niet-gegenereerde naam doorgeeft.
    """
    candidate = (UPLOAD_DIR / name).resolve()
    if not candidate.is_relative_to(UPLOAD_DIR):
        raise UploadError("Ongeldig opslagpad.")
    return candidate


def storage_name(member_id: int) -> str:
    """Willekeurige, traversal-veilige opslagnaam (``<id>-<hex>.webp``).

    Het client-filename wordt genegeerd; geen ``/`` of ``..`` mogelijk.
    """
    return f"{member_id}-{secrets.token_hex(8)}.webp"


def validate_upload(filename: str, content_type: str, size: int) -> None:
    """Goedkope pre-checks (type/grootte) vóór de Pillow-revalidatie.

    Raise ``UploadError`` bij een niet-toegestaan mimetype, bij een leeg
    bestand, of bij ``size > settings.max_upload_bytes``. Content-Type is
    spoofbaar → de echte poort is ``process_image`` (Pillow ``verify()``).
    ``filename`` wordt niet vertrouwd (de opslagnaam is willekeurig).
    """
    ctype = (content_type or "").split(";", 1)[0].strip().lower()
    if ctype not in settings.allowed_image_type_set:
        raise UploadError(
            "Alleen JPEG-, PNG- of WEBP-afbeeldingen zijn toegestaan."
        )
    if size <= 0:
        raise UploadError("Het bestand is leeg.")
    if size > settings.max_upload_bytes:
        mb = settings.max_upload_bytes // (1024 * 1024)
        raise UploadError(f"De afbeelding is te groot (max {mb} MB).")


def process_image(raw: bytes) -> bytes:
    """Decode → EXIF-strip → vierkante crop → resize → WEBP-bytes.

    Honoreert eerst de EXIF-oriëntatie (``exif_transpose``) en dropt dáárna
    alle metadata via ``convert("RGB")`` + een verse ``save`` (geen EXIF/GPS in
    de output — AVG). ``ImageOps.fit`` doet een vierkante center-crop naar
    ``settings.photo_output_px``. Ongeldige/corrupte bytes → ``UploadError``.
    """
    px = settings.photo_output_px

    # Eerst hard valideren met een wegwerp-decode: ``verify()`` consumeert de
    # stream, dus daarna opnieuw openen voor de echte verwerking.
    try:
        probe = Image.open(BytesIO(raw))
        probe.verify()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        raise UploadError("Geen geldige afbeelding.") from exc

    try:
        img = Image.open(BytesIO(raw))
        img = ImageOps.exif_transpose(img)  # honoreer oriëntatie vóór strip
        img = img.convert("RGB")  # dropt alpha + ALLE EXIF/GPS-metadata (AVG)
        img = ImageOps.fit(img, (px, px), Image.LANCZOS)  # vierkante center-crop
        out = BytesIO()
        img.save(out, format="WEBP", quality=82, method=6)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise UploadError("Geen geldige afbeelding.") from exc

    return out.getvalue()


def save_photo(raw: bytes, member_id: int) -> str:
    """Verwerk + schrijf de foto weg; retourneer de publieke URL.

    Schrijft de verwerkte WEBP-bytes naar een willekeurige, traversal-veilige
    naam onder ``UPLOAD_DIR`` en retourneert het relatieve serveer-pad
    (``f"{settings.upload_url_prefix}/{naam}"``).
    """
    data = process_image(raw)
    name = storage_name(member_id)
    path = _abs_path(name)  # anti-traversal-guard
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return f"{settings.upload_url_prefix}/{name}"


def save_screenshot(raw: bytes, offering_id: int) -> str | None:
    """Verwerk + schrijf een project-screenshot weg; retourneer het serveer-pad.

    Anders dan ``save_photo`` (vierkante avatar-crop): een screenshot-hero is
    landschap. We schalen naar max 1200px breed (aspect behouden), strippen alle
    metadata via ``convert("RGB")`` en bewaren als WEBP onder ``UPLOAD_DIR`` met
    een willekeurige, traversal-veilige naam. Ongeldige bytes → ``None`` (de
    enrich-laag is best-effort; nooit crashen op een rare render).
    """
    try:
        img = Image.open(BytesIO(raw))
        img = img.convert("RGB")  # dropt alpha + metadata
        max_w = 1200
        if img.width > max_w:
            h = round(img.height * (max_w / img.width))
            img = img.resize((max_w, h), Image.LANCZOS)
        out = BytesIO()
        img.save(out, format="WEBP", quality=82, method=6)
    except (UnidentifiedImageError, OSError, ValueError):
        return None
    name = f"proj-{offering_id}-{secrets.token_hex(8)}.webp"
    path = _abs_path(name)  # anti-traversal-guard
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path.write_bytes(out.getvalue())
    return f"{settings.upload_url_prefix}/{name}"


def delete_photo(photo_url: str | None) -> None:
    """Verwijder het bestand achter ``photo_url`` (idempotent, AVG).

    Leidt de bestandsnaam af uit het laatste pad-segment, valideert die via
    ``_abs_path`` (anti-traversal) en verwijdert het bestand binnen
    ``UPLOAD_DIR``. ``None``/lege/onbekende URL = no-op.
    """
    if not photo_url:
        return
    name = photo_url.rstrip("/").rsplit("/", 1)[-1]
    if not name:
        return
    try:
        path = _abs_path(name)
    except UploadError:
        # Een URL die buiten UPLOAD_DIR zou wijzen raken we niet aan.
        return
    path.unlink(missing_ok=True)
