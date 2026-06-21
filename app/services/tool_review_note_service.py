"""Tool-review-note-service (doc 03 §4.3, Fase C) — mens-naast-AI-correctie.

Een lid kan een review-veld corrigeren/aanvullen. Die aanvulling wordt als een
APARTE ``ToolReviewNote``-rij opgeslagen en NAAST het AI-blok getoond — ze
overschrijft ``tool.tool_review`` NOOIT. Zo blijft de herkomst (AI vs mens)
zichtbaar en houdt het expert-netwerk de review scherp.

Spiegelt ``idea_service``/``feedback_service``:

1. **Toevoegen** (``add_note``) — één rij per lid, met per-lid rate-limit in een
   glijdend uur-venster (``magic_link._recent_count``-patroon, exact zoals ideeën).
   ``body`` wordt hard gecapt op ``settings.max_feedback_body_chars``.
2. **Weergave** (``list_notes``) — zichtbare aanvullingen (niet ``hidden``) voor
   één tool, nieuwste eerst.
3. **Moderatie** (``hide_note``) — admin verbergt een aanvulling (``hidden=True``)
   + schrijft een ``tool_note_hidden``-AuditLog (lichtgewicht, geen zware queue).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AuditAction, AuditLog, Member, Tool, ToolReviewNote
from app.security import naive_utc, utcnow

__all__ = [
    "ToolNoteRateLimited",
    "check_tool_note_rate_limit",
    "add_note",
    "list_notes",
    "hide_note",
]


class ToolNoteRateLimited(RuntimeError):
    """Het lid overschreed de aanvul-rate-limit binnen het uur-venster."""


# --------------------------------------------------------------------------- #
# Rate-limit (per lid, glijdend uur-venster — magic_link._recent_count-patroon) #
# --------------------------------------------------------------------------- #


def _recent_note_count(db: Session, member_id: int, now: datetime) -> int:
    """Tel ``ToolReviewNote``-rijen van dit lid in het laatste uur."""
    window_start = naive_utc(now) - timedelta(hours=1)
    return (
        db.scalar(
            select(func.count())
            .select_from(ToolReviewNote)
            .where(
                ToolReviewNote.member_id == member_id,
                ToolReviewNote.created_at >= window_start,
            )
        )
        or 0
    )


def check_tool_note_rate_limit(
    db: Session,
    member: Member,
    *,
    now: datetime | None = None,
) -> None:
    """Raise ``ToolNoteRateLimited`` als het lid het uur-budget overschreed."""
    now = now or utcnow()
    if (
        _recent_note_count(db, member.id, now)
        >= settings.rate_limit_tool_note_per_hour
    ):
        raise ToolNoteRateLimited()


# --------------------------------------------------------------------------- #
# Toevoegen                                                                   #
# --------------------------------------------------------------------------- #


def add_note(
    db: Session,
    *,
    tool: Tool,
    member: Member,
    field: str | None,
    body: str,
) -> ToolReviewNote:
    """Voeg één aanvulling/correctie toe (NAAST de AI-review) en geef de rij terug.

    De caller heeft de rate-limit al via ``check_tool_note_rate_limit`` getoetst.
    ``body`` wordt hard gecapt op ``settings.max_feedback_body_chars``; ``field``
    op de kolomlengte (40). Een leeg/whitespace-``field`` wordt ``None`` (algemeen).
    Dit raakt ``tool.tool_review`` NIET aan — mens overschrijft de AI nooit stil.
    """
    body = (body or "").strip()[: settings.max_feedback_body_chars]
    clean_field = (field or "").strip()[:40] or None
    note = ToolReviewNote(
        tool_id=tool.id,
        member_id=member.id,
        field=clean_field,
        body=body,
    )
    db.add(note)
    db.flush()
    return note


# --------------------------------------------------------------------------- #
# Weergave                                                                    #
# --------------------------------------------------------------------------- #


def list_notes(db: Session, tool: Tool) -> list[ToolReviewNote]:
    """Zichtbare aanvullingen (niet ``hidden``) voor één tool, nieuwste eerst."""
    stmt = (
        select(ToolReviewNote)
        .where(
            ToolReviewNote.tool_id == tool.id,
            ToolReviewNote.hidden.is_(False),
        )
        .order_by(ToolReviewNote.created_at.desc(), ToolReviewNote.id.desc())
    )
    return list(db.scalars(stmt).all())


# --------------------------------------------------------------------------- #
# Moderatie (admin)                                                           #
# --------------------------------------------------------------------------- #


def hide_note(
    db: Session,
    note: ToolReviewNote,
    *,
    actor: Member | None = None,
) -> ToolReviewNote:
    """Verberg een aanvulling (``hidden=True``) + schrijf een AuditLog.

    Lichtgewicht moderatie (geen zware queue) — exact het ``idea_service``-patroon.
    """
    note.hidden = True
    db.add(
        AuditLog(
            action=AuditAction.tool_note_hidden,
            actor_member_id=actor.id if actor is not None else None,
            target_member_id=note.member_id,
            detail=f"tool_review_note#{note.id} hidden",
        )
    )
    db.flush()
    return note
