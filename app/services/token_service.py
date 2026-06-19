"""Personal-token-service (MCP-server) — uitgeven, verifiëren, intrekken.

Spiegelt het magic-link-hashpatroon: de ruwe token (prefix ``dwv_``) wordt één
keer teruggegeven en NOOIT opgeslagen; alleen ``hash_token(raw)`` gaat de DB in.
``resolve`` is het auth-pad van de MCP-server: ruwe Bearer-token → goedgekeurd lid
(of ``None``), met bijwerken van ``last_used_at``.
"""

from __future__ import annotations

import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Member, MemberStatus
from app.models.personal_token import PersonalToken
from app.security import hash_token, naive_utc, utcnow

__all__ = ["generate", "resolve", "list_for_member", "revoke", "TOKEN_PREFIX"]

TOKEN_PREFIX = "dwv_"


def generate(db: Session, member: Member, *, label: str = "") -> tuple[str, PersonalToken]:
    """Geef een nieuw token uit. Retourneert (ruwe_token, rij). De ruwe token wordt
    één keer aan het lid getoond; alleen de hash wordt bewaard."""
    raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
    token = PersonalToken(
        member_id=member.id,
        token_hash=hash_token(raw),
        label=(label or "").strip()[:80] or "AI-tool",
    )
    db.add(token)
    db.flush()
    return raw, token


def resolve(db: Session, raw: str | None) -> Member | None:
    """Ruwe Bearer-token → goedgekeurd lid, of ``None``.

    Verifieert tegen ``token_hash`` (niet ingetrokken), eist een ``approved`` lid
    (een geschorst lid → dood token), en stempelt ``last_used_at``. De caller
    commit (de MCP-auth-laag doet dat per request)."""
    if not raw or not raw.startswith(TOKEN_PREFIX):
        return None
    row = db.scalar(
        select(PersonalToken).where(
            PersonalToken.token_hash == hash_token(raw),
            PersonalToken.revoked_at.is_(None),
        )
    )
    if row is None:
        return None
    member = db.get(Member, row.member_id)
    if member is None or member.status != MemberStatus.approved:
        return None
    row.last_used_at = naive_utc(utcnow())
    return member


def list_for_member(db: Session, member: Member) -> list[PersonalToken]:
    """Actieve (niet-ingetrokken) tokens van het lid, nieuwste eerst."""
    return list(
        db.scalars(
            select(PersonalToken)
            .where(
                PersonalToken.member_id == member.id,
                PersonalToken.revoked_at.is_(None),
            )
            .order_by(PersonalToken.id.desc())
        )
    )


def revoke(db: Session, token_id: int, member: Member) -> bool:
    """Trek een eigen token in (idempotent). True als er iets is ingetrokken."""
    row = db.get(PersonalToken, token_id)
    if row is None or row.member_id != member.id or row.revoked_at is not None:
        return False
    row.revoked_at = naive_utc(utcnow())
    db.flush()
    return True
