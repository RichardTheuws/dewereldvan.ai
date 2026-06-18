"""Feedback-router (E1) — widget-paneel, inzending + admin-overzicht.

Routes:
- GET  ``/feedback/paneel``            — kosmisch htmx-paneel (formulier), met de
  paginacontext uit ``HX-Current-URL``/``Referer`` (via ``safe_url`` gevalideerd).
- POST ``/feedback``                   — sla op (rate-limit per lid), render ``_sent``.
- GET  ``/admin/feedback``             — admin-overzicht (require_admin), noindex.
- POST ``/admin/feedback/{id}/verberg``— toggle hidden + AuditLog (require_admin).

Auth: het paneel + de inzending zijn publiek (een ingelogd lid wordt automatisch
gekoppeld via ``current_member``); moderatie is ``require_admin``. CSRF loopt via
``hx-headers`` (htmx) op de pagina-``<body>``. Anti-abuse: ingelogde inzending
wordt per lid begrensd, anonieme inzending per inzender-IP (``feedback.ip``) —
zie ``feedback_service.check_feedback_rate_limit``.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_member, require_admin
from app.models import AuditAction, AuditLog, Feedback, Member
from app.schemas.feedback import FeedbackForm
from app.services import feedback_service

router = APIRouter(tags=["feedback"])


def _render(request: Request, name: str, ctx: dict | None = None, **kw) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, name, ctx or {}, **kw)


def _safe_candidate(value: str | None) -> str:
    """Weiger gevaarlijke schemes (``javascript:``/``data:`` e.d.) op een ruwe URL.

    Spiegelt ``app.main.safe_url`` maar zonder die module te importeren (zou een
    circulaire import met de router-registratie geven). We hoeven hier alleen het
    pad over te houden, dus dit volstaat als scheme-poort vóór ``urlsplit``.
    """
    if not value:
        return ""
    stripped = value.strip()
    if not stripped:
        return ""
    head = stripped.split("/", 1)[0]
    if ":" in head:
        scheme = head.split(":", 1)[0].strip().lower()
        if scheme not in ("http", "https"):
            return ""
    return stripped


def _client_ip(request: Request) -> str | None:
    """Inzender-IP voor de anonieme rate-limit (spiegelt ``auth._client_ip``)."""
    return request.client.host if request.client else None


def _page_path(request: Request, supplied: str | None = None) -> str:
    """Bepaal een veilig, intern paginapad voor de feedback-context.

    Voorkeur: het meegestuurde veld (uit het paneel-formulier), dan
    ``HX-Current-URL``, dan ``Referer``. Alles loopt via ``safe_url`` (blokkeert
    ``javascript:``/``data:`` e.d.) en we bewaren enkel het *pad* (geen host,
    geen querystring met mogelijk gevoelige tokens). Fallback ``/``.
    """
    candidate = (
        supplied
        or request.headers.get("HX-Current-URL")
        or request.headers.get("Referer")
        or "/"
    )
    cleaned = _safe_candidate(candidate) or "/"
    parts = urlsplit(cleaned)
    path = parts.path or "/"
    if not path.startswith("/"):
        path = "/"
    return path[:500]


# --------------------------------------------------------------------------- #
# Widget                                                                      #
# --------------------------------------------------------------------------- #


@router.get("/feedback/paneel", response_class=HTMLResponse)
def panel(
    request: Request,
    member: Member | None = Depends(current_member),
) -> HTMLResponse:
    """Render het kosmische feedback-paneel (htmx-fragment) met paginacontext."""
    return _render(
        request,
        "feedback/_panel.html",
        {"page_path": _page_path(request), "member": member},
    )


@router.post("/feedback", response_class=HTMLResponse)
def submit(
    request: Request,
    body: str = Form(""),
    page_path: str = Form("/"),
    kind: str = Form("algemeen"),
    member: Member | None = Depends(current_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Sla feedback op (met paginacontext) en geef de kosmische succes-staat terug."""
    try:
        data = FeedbackForm(body=body, page_path=page_path, kind=kind)
    except ValueError:
        return _render(
            request,
            "feedback/_panel.html",
            {
                "page_path": _page_path(request, page_path),
                "member": member,
                "error": "Schrijf eerst even je gedachte.",
                "body": body,
            },
            status_code=400,
        )

    client_ip = _client_ip(request)
    try:
        feedback_service.check_feedback_rate_limit(db, member, ip=client_ip)
    except feedback_service.FeedbackRateLimited:
        return _render(
            request,
            "feedback/_panel.html",
            {
                "page_path": _page_path(request, page_path),
                "member": member,
                "error": (
                    "Je deelde net al veel — geef ons even tijd om het te lezen. "
                    "Probeer het over een uur opnieuw."
                ),
            },
            status_code=429,
        )

    feedback_service.create(
        db,
        member=member,
        page_path=_page_path(request, data.page_path),
        body=data.body,
        kind=data.kind,
        ip=client_ip,
    )
    db.commit()
    return _render(request, "feedback/_sent.html", {})


# --------------------------------------------------------------------------- #
# Admin                                                                       #
# --------------------------------------------------------------------------- #


@router.get("/admin/feedback", response_class=HTMLResponse)
def admin_overview(
    request: Request,
    admin: Member = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Admin-overzicht: niet-verborgen eerst, nieuwste eerst (login-gated, noindex)."""
    items = feedback_service.list_for_admin(db, include_hidden=True)
    return _render(request, "admin/feedback.html", {"items": items})


@router.post("/admin/feedback/{feedback_id}/verberg", response_class=HTMLResponse)
def admin_hide(
    request: Request,
    feedback_id: int,
    admin: Member = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Toggle ``hidden`` op een feedback-rij + AuditLog; swap de rij terug."""
    item = db.get(Feedback, feedback_id)
    if item is None:
        return HTMLResponse("", status_code=status.HTTP_404_NOT_FOUND)
    new_hidden = not item.hidden
    feedback_service.set_hidden(db, item, hidden=new_hidden)
    db.add(
        AuditLog(
            action=AuditAction.feedback_hidden,
            actor_member_id=admin.id,
            target_member_id=item.member_id,
            detail=f"feedback#{item.id} hidden={new_hidden}",
        )
    )
    db.commit()
    db.refresh(item)
    return _render(request, "admin/_feedback_row.html", {"item": item})
