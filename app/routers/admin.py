"""Admin routes: the approval queue + one-click approve/reject/suspend.

All actions are guarded by ``require_admin`` and write an ``AuditLog`` row via
the approval service. Buttons use htmx to swap the affected member row in place
(``_member_row.html``) without a full page reload.

Note: this router carries ``prefix="/admin"`` (set by FOUNDATION), so the paths
below resolve to /admin/queue, /admin/members/{id}/approve, etc.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_admin
from app.models import Member, MemberStatus
from app.services import approval as approval_service

router = APIRouter(prefix="/admin", tags=["admin"])


def _render(request: Request, name: str, ctx: dict | None = None, **kw) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, name, ctx or {}, **kw)


@router.get("/queue", response_class=HTMLResponse)
def queue(
    request: Request,
    admin: Member = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    pending = db.scalars(
        select(Member)
        .where(Member.status == MemberStatus.pending)
        .order_by(Member.created_at.asc())
    ).all()
    return _render(request, "admin/queue.html", {"pending": pending})


def _row(request: Request, member: Member, message: str) -> HTMLResponse:
    return _render(
        request,
        "admin/_member_row.html",
        {"member": member, "message": message},
    )


def _load_target(db: Session, member_id: int) -> Member | None:
    return db.get(Member, member_id)


@router.post("/members/{member_id}/approve", response_class=HTMLResponse)
def approve(
    request: Request,
    member_id: int,
    admin: Member = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    target = _load_target(db, member_id)
    if target is None:
        # Stale queue: return an inline row fragment (not the full 404 page) so
        # the htmx outerHTML swap into the <tr> stays valid markup.
        return _render(request, "admin/_member_gone.html", status_code=404)
    try:
        approval_service.approve_member(db, target, actor=admin)
    except approval_service.IllegalTransition as exc:
        db.rollback()
        return _row(request, target, f"Niet mogelijk: {exc}")
    db.commit()
    return _row(request, target, "Goedgekeurd.")


@router.post("/members/{member_id}/reject", response_class=HTMLResponse)
def reject(
    request: Request,
    member_id: int,
    admin: Member = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    target = _load_target(db, member_id)
    if target is None:
        # Stale queue: return an inline row fragment (not the full 404 page) so
        # the htmx outerHTML swap into the <tr> stays valid markup.
        return _render(request, "admin/_member_gone.html", status_code=404)
    try:
        approval_service.reject_member(db, target, actor=admin)
    except approval_service.IllegalTransition as exc:
        db.rollback()
        return _row(request, target, f"Niet mogelijk: {exc}")
    db.commit()
    return _row(request, target, "Geweigerd.")


@router.post("/members/{member_id}/suspend", response_class=HTMLResponse)
def suspend(
    request: Request,
    member_id: int,
    admin: Member = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    target = _load_target(db, member_id)
    if target is None:
        # Stale queue: return an inline row fragment (not the full 404 page) so
        # the htmx outerHTML swap into the <tr> stays valid markup.
        return _render(request, "admin/_member_gone.html", status_code=404)
    try:
        approval_service.suspend_member(db, target, actor=admin)
    except approval_service.IllegalTransition as exc:
        db.rollback()
        return _row(request, target, f"Niet mogelijk: {exc}")
    db.commit()
    return _row(request, target, "Geschorst.")
