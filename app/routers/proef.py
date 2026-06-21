"""Publieke voordeur (Concept A) — "plak een link, zie wat onze agent ziet".

Een NIET-lid plakt één URL; áchter de bestaande kosten-gate (``visitor_ai_guard``)
bouwt ÉÉN gecapte Opus-call een drie-delige mini-kaart (wie/wat · thema's · "bij
wie zou je passen"). Geen auth-dep: dit pad is bewust publiek.

Geld-kritisch pad (doc §4.3) — staat overzichtelijk in ``_run_card`` hieronder:
er gebeurt GEEN betaalde call vóór ``guard.check(...) == 'ok'``, en ná de call
draait ALTIJD ``guard.record_after_call(...)``. Faal-veilig: ontbrekende
Turnstile-keys / Browser Rendering / Telegram → nette kosmische staat, nooit een
crash, nooit ongemonitorde spend.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Depends, Form, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Member, MemberChannel, MemberRole
from app.security import client_ip, get_or_set_visitor_id
from app.services import (
    notification_service,
    telegram_service,
    turnstile_service,
    visitor_ai_guard,
    visitor_url_card,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["proef"])

_CONCEPT = "url_card"


def _render(request: Request, name: str, ctx: dict | None = None, **kw) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, name, ctx or {}, **kw)


def _normalize_url(raw: str) -> str | None:
    """Normaliseer een geplakte URL → http(s); None als het geen geldige URL is.

    Strip whitespace, lowercase de host, drop fragment + trailing slash. Alleen
    http/https met een host komt erdoor (anders nette inline-fout, geen call).
    """
    value = (raw or "").strip()
    if not value:
        return None
    # Zonder scheme: ga uit van https (een bezoeker plakt vaak "voorbeeld.nl").
    if "://" not in value:
        value = f"https://{value}"
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    host = parts.hostname.lower()
    netloc = host if not parts.port else f"{host}:{parts.port}"
    path = parts.path.rstrip("/")
    # Fragment weg; query behouden (kan betekenis dragen). Genormaliseerd terug.
    return urlunsplit((parts.scheme, netloc, path, parts.query, ""))


def _prompt_hash(normalized_url: str) -> str:
    """Hash van (concept, genormaliseerde URL) voor cache + dedup."""
    return hashlib.sha256(f"{_CONCEPT}:{normalized_url}".encode()).hexdigest()


# --------------------------------------------------------------------------- #
# GET /proef — landingspagina                                                 #
# --------------------------------------------------------------------------- #
@router.get("/proef", response_class=HTMLResponse)
def proef_page(request: Request) -> HTMLResponse:
    """Kosmische landing: URL-input + Turnstile, of de veilige-default-staat.

    Zonder geconfigureerde Turnstile-keys tonen we GEEN input maar een eerlijke
    "binnenkort / word lid"-staat (nul spend, veilige default, doc §4.2).
    """
    return _render(
        request,
        "proef/index.html",
        {
            "turnstile_configured": turnstile_service.configured(),
            "turnstile_site_key": settings.turnstile_site_key,
        },
    )


# --------------------------------------------------------------------------- #
# POST /proef — bouw de mini-kaart (htmx → resultaat-container)                #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class _Ctx:
    """Per-request identiteit + genormaliseerde input voor het geld-kritische pad."""

    visitor_id: str
    ip: str
    normalized_url: str
    prompt_hash: str


@router.post("/proef", response_class=HTMLResponse)
async def proef_submit(
    request: Request,
    url: str = Form(default=""),
    db: Session = Depends(get_db),
    cf_turnstile_response: str | None = Form(default=None, alias="cf-turnstile-response"),
) -> HTMLResponse:
    """Lees URL + turnstile-token, run de gate, en render het resultaat-fragment."""
    # De visitor-cookie wordt op het RESPONSE-object gezet; htmx-fragment-respons.
    response = HTMLResponse()
    visitor_id = get_or_set_visitor_id(request, response)
    ip = client_ip(request)

    # Veilige default: zonder Turnstile-keys nooit een call (toon CTA-staat).
    if not turnstile_service.configured():
        return _fragment(request, "proef/_unavailable.html", response)

    normalized = _normalize_url(url)
    if normalized is None:
        # URL-validatie: geen call, nette inline-fout.
        return _fragment(request, "proef/_invalid_url.html", response)

    ctx = _Ctx(
        visitor_id=visitor_id,
        ip=ip,
        normalized_url=normalized,
        prompt_hash=_prompt_hash(normalized),
    )
    return await _run_card(request, db, ctx, cf_turnstile_response, response)


async def _run_card(
    request: Request,
    db: Session,
    ctx: _Ctx,
    turnstile_token: str | None,
    response: HTMLResponse,
) -> HTMLResponse:
    """Het geld-kritische pad, op één plek: gate → (call) → boeken.

    GEEN betaalde Opus-call gebeurt vóór ``check()`` 'ok' teruggaf; ná de call
    draait ALTIJD ``record_after_call``. Elke niet-'ok'-reden rendert de nette
    degradatie-staat zonder een call (en zonder spend).
    """
    decision = visitor_ai_guard.check(
        db,
        visitor_id=ctx.visitor_id,
        ip=ctx.ip,
        concept=_CONCEPT,
        prompt_hash=ctx.prompt_hash,
        turnstile_token=turnstile_token,
    )

    # Cache-hit: serveer dezelfde kaart uit de eerdere rij (€0, geen call).
    if decision.reason == "cache" and decision.cache_hit is not None:
        return _card_fragment(request, decision.cache_hit.response_text or "", response)

    # Elke andere niet-'ok'-reden → nette degradatie-staat, geen call/spend.
    if not decision.allowed:
        return _degraded_fragment(request, decision.reason, response)

    # 'ok' → de call MAG. Dure stap: 1 fetch + ÉÉN gecapte Opus-call.
    try:
        result = await run_in_threadpool(
            visitor_url_card.build_card, ctx.normalized_url
        )
    except visitor_url_card.BrowserRenderUnavailable:
        # Fetch faalde/niet-geconfigureerd → nette foutstaat, GEEN boeking.
        return _fragment(request, "proef/_fetch_failed.html", response)
    except Exception:  # noqa: BLE001 — een call-fout mag het pad nooit crashen
        logger.warning("proef: Opus-call faalde", exc_info=True)
        return _fragment(request, "proef/_fetch_failed.html", response)

    # Stap 8 — boek de ECHTE token-usage; stap 9 — drempel-check.
    record = visitor_ai_guard.record_after_call(
        db,
        visitor_id=ctx.visitor_id,
        ip=ctx.ip,
        concept=_CONCEPT,
        prompt_hash=ctx.prompt_hash,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        response_text=result.text,
    )
    # Commit ná het boeken zodat de telling klopt voor de volgende request.
    db.commit()

    # Best-effort Telegram-ping bij 80%/100% weekcap (mag de respons nooit breken).
    if record.threshold_crossed in ("warn", "cap"):
        _ping_admins(db, record.threshold_crossed)

    return _card_fragment(request, result.text, response)


def _ping_admins(db: Session, threshold: str) -> None:
    """Ping admins met een verifieerd Telegram-kanaal bij een weekcap-drempel.

    Best-effort: faalt volledig stil — een falende of niet-geconfigureerde
    Telegram-ping mag de bezoeker-respons NOOIT breken (doc §2.4).
    """
    budget = settings.visitor_ai_budget_eur_per_week
    if threshold == "cap":
        text = (
            f"<b>Weekcap geraakt</b> (€{budget:.0f}/€{budget:.0f}) — niet-leden "
            "zien nu de proef-uitverkocht-staat. De gate weigerde de call al; "
            "geen geld weg."
        )
    else:
        text = (
            f"<b>Bezoeker-AI-budget op 80%</b> (≈ €{0.8 * budget:.0f}/€{budget:.0f} "
            "deze week)."
        )
    try:
        if not telegram_service.configured():
            return
        admins = db.scalars(
            select(Member)
            .join(MemberChannel, MemberChannel.member_id == Member.id)
            .where(
                Member.role == MemberRole.admin,
                MemberChannel.channel == notification_service.CHANNEL_TELEGRAM,
                MemberChannel.verified_at.is_not(None),
                MemberChannel.address.is_not(None),
            )
        ).all()
        for admin in admins:
            channel = notification_service._verified_telegram(db, admin)
            if channel and channel.address:
                telegram_service.send_message(channel.address, text)
    except Exception:  # noqa: BLE001 — een falende ping mag de respons nooit breken
        logger.warning("proef: Telegram-drempel-ping overgeslagen", exc_info=True)


# --------------------------------------------------------------------------- #
# Fragment-renderers (zetten de visitor-cookie op de fragment-respons)         #
# --------------------------------------------------------------------------- #
def _fragment(
    request: Request, name: str, response: HTMLResponse, ctx: dict | None = None
) -> HTMLResponse:
    """Render ``name`` als fragment, met de op ``response`` gezette cookies erbij."""
    rendered = _render(request, name, ctx or {})
    rendered.raw_headers.extend(response.raw_headers)
    return rendered


def _card_fragment(request: Request, text: str, response: HTMLResponse) -> HTMLResponse:
    """Render de mini-kaart uit de (gegenereerde of gecachte) kaarttekst."""
    parts = visitor_url_card.parse_card(text)
    return _fragment(request, "proef/_card.html", response, {"card": parts})


def _degraded_fragment(
    request: Request, reason: str, response: HTMLResponse
) -> HTMLResponse:
    """Nette, eerlijke degradatie-staat per gate-reden (doc §2.2)."""
    messages = {
        "turnstile": "Even verifieren dat je een mens bent — probeer het zo nog eens.",
        "burst": "Even geduld — je was net iets te snel. Probeer het over een halve minuut.",
        "day_visitor": "Je gebruikte vandaag de gratis proef — leden doen dit onbeperkt.",
        "day_ip": "Vanaf dit netwerk is de gratis proef vandaag op — leden doen dit onbeperkt.",
        "weekcap": "De gratis proef is deze week op — kom morgen terug of word lid.",
    }
    message = messages.get(reason, "De gratis proef is nu even niet beschikbaar.")
    return _fragment(
        request,
        "proef/_degraded.html",
        response,
        {"message": message, "reason": reason},
    )
