"""Notificatie-dispatcher — push náást de in-app pull-chip (lid-gekozen kanaal).

AUGMENT, geen tweede notificatie-systeem: de in-app-chips blijven state-derived
(nudge_service) en dekken het ``in_app``-kanaal volledig. Deze service voegt een
**push** toe naar het door het lid gekozen kanaal (Telegram eerst, uitbreidbaar).
``notify(db, member, n)`` pusht alleen als het lid een verifieerd push-kanaal koos;
bij ``in_app`` (default) is het een no-op (de pull-chip dekt 't al). Best-effort:
een notificatie faalt nooit hard en blokkeert nooit de aanroeper.

Geen e-mail (bewust): e-mail blijft alléén voor de magic-link. Zie
``docs/PRD-notificaties.md`` + memory [[dewereldvan-notificaties]].
"""

from __future__ import annotations

import html
import logging
import secrets
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Member, MemberChannel, NotificationPref
from app.security import naive_utc, utcnow
from app.services import telegram_service

logger = logging.getLogger(__name__)

CHANNEL_IN_APP = "in_app"
CHANNEL_TELEGRAM = "telegram"

__all__ = [
    "Notification",
    "CHANNEL_IN_APP",
    "CHANNEL_TELEGRAM",
    "notify",
    "notify_admins",
    "preferred_channel",
    "set_preference",
    "telegram_status",
    "begin_telegram_link",
    "link_telegram_from_start",
    "unlink_telegram",
]


@dataclass(frozen=True)
class Notification:
    """Eén te bezorgen seintje. ``url`` mag relatief zijn (wordt geabsoluteerd);
    ``action_label`` is het label van de tikbare knop bij een push (Telegram)."""

    kind: str
    title: str
    body: str
    url: str | None = None
    action_label: str = "Bekijk"


# --------------------------------------------------------------------------- #
# Voorkeur                                                                     #
# --------------------------------------------------------------------------- #


def preferred_channel(db: Session, member: Member) -> str:
    pref = db.get(NotificationPref, member.id)
    return pref.channel if pref is not None else CHANNEL_IN_APP


def set_preference(db: Session, member: Member, channel: str) -> str:
    """Zet het voorkeurskanaal. Telegram alleen als 't gekoppeld+verifieerd is;
    onbekend/onbeschikbaar → valt terug op ``in_app``. Returnt het gezette kanaal."""
    if channel == CHANNEL_TELEGRAM and _verified_telegram(db, member) is None:
        channel = CHANNEL_IN_APP
    if channel not in (CHANNEL_IN_APP, CHANNEL_TELEGRAM):
        channel = CHANNEL_IN_APP
    pref = db.get(NotificationPref, member.id)
    if pref is None:
        db.add(NotificationPref(member_id=member.id, channel=channel))
    else:
        pref.channel = channel
    db.flush()
    return channel


# --------------------------------------------------------------------------- #
# Telegram koppelen                                                            #
# --------------------------------------------------------------------------- #


def _get_channel(db: Session, member_id: int, channel: str) -> MemberChannel | None:
    return db.scalar(
        select(MemberChannel).where(
            MemberChannel.member_id == member_id, MemberChannel.channel == channel
        )
    )


def _verified_telegram(db: Session, member: Member) -> MemberChannel | None:
    ch = _get_channel(db, member.id, CHANNEL_TELEGRAM)
    return ch if (ch is not None and ch.is_verified) else None


def telegram_status(db: Session, member: Member) -> str:
    """``"linked"`` (verifieerd) | ``"pending"`` (link-token uit) | ``"none"``."""
    ch = _get_channel(db, member.id, CHANNEL_TELEGRAM)
    if ch is None:
        return "none"
    if ch.is_verified:
        return "linked"
    return "pending"


def begin_telegram_link(db: Session, member: Member) -> str | None:
    """Maak/refresh een link-token en geef de deep-link terug (of None als de bot
    nog niet geconfigureerd is). De caller commit."""
    if not telegram_service.configured():
        return None
    token = secrets.token_urlsafe(24)
    ch = _get_channel(db, member.id, CHANNEL_TELEGRAM)
    if ch is None:
        ch = MemberChannel(member_id=member.id, channel=CHANNEL_TELEGRAM)
        db.add(ch)
    ch.address = None
    ch.verified_at = None
    ch.link_token = token
    db.flush()
    return telegram_service.link_url(token)


