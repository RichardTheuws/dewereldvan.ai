"""Telegram Bot API — koppelen (deep-link + webhook) + verzenden.

Dun laagje over de Bot API (httpx, zoals de andere integraties). Gegate op
``settings.telegram_bot_token``: zonder token is alles een nette no-op (geen
thread-/netwerk-ruis in dev/test). Het koppelen verloopt via een deep-link
``t.me/<bot>?start=<token>``; de bot-**webhook** ontvangt ``/start <token>`` en
geeft ons de ``chat_id`` (zie ``notification_service.link_telegram_from_start``).

Beveiliging: ``setWebhook`` registreert een ``secret_token`` → Telegram stuurt dat
mee als ``X-Telegram-Bot-Api-Secret-Token``-header; de webhook-route valideert 'm.
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_API = "https://api.telegram.org"
_TIMEOUT = 8.0


def configured() -> bool:
    """True als er een bot-token is (anders is het kanaal niet beschikbaar)."""
    return bool(settings.telegram_bot_token)


def link_url(token: str) -> str | None:
    """De deep-link die het lid opent om Telegram te koppelen, of None.

    Vereist een bot-username (voor ``t.me/<bot>``). Zonder username kunnen we de
    link niet bouwen → None (de UI toont dan 'binnenkort').
    """
    username = (settings.telegram_bot_username or "").strip().lstrip("@")
    if not username or not token:
        return None
    return f"https://t.me/{username}?start={token}"


def _base() -> str:
    return f"{_API}/bot{settings.telegram_bot_token}"


def send_message(chat_id: str, text: str) -> bool:
    """Stuur één bericht naar een chat_id (best-effort; faalt stil → False)."""
    if not configured() or not chat_id:
        return False
    try:
        resp = httpx.post(
            f"{_base()}/sendMessage",
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning("Telegram sendMessage gaf %s", resp.status_code)
            return False
        return True
    except httpx.HTTPError:
        logger.warning("Telegram sendMessage faalde", exc_info=True)
        return False


def set_webhook() -> bool:
    """Registreer de webhook bij Telegram (idempotent). False bij ontbrekende creds.

    URL = ``<base_url>/telegram/webhook``; ``secret_token`` = de webhook-secret zodat
    we inkomende calls kunnen valideren. Aangeroepen bij startup als de creds er zijn.
    """
    if not configured():
        return False
    url = f"{settings.base_url.rstrip('/')}/telegram/webhook"
    payload: dict = {"url": url, "allowed_updates": ["message"]}
    if settings.telegram_webhook_secret:
        payload["secret_token"] = settings.telegram_webhook_secret
    try:
        resp = httpx.post(f"{_base()}/setWebhook", json=payload, timeout=_TIMEOUT)
        ok = resp.status_code == 200 and resp.json().get("ok") is True
        if not ok:
            logger.warning("Telegram setWebhook gaf %s: %s", resp.status_code, resp.text[:200])
        return ok
    except (httpx.HTTPError, ValueError):
        logger.warning("Telegram setWebhook faalde", exc_info=True)
        return False


def parse_start(update: dict) -> tuple[str | None, str | None]:
    """Lees ``(link_token, chat_id)`` uit een ``/start <token>``-update, anders (None, None).

    Behandelt de update UITSLUITEND als data; we lezen alleen de bekende velden.
    """
    if not isinstance(update, dict):
        return None, None
    msg = update.get("message")
    if not isinstance(msg, dict):
        return None, None
    text = str(msg.get("text", "")).strip()
    chat = msg.get("chat")
    chat_id = str(chat.get("id")) if isinstance(chat, dict) and chat.get("id") else None
    if not chat_id or not text.startswith("/start"):
        return None, chat_id
    parts = text.split(maxsplit=1)
    token = parts[1].strip() if len(parts) > 1 else ""
    return (token or None), chat_id
