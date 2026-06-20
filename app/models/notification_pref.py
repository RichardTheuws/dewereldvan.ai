"""NotificationPref — het door het lid gekozen notificatiekanaal.

Eén rij per lid (``member_id`` uniek). ``channel`` = het voorkeurskanaal voor
push-seintjes; default ``in_app`` (de state-derived pull-chip, geen actieve push).
Kiest een lid ``telegram`` (na koppeling), dan pusht ``notify()`` naar Telegram —
náást de in-app-chip. Uitbreidbaar: een nieuw kanaal = een extra toegestane waarde.

CASCADE op het lid + opname in ``delete_member_completely`` (AVG).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.member import Member


class NotificationPref(Base):
    __tablename__ = "notification_pref"

    member_id: Mapped[int] = mapped_column(
        ForeignKey("member.id", ondelete="CASCADE"), primary_key=True
    )
    channel: Mapped[str] = mapped_column(String(16), nullable=False, default="in_app")

    member: Mapped[Member] = relationship()
