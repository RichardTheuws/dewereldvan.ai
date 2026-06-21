"""Tool-router (doc 03 Fase C) — mens-naast-AI-correctiepad + re-review.

Routes:
- POST ``/tools/{tool_id}/correctie`` (require_member) — voeg een aanvulling/
  correctie toe (NAAST de AI-review, nooit eroverheen); swap de notes-lijst.
- POST ``/admin/tool-notes/{note_id}/verberg`` (require_admin) — verberg een
  aanvulling + AuditLog; htmx-swap (spiegelt ``feedback.admin_hide``).
- POST ``/tools/{tool_id}/herzie`` (require_admin) — "ververs nu": trigger een
  re-review. BEWUST admin-only om AI-kosten te beheersen (zie route-comment).

Auth: het correctie-pad is ``require_member`` (ingelogd+approved); verbergen én
herzien zijn ``require_admin``. CSRF via ``hx-headers`` (htmx), zoals overal.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_admin, require_member
from app.models import Member, Tool, ToolReviewNote
from app.services import tool_review_note_service, tool_review_service

router = APIRouter(tags=["tools"])


def _render(request: Request, name: str, ctx: dict | None = None, **kw) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, name, ctx or {}, **kw)


def _notes_context(db: Session, tool: Tool, member: Member) -> dict:
    """Context voor het notes-fragment: de zichtbare aanvullingen + auth-flags."""
    return {
        "tool": tool,
        "notes": tool_review_note_service.list_notes(db, tool),
        "can_note": True,  # de viewer is hier altijd een ingelogd lid
        "is_admin": member.role.value == "admin",
    }


# --------------------------------------------------------------------------- #
# Lid: correctie/aanvulling (mens NAAST de AI)                                 #
# --------------------------------------------------------------------------- #


@router.post("/tools/{tool_id}/correctie", response_class=HTMLResponse)
def add_correction(
    request: Request,
    tool_id: int,
    body: str = Form(""),
    field: str = Form(""),
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Voeg een aanvulling/correctie toe (NAAST de AI-review) en swap de lijst.

    Raakt ``tool.tool_review`` NOOIT aan — de aanvulling is een aparte rij die
    apart getoond wordt. Bij rate-limit/lege tekst → nette inline-fout.
    """
    tool = db.get(Tool, tool_id)
    if tool is None:
        return HTMLResponse("", status_code=status.HTTP_404_NOT_FOUND)

    if not (body or "").strip():
        ctx = _notes_context(db, tool, member)
        ctx["error"] = "Schrijf eerst even je aanvulling."
        return _render(request, "profiles/_tool_review_notes.html", ctx, status_code=400)

    try:
        tool_review_note_service.check_tool_note_rate_limit(db, member)
    except tool_review_note_service.ToolNoteRateLimited:
        ctx = _notes_context(db, tool, member)
        ctx["error"] = (
            "Je vulde net al veel aan — geef ons even tijd. Probeer het over "
            "een uur opnieuw."
        )
        return _render(request, "profiles/_tool_review_notes.html", ctx, status_code=429)

    tool_review_note_service.add_note(
        db, tool=tool, member=member, field=field, body=body
    )
    db.commit()
    return _render(
        request, "profiles/_tool_review_notes.html", _notes_context(db, tool, member)
    )


# --------------------------------------------------------------------------- #
# Admin: verberg een aanvulling                                               #
# --------------------------------------------------------------------------- #


@router.post("/admin/tool-notes/{note_id}/verberg", response_class=HTMLResponse)
def admin_hide_note(
    request: Request,
    note_id: int,
    admin: Member = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Verberg een aanvulling (+ AuditLog); swap de notes-lijst terug."""
    note = db.get(ToolReviewNote, note_id)
    if note is None:
        return HTMLResponse("", status_code=status.HTTP_404_NOT_FOUND)
    tool = db.get(Tool, note.tool_id)
    tool_review_note_service.hide_note(db, note, actor=admin)
    db.commit()
    return _render(
        request, "profiles/_tool_review_notes.html", _notes_context(db, tool, admin)
    )


# --------------------------------------------------------------------------- #
# Admin: "ververs nu" (re-review)                                             #
# --------------------------------------------------------------------------- #


@router.post("/tools/{tool_id}/herzie", response_class=HTMLResponse)
def admin_rereview(
    request: Request,
    tool_id: int,
    admin: Member = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Trigger een verse AI-review van deze tool ("ververs nu").

    BEWUST admin-only (``require_admin``) om AI-kosten te beheersen: leden
    beïnvloeden de review gratis via correctie-notes en de nachtjob doet de
    cadans (90 dagen). Een open re-review-knop voor bezoekers zou per klik tokens
    kosten — daarom hier niet. De review draait async (eigen sessie); we swappen
    een korte bevestiging.
    """
    tool = db.get(Tool, tool_id)
    if tool is None:
        return HTMLResponse("", status_code=status.HTTP_404_NOT_FOUND)
    tool_review_service.trigger_async(tool_id)
    return _render(request, "profiles/_tool_rereview_started.html", {"tool": tool})
