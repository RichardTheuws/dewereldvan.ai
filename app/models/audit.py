"""Audit log model — AVG-traceability for approvals and visibility changes."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AuditAction, Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Expliciete, ruime lengte (64) i.p.v. de auto-sizing op de langste enum-waarde:
    # zo breekt een nieuwe, langere audit-actie niet stil op Postgres (zie 0008 —
    # ``invite_registration`` = 19 > de oude VARCHAR(18)). SQLite negeert de lengte.
    action: Mapped[AuditAction] = mapped_column(
        SQLEnum(AuditAction, name="audit_action", native_enum=False, length=64),
        nullable=False,
        index=True,
    )
    # Who did it (e.g. the admin).
    actor_member_id: Mapped[int | None] = mapped_column(
        ForeignKey("member.id", ondelete="SET NULL"), nullable=True
    )
    # Whom it affected.
    target_member_id: Mapped[int | None] = mapped_column(
        ForeignKey("member.id", ondelete="SET NULL"), nullable=True
    )
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)  # e.g. "members->public"
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
