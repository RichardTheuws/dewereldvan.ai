"""inquiry_service — vragen van bezoekers aan een lid (PRD hub §4.1).

De eerste weg van buiten naar binnen. **Nul AI** (harde constraint: een bezoeker
triggert nooit betaalde AI). Spam-poort in lagen, goedkoopste eerst:

  1. honeypot-veld gevuld / te snel ingevuld  → stil "verzonden", niets opgeslagen
  2. Turnstile (in de router, net als ``/proef``)
  3. validatie (naam, e-mail, onderwerp, berichtlengte, toestemming)
  4. per-IP-limiet (gezouten hash, nooit het ruwe IP) en per-profiel-limiet
  5. dedupe: dezelfde (e-mail, profiel, bericht) binnen 24u → idempotent, via een
     savepoint op de unique-constraint (zie [[dewereldvan-idempotent-race]])

Bezorging: ``notification_service.notify`` naar het lid-gekozen kanaal (Telegram)
+ de in-app chip (``count_new``). Geen e-mail; het lid antwoordt zelf per mail.
Een aanvraag kan alleen bij een **openbaar** profiel (``visibility.can_view`` met
viewer=None): besloten leden bereik je als lid via de intro's.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Inquiry, InquiryStatus, Member, Profile
from app.security import naive_utc, utcnow
from app.services import notification_service, openness_service
from app.services import visibility as visibility_service

logger = logging.getLogger(__name__)

__all__ = [
    "TOPIC_OTHER",
    "RETENTION_DAYS",
    "SubmitResult",
    "accepts_inquiries",
    "topics_for",
    "submit",
    "list_for_member",
    "count_new",
    "get_for_member",
    "mark_read",
    "set_status",
    "purge_expired",
    "topic_label",
]

TOPIC_OTHER = "anders"
RETENTION_DAYS = 180
MIN_FILL_SECONDS = 3
IP_LIMIT_24H = 5
PROFILE_LIMIT_24H = 20
MESSAGE_MIN = 20
MESSAGE_MAX = 2000

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


@dataclass(frozen=True)
class SubmitResult:
    """Uitkomst van ``submit``.

    ``status``: 'ok' (opgeslagen of idempotent herhaald), 'silent' (bot-signaal:
    toon een bevestiging, sla niets op), 'invalid' (``errors`` per veld),
    'limit' (te veel aanvragen), 'closed' (profiel neemt geen aanvragen aan).
    """

    status: str
    inquiry: Inquiry | None = None
    errors: dict[str, str] = field(default_factory=dict)
    created: bool = False


def accepts_inquiries(profile: Profile) -> bool:
    """Alleen een openbaar zichtbaar profiel van een goedgekeurd lid."""
    return visibility_service.can_view(profile, None)


def topics_for(profile: Profile) -> list[tuple[str, str]]:
    """De onderwerp-keuzes: de ``open_to``-waarden van het lid (alleen als die
    sectie publiek is) + altijd "iets anders"."""
    items: list[tuple[str, str]] = []
    if visibility_service.public_section_visible(profile, "open_to", None):
        items = [(o.slug, o.label) for o in openness_service.labels_for(profile.open_to)]
    items.append((TOPIC_OTHER, "Iets anders"))
    return items


def _ip_hash(ip: str) -> str:
    return hashlib.sha256(f"{settings.secret_key}:inquiry-ip:{ip}".encode()).hexdigest()


def _dedupe_hash(profile_id: int, email: str, message: str, day: str) -> str:
    raw = f"{profile_id}:{email}:{' '.join(message.split()).lower()}:{day}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _validate(
    profile: Profile, name: str, email: str, org: str, topic: str, message: str, consent: bool
) -> dict[str, str]:
    errors: dict[str, str] = {}
    if not (2 <= len(name) <= 120):
        errors["name"] = "Vul je naam in."
    if len(email) > 320 or not _EMAIL_RE.match(email):
        errors["email"] = "Dit lijkt geen geldig e-mailadres."
    if len(org) > 160:
        errors["org"] = "Houd de organisatie korter dan 160 tekens."
    if topic not in {slug for slug, _ in topics_for(profile)}:
        errors["topic"] = "Kies een onderwerp."
    if len(message) < MESSAGE_MIN:
        errors["message"] = f"Vertel iets meer (minstens {MESSAGE_MIN} tekens)."
    elif len(message) > MESSAGE_MAX:
        errors["message"] = f"Houd het onder de {MESSAGE_MAX} tekens."
    if not consent:
        errors["consent"] = "Vink aan dat we je gegevens aan dit lid mogen geven."
    return errors


def submit(
    db: Session,
    profile: Profile,
    *,
    name: str,
    email: str,
    org: str,
    topic: str,
    message: str,
    consent: bool,
    ip: str,
    honeypot: str = "",
    started_at: float | None = None,
    now: datetime | None = None,
) -> SubmitResult:
    """Valideer + sla een aanvraag op en seintje het lid. Commit NIET (de router doet dat)."""
    now_naive = naive_utc(now or utcnow())
    if not accepts_inquiries(profile):
        return SubmitResult(status="closed")

    # 1. Bot-signalen: stil "verzonden" — geen hint voor de bot, niets opgeslagen.
    if honeypot.strip():
        return SubmitResult(status="silent")
    if started_at is not None and (now_naive.timestamp() - started_at) < MIN_FILL_SECONDS:
        return SubmitResult(status="silent")

    name, email, org, message = name.strip(), email.strip().lower(), org.strip(), message.strip()
    topic = topic.strip().lower()
    errors = _validate(profile, name, email, org, topic, message, consent)
    if errors:
        return SubmitResult(status="invalid", errors=errors)

    # 4. Rate-limits (24u-venster, pure telling).
    since = now_naive - timedelta(hours=24)
    ip_hash = _ip_hash(ip)
    by_ip = (
        db.scalar(
            select(func.count(Inquiry.id)).where(
                Inquiry.ip_hash == ip_hash, Inquiry.created_at >= since
            )
        )
        or 0
    )
    by_profile = (
        db.scalar(
            select(func.count(Inquiry.id)).where(
                Inquiry.profile_id == profile.id, Inquiry.created_at >= since
            )
        )
        or 0
    )

    dedupe = _dedupe_hash(profile.id, email, message, now_naive.strftime("%Y-%m-%d"))
    existing = db.scalar(select(Inquiry).where(Inquiry.dedupe_hash == dedupe))
    if existing is not None:
        return SubmitResult(status="ok", inquiry=existing, created=False)
    if by_ip >= IP_LIMIT_24H or by_profile >= PROFILE_LIMIT_24H:
        return SubmitResult(status="limit")

    inquiry = Inquiry(
        member_id=profile.member_id,
        profile_id=profile.id,
        sender_name=name,
        sender_email=email,
        sender_org=org or None,
        topic=topic,
        message=message,
        status=InquiryStatus.new,
        ip_hash=ip_hash,
        dedupe_hash=dedupe,
        created_at=now_naive,
    )
    try:
        with db.begin_nested():
            db.add(inquiry)
            db.flush()
    except IntegrityError:
        # Dubbele submit in een race: de andere request won; dat is dezelfde aanvraag.
        existing = db.scalar(select(Inquiry).where(Inquiry.dedupe_hash == dedupe))
        return SubmitResult(status="ok", inquiry=existing, created=False)

    _notify(db, profile, inquiry)
    return SubmitResult(status="ok", inquiry=inquiry, created=True)


def topic_label(topic: str) -> str:
    for o in openness_service.options():
        if o.slug == topic:
            return o.label
    return "Iets anders"


def _notify(db: Session, profile: Profile, inquiry: Inquiry) -> None:
    member = db.get(Member, profile.member_id)
    if member is None:
        return
    who = inquiry.sender_name + (f" ({inquiry.sender_org})" if inquiry.sender_org else "")
    snippet = inquiry.message if len(inquiry.message) <= 280 else inquiry.message[:277] + "…"
    notification_service.notify(
        db,
        member,
        notification_service.Notification(
            kind="inquiry_received",
            title=f"Nieuwe vraag van {who} · {topic_label(inquiry.topic)}",
            body=snippet,
            url=f"/aanvragen/{inquiry.id}",
            action_label="Lees de vraag",
        ),
    )


# --------------------------------------------------------------------------- #
# Inbox van het lid                                                            #
# --------------------------------------------------------------------------- #
def list_for_member(db: Session, member: Member, *, include_spam: bool = False) -> list[Inquiry]:
    stmt = select(Inquiry).where(Inquiry.member_id == member.id)
    if not include_spam:
        stmt = stmt.where(Inquiry.status != InquiryStatus.spam)
    return list(db.scalars(stmt.order_by(Inquiry.created_at.desc(), Inquiry.id.desc())))


def count_new(db: Session, member: Member) -> int:
    return (
        db.scalar(
            select(func.count(Inquiry.id)).where(
                Inquiry.member_id == member.id, Inquiry.status == InquiryStatus.new
            )
        )
        or 0
    )


def get_for_member(db: Session, member: Member, inquiry_id: int) -> Inquiry | None:
    """Alleen de eigen aanvragen (een ander id → None → 404, geen bestaan-lek)."""
    inquiry = db.get(Inquiry, inquiry_id)
    if inquiry is None or inquiry.member_id != member.id:
        return None
    return inquiry


def mark_read(db: Session, inquiry: Inquiry, now: datetime | None = None) -> None:
    if inquiry.status == InquiryStatus.new:
        inquiry.status = InquiryStatus.read
    if inquiry.read_at is None:
        inquiry.read_at = naive_utc(now or utcnow())
    db.flush()


def set_status(db: Session, inquiry: Inquiry, status: InquiryStatus) -> None:
    inquiry.status = status
    if inquiry.read_at is None:
        inquiry.read_at = naive_utc(utcnow())
    db.flush()


def purge_expired(db: Session, now: datetime | None = None) -> int:
    """Wis aanvragen ouder dan ``RETENTION_DAYS`` (belofte in het toestemmingsvinkje)."""
    cutoff = naive_utc(now or utcnow()) - timedelta(days=RETENTION_DAYS)
    result = db.execute(delete(Inquiry).where(Inquiry.created_at < cutoff))
    return result.rowcount or 0
