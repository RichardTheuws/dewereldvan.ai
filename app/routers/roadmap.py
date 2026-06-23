"""Roadmap-router (E3) — /roadmap (leden) + admin-CRUD-board.

Routes (zie bouwcontract §3 E3):
- GET  ``/roadmap``                       — levende roadmap, per fase, op positie.
- GET  ``/admin/roadmap``                 — admin CRUD-board.
- POST ``/admin/roadmap``                 — maak item, swap nieuwe rij.
- POST ``/admin/roadmap/{id}/bewerken``   — update, swap rij.
- POST ``/admin/roadmap/{id}/verwijderen``— delete, swap leeg.

Auth: ``/roadmap`` is **publiek + indexeerbaar** — de levende roadmap is een
transparant onderdeel van de waardepropositie (noordster: open, transparant; voedt
de homepage "wat komt eraan"). Admin-CRUD ``require_admin``. CSRF via ``hx-headers``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_member, require_admin
from app.models import Member, RoadmapStatus
from app.schemas.roadmap import RoadmapItemForm
from app.services import roadmap_service

router = APIRouter(tags=["roadmap"])


def _render(request: Request, name: str, ctx: dict | None = None, **kw) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, name, ctx or {}, **kw)


# --------------------------------------------------------------------------- #
# Leden-weergave                                                              #
# --------------------------------------------------------------------------- #


@router.get("/roadmap", response_class=HTMLResponse)
def index(
    request: Request,
    member: Member | None = Depends(current_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """De kosmische, levende roadmap — een echt kanban op status (overwegen →
    gepland → in aanbouw → gelanceerd), publiek leesbaar (ook anon, indexeerbaar)."""
    columns = roadmap_service.list_by_status(db)
    shipped = sum(len(items) for status, _label, items in columns if status.value == "gedaan")
    return _render(
        request,
        "roadmap/index.html",
        {
            "columns": columns,
            "shipped_count": shipped,
            "member": member,
            "statuses": list(RoadmapStatus),
        },
    )


# --------------------------------------------------------------------------- #
# Admin CRUD                                                                  #
# --------------------------------------------------------------------------- #


@router.get("/admin/roadmap", response_class=HTMLResponse)
def admin_board(
    request: Request,
    admin: Member = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Admin CRUD-board met alle items + maak-formulier."""
    items = roadmap_service.list_all(db)
    return _render(
        request,
        "roadmap/admin.html",
        {"items": items, "statuses": list(RoadmapStatus)},
    )


@router.post("/admin/roadmap", response_class=HTMLResponse)
def admin_create(
    request: Request,
    title: str = Form(""),
    description: str = Form(""),
    status_value: str = Form(RoadmapStatus.overwegen.value, alias="status"),
    phase: str = Form("Later"),
    position: int = Form(0),
    admin: Member = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Maak een roadmap-item; geef het verse admin-board terug."""
    try:
        data = RoadmapItemForm(
            title=title,
            description=description or None,
            status=status_value,
            phase=phase,
            position=position,
        )
    except ValueError:
        items = roadmap_service.list_all(db)
        return _render(
            request,
            "roadmap/admin.html",
            {
                "items": items,
                "statuses": list(RoadmapStatus),
                "error": "Geef het item minstens een titel.",
            },
            status_code=400,
        )

    roadmap_service.create(
        db,
        title=data.title,
        description=data.description,
        status=data.status,
        phase=data.phase,
        position=data.position or None,
    )
    db.commit()
    items = roadmap_service.list_all(db)
    return _render(
        request,
        "roadmap/admin.html",
        {"items": items, "statuses": list(RoadmapStatus), "saved": True},
    )


@router.post("/admin/roadmap/{item_id}/bewerken", response_class=HTMLResponse)
def admin_update(
    request: Request,
    item_id: int,
    title: str = Form(""),
    description: str = Form(""),
    status_value: str = Form("", alias="status"),
    phase: str = Form(""),
    position: int = Form(0),
    admin: Member = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Werk een roadmap-item bij; swap de rij."""
    item = roadmap_service.get(db, item_id)
    if item is None:
        return HTMLResponse("", status_code=status.HTTP_404_NOT_FOUND)
    roadmap_service.update(
        db,
        item,
        title=title or None,
        description=description,
        status=status_value or None,
        phase=phase or None,
        position=position,
    )
    db.commit()
    db.refresh(item)
    return _render(
        request,
        "roadmap/_admin_item.html",
        {"item": item, "statuses": list(RoadmapStatus)},
    )


@router.post("/admin/roadmap/{item_id}/verwijderen", response_class=HTMLResponse)
def admin_delete(
    request: Request,
    item_id: int,
    admin: Member = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Verwijder een roadmap-item; swap met leeg (htmx outerHTML)."""
    item = roadmap_service.get(db, item_id)
    if item is None:
        return HTMLResponse("", status_code=status.HTTP_404_NOT_FOUND)
    roadmap_service.delete(db, item)
    db.commit()
    return HTMLResponse("")