def link_telegram_from_start(db: Session, token: str, chat_id: str) -> bool:
    """Koppel een chat_id aan het lid dat bij ``token`` hoort (webhook). De caller commit."""
    if not token or not chat_id:
        return False
    ch = db.scalar(select(MemberChannel).where(MemberChannel.link_token == token))
    if ch is None:
        return False
    ch.address = chat_id
    ch.verified_at = naive_utc(utcnow())
    ch.link_token = None
    # Koppelen ÍS opt-in: wie de moeite neemt Telegram te verbinden, wil daar z'n
    # seintjes — zet het voorkeurskanaal meteen op telegram (omkeerbaar in het paneel).
    pref = db.get(NotificationPref, ch.member_id)
    if pref is None:
        db.add(NotificationPref(member_id=ch.member_id, channel=CHANNEL_TELEGRAM))
    else:
        pref.channel = CHANNEL_TELEGRAM
    db.flush()
    return True


def unlink_telegram(db: Session, member: Member) -> None:
    """Ontkoppel Telegram en val terug op in-app als dat het voorkeurskanaal was."""
    ch = _get_channel(db, member.id, CHANNEL_TELEGRAM)
    if ch is not None:
        db.delete(ch)
    pref = db.get(NotificationPref, member.id)
    if pref is not None and pref.channel == CHANNEL_TELEGRAM:
        pref.channel = CHANNEL_IN_APP
    db.flush()


# --------------------------------------------------------------------------- #
# Dispatch                                                                     #
# --------------------------------------------------------------------------- #


def _absolute(url: str | None) -> str | None:
    if not url:
        return None
    if url.startswith(("http://", "https://")):
        return url
    return f"{settings.base_url.rstrip('/')}/{url.lstrip('/')}"


def _html_text(notif: Notification) -> str:
    """Rich Telegram-tekst: vette titel + body (HTML-escaped tegen injectie)."""
    title = html.escape(notif.title.strip())
    body = html.escape(notif.body.strip())
    return f"<b>{title}</b>\n\n{body}" if body else f"<b>{title}</b>"


def notify(db: Session, member: Member, notif: Notification) -> None:
    """Push het seintje naar het voorkeurskanaal van het lid (best-effort).

    ``in_app`` (default) → no-op: de state-derived pull-chip dekt 't al. Een
    verifieerd push-kanaal (Telegram) → stuur een rich bericht (vette titel + een
    tikbare knop naar de actie). Faalt nooit hard.
    """
    try:
        if preferred_channel(db, member) != CHANNEL_TELEGRAM:
            return  # in-app pull-chip dekt 't
        ch = _verified_telegram(db, member)
        if ch is None or not ch.address:
            return
        url = _absolute(notif.url)
        telegram_service.send_message(
            ch.address,
            _html_text(notif),
            button_text=notif.action_label if url else None,
            button_url=url,
        )
    except Exception:  # noqa: BLE001 — een seintje mag de aanroeper nooit breken
        logger.warning("notify faalde voor member %s (%s)", member.id, notif.kind, exc_info=True)


def notify_admins(db: Session, notif: Notification) -> None:
    """Push een admin-seintje naar de Telegram van élke admin (best-effort).

    Admin-communicatie loopt via **Telegram**, niet e-mail (operator-voorkeur):
    een directe push naar het geverifieerde Telegram-kanaal van elke admin,
    ongeacht hun persoonlijke voorkeurskanaal. Een admin zonder gekoppelde
    Telegram krijgt geen push — de queue blijft sowieso de bron van waarheid.
    Faalt nooit hard (mag de aanroeper, bv. registratie, nooit breken).
    """
    admin_emails = settings.admin_email_set
    if not admin_emails:
        return
    admins = db.scalars(
        select(Member).where(Member.email.in_(admin_emails))
    ).all()
    url = _absolute(notif.url)
    for admin in admins:
        try:
            ch = _verified_telegram(db, admin)
            if ch is None or not ch.address:
                continue
            telegram_service.send_message(
                ch.address,
                _html_text(notif),
                button_text=notif.action_label if url else None,
                button_url=url,
            )
        except Exception:  # noqa: BLE001 — admin-seintje mag de flow nooit breken
            logger.warning("admin-notify faalde voor member %s", admin.id, exc_info=True)
