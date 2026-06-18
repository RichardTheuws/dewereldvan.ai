"""Groep-invite-service — één actieve, herroepbare WhatsApp-uitnodigingslink.

PRD-verificatie-links §0 (vereenvoudigde richting):
- ``generate``: revoke alle bestaande actieve invites + maak een nieuwe met een
  high-entropy token en 24u TTL. Geauditeerd. Eén ACTIEVE link tegelijk.
- ``active_invite``: de huidige geldige (niet-verlopen, niet-revoked) link, voor
  de admin-weergave.
- ``validate``: geldig token (bestaat + niet-verlopen + niet-revoked), voor de
  publieke landing/registratie-poort.

Het token zit per ontwerp in een gedeelde URL (rondgaand in de groep). Korte TTL
+ herroepbaarheid (regenereren doodt een gelekte link) zijn de leak-controle; de
grant is uitsluitend "word approved lid + bouw profiel", nooit role-escalatie.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import AuditAction, AuditLog, GroupInvite, Member
from app.security import naive_utc, utcnow

# Geldigheid van een verse invite (PRD §0: 24 uur).
INVITE_TTL = timedelta(hours=24)
# Aantal random bytes achter het token (→ ~43-char URL-safe string).
_TOKEN_BYTES = 32


def generate(
    db: Session, admin: Member, *, now: datetime | None = None
) -> GroupInvite:
    """Roteer de actieve link: revoke alle bestaande, maak één verse (24u TTL).

    Schrijft één ``invite_generated``-auditrij (actor = de admin). Het oude token
    wordt zo onbruikbaar — exact de "een admin kan een gelekte link doden"-grond.
    """
    now = now or utcnow()
    now_naive = naive_utc(now)

    # Dood elke nog-actieve link in één statement (revoke = leak-control).
    db.execute(
        update(GroupInvite)
        .where(GroupInvite.revoked.is_(False))
        .values(revoked=True)
    )

    invite = GroupInvite(
        token=secrets.token_urlsafe(_TOKEN_BYTES),
        expires_at=now_naive + INVITE_TTL,
        created_by=admin.id,
        revoked=False,
    )
    db.add(invite)
    db.flush()

    db.add(
        AuditLog(
            action=AuditAction.invite_generated,
            actor_member_id=admin.id,
            target_member_id=None,
            detail="groep-invite gegenereerd (24u)",
        )
    )
    db.flush()
    return invite


def active_invite(
    db: Session, *, now: datetime | None = None
) -> GroupInvite | None:
    """De huidige geldige link: nieuwste niet-verlopen, niet-revoked rij."""
    now_naive = naive_utc(now or utcnow())
    return db.scalar(
        select(GroupInvite)
        .where(
            GroupInvite.revoked.is_(False),
            GroupInvite.expires_at > now_naive,
        )
        .order_by(GroupInvite.created_at.desc(), GroupInvite.id.desc())
        .limit(1)
    )


def validate(
    db: Session, token: str, *, now: datetime | None = None
) -> GroupInvite | None:
    """De invite voor ``token`` als die geldig is, anders ``None``.

    Geldig = bestaat + niet-revoked + niet-verlopen. Een leeg/onbekend token
    geeft ``None`` (de route toont dan de nette "verlopen of ongeldig"-pagina,
    nooit een stacktrace).
    """
    if not token:
        return None
    now_naive = naive_utc(now or utcnow())
    return db.scalar(
        select(GroupInvite).where(
            GroupInvite.token == token,
            GroupInvite.revoked.is_(False),
            GroupInvite.expires_at > now_naive,
        )
    )
