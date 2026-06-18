"""Roadmap-service (E3) — admin-CRUD, herordening en weergave-query.

De levende roadmap is admin-curated. Items zijn gegroepeerd per ``phase`` en
binnen een fase gesorteerd op ``position`` (oplopend). ``list_grouped`` levert de
fasen in een stabiele, betekenisvolle volgorde (een fase die als eerste een item
kreeg, komt eerst) zodat de kosmische weergave deterministisch is.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import RoadmapItem, RoadmapStatus

__all__ = [
    "create",
    "update",
    "delete",
    "get",
    "list_all",
    "list_grouped",
    "parse_status",
]


def parse_status(value: str | None) -> RoadmapStatus:
    """Map een ruwe stringwaarde naar ``RoadmapStatus`` (default ``overwegen``)."""
    if not value:
        return RoadmapStatus.overwegen
    try:
        return RoadmapStatus(value.strip().lower())
    except ValueError:
        return RoadmapStatus.overwegen


def get(db: Session, item_id: int) -> RoadmapItem | None:
    """Eén roadmap-item, of ``None``."""
    return db.get(RoadmapItem, item_id)


def list_all(db: Session) -> list[RoadmapItem]:
    """Alle items, gesorteerd op fase-volgorde dan ``position`` (admin-board)."""
    stmt = select(RoadmapItem).order_by(
        RoadmapItem.phase.asc(),
        RoadmapItem.position.asc(),
        RoadmapItem.id.asc(),
    )
    return list(db.scalars(stmt).all())


def list_grouped(db: Session) -> list[tuple[str, list[RoadmapItem]]]:
    """Items gegroepeerd per ``phase``, binnen elke fase op ``position`` gesorteerd.

    De fasen worden geordend op het laagste ``position`` (en daarna eerste id)
    binnen de fase, zodat de weergave-volgorde van de fasen stabiel en door de
    admin via ``position`` stuurbaar is.
    """
    items = list(
        db.scalars(
            select(RoadmapItem).order_by(
                RoadmapItem.position.asc(), RoadmapItem.id.asc()
            )
        ).all()
    )
    order: list[str] = []
    buckets: dict[str, list[RoadmapItem]] = {}
    for item in items:
        if item.phase not in buckets:
            buckets[item.phase] = []
            order.append(item.phase)
        buckets[item.phase].append(item)
    return [(phase, buckets[phase]) for phase in order]


def _next_position(db: Session, phase: str) -> int:
    """Eerstvolgende vrije ``position`` achteraan binnen een fase."""
    return (
        db.scalar(
            select(func.coalesce(func.max(RoadmapItem.position), -1) + 1).where(
                RoadmapItem.phase == phase
            )
        )
        or 0
    )


def create(
    db: Session,
    *,
    title: str,
    description: str | None = None,
    status: RoadmapStatus | str = RoadmapStatus.overwegen,
    phase: str = "Later",
    position: int | None = None,
    linked_idea_id: int | None = None,
) -> RoadmapItem:
    """Maak één roadmap-item. Zonder ``position`` komt het achteraan in de fase."""
    title = (title or "").strip()[:200]
    phase = (phase or "Later").strip()[:80] or "Later"
    if isinstance(status, str):
        status = parse_status(status)
    if position is None:
        position = _next_position(db, phase)
    item = RoadmapItem(
        title=title,
        description=(description or None),
        status=status,
        phase=phase,
        position=position,
        linked_idea_id=linked_idea_id,
    )
    db.add(item)
    db.flush()
    return item


def update(
    db: Session,
    item: RoadmapItem,
    *,
    title: str | None = None,
    description: str | None = None,
    status: RoadmapStatus | str | None = None,
    phase: str | None = None,
    position: int | None = None,
) -> RoadmapItem:
    """Werk de meegegeven velden van een roadmap-item bij (overige onveranderd)."""
    if title is not None:
        item.title = title.strip()[:200] or item.title
    if description is not None:
        item.description = description.strip()[:4000] or None
    if status is not None:
        item.status = parse_status(status) if isinstance(status, str) else status
    if phase is not None:
        item.phase = phase.strip()[:80] or "Later"
    if position is not None:
        item.position = position
    db.flush()
    return item


def delete(db: Session, item: RoadmapItem) -> None:
    """Verwijder een roadmap-item."""
    db.delete(item)
    db.flush()
