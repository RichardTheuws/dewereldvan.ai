"""Inquiry model (PRD hub §4.1) — een vraag van een bezoeker aan een lid.

De eerste weg van buiten naar binnen: een opdrachtgever (geen lid) stelt een vraag
via het openbare profiel. Nul AI; bezorging via ``notification_service.notify``
(geen e-mail — het lid antwoordt zelf vanuit z'n eigen mail).

- ``member_id`` / ``profile_id``: CASCADE — de aanvraag hoort bij de ontvanger en
  verdwijnt mee bij wissen (AVG-wis dekt dit ook expliciet; SQLite handhaaft CASCADE
  in productie niet, Postgres wel).
- ``ip_hash``: gezouten sha256 van het IP, alleen voor de rate-limit — nooit het
  ruwe IP. ``dedupe_hash`` vangt een dubbele submit (unique, race via savepoint).
- Bewaartermijn: 180 dagen (``app.jobs.purge_inquiries``), zoals beloofd in het
  toestemmingsvinkje.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, InquiryStatus

if TYPE_CHECKING:
    from app.models.member import Member
    from app.models.profile import Profile


class Inquiry(Base):
    __tablename__ = "inquiry"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(
        ForeignKey("member.id", ondelete="CASCADE"), index=True, nullable=False
    )
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profile.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sender_name: Mapped[str] = mapped_column(String(120), nullable=False)
    sender_email: Mapped[str] = mapped_column(String(320), nullable=False)
    sender_org: Mapped[str | None] = mapped_column(String(160), nullable=True)
    topic: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[InquiryStatus] = mapped_column(
        SQLEnum(InquiryStatus, name="inquiry_status", native_enum=False),
        default=InquiryStatus.new,
        nullable=False,
        index=True,
    )
    ip_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    dedupe_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False, index=True
    )
    read_at: Mapped[datetime | None] = mapped_column(nullable=True)

    member: Mapped[Member] = relationship()
    profile: Mapped[Profile] = relationship()
