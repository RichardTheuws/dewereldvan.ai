"""Conversatie-state helpers voor AI-native profielbouw (F1).

Twee verantwoordelijkheden:

1. **DB-state** (``load_messages`` / ``append_turn`` / ``clear_turns``): de
   Anthropic-conversatie leeft in ``AiChatTurn``-rijen (zie bouwcontract §3e —
   tool/thinking-blokken moeten byte-exact terug over meerdere turns). Elke rij
   bewaart ``json.dumps`` van een content-blok; ``load_messages`` reconstrueert
   de ``[{"role","content"}]``-lijst die de service aan Anthropic voert.

2. **SSE-kanaal** (``_Channel``): de GET ``/stream`` (EventSource) draait de
   synchrone Anthropic-stream in een threadpool en duwt elke tekst-delta in een
   ``_Channel``-queue; de async generator pompt die queue leeg naar de browser.
   In-process, geen extra leverancier (consistent met de lage-op-last-eis).
"""

from __future__ import annotations

import json
import queue
from collections.abc import Iterator
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AiChatTurn, Member

# Sentinel die het einde van een stream markeert (geen verdere deltas volgen).
_DONE = object()

# Veiligheids-timeout op één blokkerende read van het kanaal (seconden).
CHANNEL_TIMEOUT_SEC: float = 120.0


# --------------------------------------------------------------------------- #
# DB conversation state                                                       #
# --------------------------------------------------------------------------- #


def load_messages(db: Session, member: Member) -> list[dict[str, Any]]:
    """Reconstrueer de Anthropic-``messages``-lijst voor dit lid (chronologisch).

    Elk ``AiChatTurn.content_json`` is ``json.dumps`` van het oorspronkelijke
    content-blok (string voor lid-tekst, of de volledige assistant-content-lijst
    incl. tool/thinking-blokken). Wordt 1:1 teruggegeven zodat de SDK 'm
    ongewijzigd kan terugsturen.
    """
    rows = db.scalars(
        select(AiChatTurn)
        .where(AiChatTurn.member_id == member.id)
        .order_by(AiChatTurn.id)
    ).all()
    messages: list[dict[str, Any]] = []
    for row in rows:
        try:
            content = json.loads(row.content_json)
        except (ValueError, TypeError):
            content = row.content_json
        messages.append({"role": row.role, "content": content})
    return messages


def append_turn(
    db: Session, member: Member, role: str, content: Any
) -> AiChatTurn:
    """Persisteer één turn. ``content`` mag een string of content-blok-lijst zijn."""
    turn = AiChatTurn(
        member_id=member.id,
        role=role,
        content_json=json.dumps(content, default=_json_default),
    )
    db.add(turn)
    db.flush()
    return turn


def clear_turns(db: Session, member: Member) -> None:
    """Wis de volledige conversatie-state (nieuwe sessie / na publiceren)."""
    for row in db.scalars(
        select(AiChatTurn).where(AiChatTurn.member_id == member.id)
    ).all():
        db.delete(row)
    db.flush()


def has_turns(db: Session, member: Member) -> bool:
    """True als het lid al een lopende bouw-conversatie heeft."""
    return (
        db.scalar(
            select(AiChatTurn.id).where(AiChatTurn.member_id == member.id).limit(1)
        )
        is not None
    )


def _json_default(obj: Any) -> Any:
    """Serialiseer Anthropic content-blokken (pydantic-achtige objecten) naar JSON.

    De SDK levert content-blokken als objecten met ``.model_dump()`` (pydantic v2)
    of ``.to_dict()``; we dumpen die naar plain dicts zodat ze byte-exact bewaard
    en teruggestuurd kunnen worden.
    """
    for attr in ("model_dump", "to_dict", "dict"):
        fn = getattr(obj, attr, None)
        if callable(fn):
            return fn()
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in vars(obj).items() if not k.startswith("_")}
    return str(obj)


# --------------------------------------------------------------------------- #
# SSE channel (in-process, per stream)                                        #
# --------------------------------------------------------------------------- #


class _Channel:
    """Een tekst-delta-queue met een terminerend sentinel (één per stream).

    De producer (``stream_turn``, in een threadpool) roept ``send`` per chunk en
    ``close`` aan het eind; de SSE-generator leest met ``get`` (blokkerend, met
    veiligheids-timeout) of ``iter_text``. Het sentinel/timeout-protocol leeft
    UITSLUITEND hier — consumers mogen ``q`` niet rechtstreeks lezen.
    """

    def __init__(self) -> None:
        self.q: queue.Queue[Any] = queue.Queue()

    def send(self, text: str) -> None:
        self.q.put(text)

    def close(self) -> None:
        self.q.put(_DONE)

    def get(self, timeout: float = CHANNEL_TIMEOUT_SEC) -> str | None:
        """Eén blokkerende read; geeft ``None`` bij sentinel of timeout (=einde)."""
        try:
            item = self.q.get(timeout=timeout)
        except queue.Empty:
            return None
        if item is _DONE:
            return None
        return item

    def iter_text(self, timeout: float = CHANNEL_TIMEOUT_SEC) -> Iterator[str]:
        """Yield tekst-deltas tot het sentinel of een timeout."""
        while True:
            item = self.get(timeout)
            if item is None:
                return
            yield item
