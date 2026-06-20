"""Notificatie-routes — voorkeurskanaal kiezen + Telegram koppelen + de webhook.

Self-only (``require_member``) voor de instellingen; CSRF via ``hx-headers``. De
Telegram-**webhook** is een externe POST van Telegram (CSRF-exempt in ``app.csrf``);
die valideert de ``X-Telegram-Bot-Api-Secret-Token``-header zelf.

Geen e-mail: de notificatie-richting is in-app pull-chip (default) + een lid-gekozen
push-kanaal (Telegram eerst). Zie ``docs/PRD-notificaties.md``.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import require_member
from app.models import Member
from app.services import notification_service, telegram_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["notifications"])


def _render(request: Request, name: str, ctx: dict | None = None, **kw) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, name, ctx or {}, **kw)


def _panel_ctx(db: Session, member: Member, *, link_url: str | None = None) -> dict:
    return {
        "channel": notification_service.preferred_channel(db, member),
        "tg_status": notification_service.telegram_status(db, member),
        "tg_configured": telegram_service.configured(),
        "link_url": link_url,
    }


# --------------------------------------------------------------------------- #
# Instellingen (self-only)                                                     #
# --------------------------------------------------------------------------- #


@router.get("/profiel/notificaties", response_class=HTMLResponse)
def settings_page(
    request: Request,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """De notificatie-instellingen (kanaalkeuze + Telegram koppelen)."""
    return _render(request, "notifications/instellingen.html", _panel_ctx(db, member))


@router.post("/profiel/notificaties/kanaal", response_class=HTMLResponse)
def set_channel(
    request: Request,
    channel: str = Form("in_app"),
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Zet het voorkeurskanaal (Telegram alleen als 't gekoppeld is)."""
    notification_service.set_preference(db, member, channel)
    db.commit()
    return _render(request, "notifications/_panel.html", _panel_ctx(db, member))


@router.post("/profiel/notificaties/telegram/start", response_class=HTMLResponse)
def telegram_start(
    request: Request,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Begin de Telegram-koppeling: geef de deep-link om de bot te openen."""
    link = notification_service.begin_telegram_link(db, member)
    db.commit()
    return _render(request, "notifications/_panel.html", _panel_ctx(db, member, link_url=link))


@router.post("/profiel/notificaties/telegram/ontkoppel", response_class=HTMLResponse)
def telegram_unlink(
    request: Request,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    notification_service.unlink_telegram(db, member)
    db.commit()
    return _render(request, "notifications/_panel.html", _panel_ctx(db, member))


# --------------------------------------------------------------------------- #
# Telegram-webhook (extern — secret-header gevalideerd, CSRF-exempt)          #
# --------------------------------------------------------------------------- #


@router.post("/telegram/webhook")
async def telegram_webhook(request: Request, db: Session = Depends(get_db)) -> Response:
    """Ontvang Telegram-updates; koppel een chat_id bij een ``/start <token>``.

    Beveiliging: als er een webhook-secret is ingesteld MOET de
    ``X-Telegram-Bot-Api-Secret-Token``-header kloppen (anders 403). We geven altijd
    snel 200 terug (Telegram verwacht dat) en doen het werk best-effort.
    """
    secret = settings.telegram_webhook_secret
    if secret:
        got = request.headers.get("x-telegram-bot-api-secret-token", "")
        if got != secret:
            return Response(status_code=403)

    try:
        update = await request.json()
    except (ValueError, TypeError):
        return Response(status_code=200)

    token, chat_id = telegram_service.parse_start(update)
    if token and chat_id:
        if notification_service.link_telegram_from_start(db, token, chat_id):
            db.commit()
            telegram_service.send_message(
                chat_id,
                "<b>Gelukt — je bent gekoppeld.</b>\n\nJe krijgt voortaan hier je "
                "seintjes van dewereldvan.ai: zodra je profiel-ontdekking klaar is "
                "of iemand met je wil kennismaken.",
                button_text="Open dewereldvan.ai",
                button_url=f"{settings.base_url.rstrip('/')}/profiel/ai/bouwen",
            )
    return Response(status_code=200)
