"""Connect-router (MCP) — "verbind je AI-tool": persoonlijke tokens beheren.

De onboarding van de MCP-server: een lid genereert een token (één keer getoond),
krijgt een kant-en-klaar ``claude mcp add``-commando, en kan tokens intrekken.

Routes:
- GET  ``/profiel/verbind``                  — de kosmische connect-pagina.
- POST ``/profiel/verbind/token``            — genereer een token (toon één keer).
- POST ``/profiel/verbind/token/{id}/intrekken`` — trek een token in (swap de lijst).

Auth: ``require_member`` (alleen je eigen tokens). CSRF via ``hx-headers``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import require_member
from app.models import Member
from app.services import token_service

router = APIRouter(tags=["connect"])


def _render(request: Request, name: str, ctx: dict | None = None, **kw) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, name, ctx or {}, **kw)


def _ctx(db: Session, member: Member, **extra) -> dict:
    return {
        "tokens": token_service.list_for_member(db, member),
        "mcp_url": settings.mcp_base_url.rstrip("/"),
        **extra,
    }


@router.get("/profiel/verbind", response_class=HTMLResponse)
def connect_page(
    request: Request,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    return _render(request, "connect/index.html", _ctx(db, member))


@router.post("/profiel/verbind/token", response_class=HTMLResponse)
def create_token(
    request: Request,
    label: str = Form(""),
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Genereer een token; toon de ruwe waarde + het commando ÉÉN keer."""
    raw, _token = token_service.generate(db, member, label=label)
    db.commit()
    return _render(
        request,
        "connect/_new_token.html",
        _ctx(db, member, raw_token=raw),
    )


@router.post("/profiel/verbind/token/{token_id}/intrekken", response_class=HTMLResponse)
def revoke_token(
    request: Request,
    token_id: int,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    token_service.revoke(db, token_id, member)
    db.commit()
    return _render(request, "connect/_tokens.html", _ctx(db, member))
