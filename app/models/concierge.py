"""Concierge models — proactive-nudge frequency cap (PRD §2.4, §4.2).

The proactive layer is pure-SQL (no LLM per pageview). When a member dismisses
a nudge ("✕ niet nu"), we persist one row per ``(member, nudge_kind)`` so the
same suggestion stays silent for 30 days. One row per member+kind: a fresh
dismissal updates ``dismissed_at`` rather than stacking rows (see
``nudge_service.dismiss``).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.member import Member


class ConciergeNudgeDismissal(Base):
    __tablename__ = "concierge_nudge_dismissal"
    __table_args__ = (
        UniqueConstraint("member_id", "nudge_kind", name="uq_concierge_nudge"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(
        ForeignKey("member.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Stable nudge identity: the trigger kind, optionally scoped to a subject
    # (e.g. "tag_overlap:mark-slug") so dismissing one person's intro does not
    # silence all of them. Length covers "kind:slug" comfortably.
    nudge_kind: Mapped[str] = mapped_column(String(120), nullable=False)
    dismissed_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    member: Mapped[Member] = relationship(back_populates="nudge_dismissals")
