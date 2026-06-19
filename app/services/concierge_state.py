"""Concierge conversatie-state (Agent-Shell Fase 1) — platte-tekst helpers.

Bewaart UITSLUITEND platte ``str``-tekst per beurt (geen tool_use/thinking-blokken
cross-turn). Dat is de harde history-discipline die het permanente-400-vergiftigings-
pad voorkomt: een leeg of niet-replaybaar blok mag de Messages-API nooit bereiken.

- ``append_turn`` coerced naar ``str`` én weigert lege/whitespace content (→ ``None``).
- ``load_messages`` filtert lege turns defensief weg (tweede gordel naast de DB-discipline).

Sjabloon: ``ai_conversation``'s turn-helpers, maar met een platte ``content``-kolom
i.p.v. JSON-blokken — de concierge draait custom function-tools, geen webtools.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ConciergeTurn


def append_turn(
    db: Session, member_id: int, role: str, content: object
) -> ConciergeTurn | None:
    """Persisteer één turn als PLATTE TEKST. Lege/whitespace content → geen rij.

    Coerced naar ``str`` zodat per constructie nooit een tool_use/thinking-blok in
    ``concierge_turn`` belandt (cross-turn-replay-invariant). Geeft ``None`` terug
    bij lege content; de caller commit.
    """
    text = content if isinstance(content, str) else str(content)
    text = text.strip()
    if not text:
        return None
    turn = ConciergeTurn(member_id=member_id, role=role, content=text)
    db.add(turn)
    db.flush()
    return turn


def load_messages(db: Session, member_id: int, *, limit: int = 20) -> list[dict]:
    """De laatste ``limit`` turns oplopend → ``[{"role", "content": <str>}]``.

    Lege turns worden defensief weggefilterd (tweede gordel): de historie die naar
    ``client.messages.stream`` gaat bevat nooit een lege-content bericht.
    """
    rows = db.scalars(
        select(ConciergeTurn)
        .where(ConciergeTurn.member_id == member_id)
        .order_by(ConciergeTurn.id.desc())
        .limit(limit)
    ).all()
    rows = list(reversed(rows))
    return [
        {"role": r.role, "content": r.content}
        for r in rows
        if (r.content or "").strip()
    ]


def clear_turns(db: Session, member_id: int) -> None:
    """Wis alle conversatie-turns van één lid + het eruit gedistilleerde geheugen.

    Wat de concierge uit het gesprek onthield (``member_memory`` + hoogwatermerk)
    gaat mee — anders blijft een geheugen hangen zonder de turns eronder. Caller
    commit. (Bij volledige account-wissing verdwijnt alles al met de member-row.)
    """
    from app.models import Member

    for r in db.scalars(
        select(ConciergeTurn).where(ConciergeTurn.member_id == member_id)
    ).all():
        db.delete(r)
    member = db.get(Member, member_id)
    if member is not None:
        member.member_memory = None
        member.memory_synced_turn_id = None
    db.flush()
