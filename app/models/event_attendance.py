"""EventAttendance — de sociale laag op de agenda: wie gaat, organiseert, spreekt.

Eén rij per (event, lid): een lid kiest hoogstens één rol per event (de unieke
constraint maakt her-zetten een update i.p.v. een dubbele rij). Maakt de agenda
sociaal — een kaart toont de telling + de namen van organisatoren/sprekers, en die
namen linken naar hun profiel (graaf-knoop, geen aparte graaf-tabel).

AVG: zowel ``post_id`` als ``member_id`` is ``ON DELETE CASCADE`` — verdwijnt het
event óf het lid, dan verdwijnt de aanmelding mee (er valt niets meer aan te melden).
De expliciete wis-keten in ``account_deletion`` dekt dit ook (SQLite handhaaft
CASCADE niet zonder pragma).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, UniqueConstraint, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, EventAttendanceRole

if TYPE_CHECKING:
    from app.models.member import Member
    from app.models.post import Post


class EventAttendance(Base):
    __tablename__ = "event_attendance"
    __table_args__ = (
        UniqueConstraint("post_id", "member_id", name="uq_event_attendance_post_member"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(
        ForeignKey("post.id", ondelete="CASCADE"), index=True, nullable=False
    )
    member_id: Mapped[int] = mapped_column(
        ForeignKey("member.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[EventAttendanceRole] = mapped_column(
        SQLEnum(EventAttendanceRole, name="event_attendance_role", native_enum=False),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    member: Mapped[Member] = relationship()
    post: Mapped[Post] = relationship()
