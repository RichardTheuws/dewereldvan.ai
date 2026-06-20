"""Discovery-routes (Fase 1a) — de live-streamende footprint-ontdekking.

De expliciete profiel-actie "Zal ik je online opzoeken en je profiel aanvullen?"
→ ``footprint_service.discover`` zoekt het lid op, disambigueert, classificeert en
streamt de gegronde bevindingen live de canvas in (kosmische kaarten die
voorbijvliegen + crystalliseren). Per kaart: ✓ Koppelen (→ voorgevuld draft naar
een bestaand endpoint) / ✗ Negeren (kaart verdwijnt). NIETS wordt gepersisteerd
zonder de bevestig-klik.

Self-only (AVG): elke route opereert UITSLUITEND op het profiel van het ingelogde
lid (``require_member``). CSRF via ``hx-headers``. Spiegelt de SSE-machinerie van
``ai_profile`` (``_sse_event`` + ``ai_conversation._Channel`` + ``run_in_threadpool``-
drain + ``CHANNEL_TIMEOUT_SEC``).

Routes:
1. ``POST /profiel/ai/ontdek``        — start (render de discovery-host; opent de SSE).
2. ``GET  /profiel/ai/ontdek/stream`` — de SSE-stroom (search/reasoning/candidate/done).
3. ``POST /profiel/ai/ontdek/koppel`` — render het voorgevulde draft-formulier voor
   één kandidaat (GEEN write; het lid bevestigt via het bestaande endpoint).
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, StreamingResponse
from markupsafe import escape
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import require_member
from app.models import Member
from app.services import ai_conversation, footprint_service, profile_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["discovery"])


def _render(request: Request, name: str, ctx: dict | None = None, **kw) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, name, ctx or {}, **kw)


def _render_str(request: Request, name: str, ctx: dict | None = None) -> str:
    """Render a template to a plain string (for embedding in an SSE event)."""
    tmpl = request.app.state.templates.get_template(name)
    context = {"request": request, **(ctx or {})}
    from app.csrf import get_csrf_token

    context.setdefault("csrf_token", get_csrf_token(request))
    return tmpl.render(context)


def safe_url(value: str | None) -> str:
    """Lazy proxy naar de gedeelde ``safe_url``-filter (vermijdt circulaire import)."""
    from app.main import safe_url as _safe_url

    return _safe_url(value)


def _sse_event(event: str | None, data: str) -> str:
    """Format one SSE event. Multi-line ``data`` is split into ``data:`` lines."""
    lines = "".join(f"data: {line}\n" for line in data.split("\n"))
    prefix = f"event: {event}\n" if event else ""
    return f"{prefix}{lines}\n"


# --------------------------------------------------------------------------- #
# 1. Start — render de discovery-host (opent de SSE)                           #
# --------------------------------------------------------------------------- #


@router.post("/profiel/ai/ontdek", response_class=HTMLResponse)
def start(
    request: Request,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Open de live-ontdekking (SSE-host). Self-only: het eigen profiel."""
    if not settings.ai_enrich_enabled:
        return _render(
            request,
            "discovery/_done.html",
            {"message": "AI-ontdekking staat momenteel uit."},
            status_code=200,
        )
    # Borg dat het eigen profiel bestaat (de stream opereert erop).
    profile_service.get_or_create_profile(db, member)
    db.commit()
    return _render(request, "discovery/_stream_host.html", {})


# --------------------------------------------------------------------------- #
# 2. SSE-stream — search / reasoning / candidate / done                       #
# --------------------------------------------------------------------------- #


@router.get("/profiel/ai/ontdek/stream")
async def stream(
    request: Request,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
):
    """Server-Sent Events voor de footprint-ontdekking (self-only).

    ``footprint_service.discover`` draait in een threadpool en duwt (event, data)
    via één ``_Channel``; de async generator pompt die naar de browser. De
    ``candidate``-events dragen een server-side gerenderde kosmische kaart (echte
    data). Faal-takken leveren altijd een nette ``done``.
    """
    profile = profile_service.get_or_create_profile(db, member)
    member_id = member.id
    ch = ai_conversation._Channel()

    def _run() -> None:
        try:
            footprint_service.discover(
                profile, lambda event, data: ch.send((event, data))
            )
        except Exception:  # noqa: BLE001 — surface as a friendly done, no traceback
            logger.exception("Discovery faalde voor member %s", member_id)
            ch.send(("done", "Er ging iets mis bij het zoeken."))
        finally:
            ch.close()

    async def _gen():
        if not settings.ai_enrich_enabled:
            yield _sse_event(
                "done",
                _render_str(
                    request, "discovery/_done.html",
                    {"message": "AI-ontdekking staat momenteel uit."},
                ),
            )
            return

        import asyncio
        import time

        from app.services.ai_conversation import CHANNEL_TIMEOUT_SEC

        task = asyncio.ensure_future(run_in_threadpool(_run))
        deadline = time.monotonic() + CHANNEL_TIMEOUT_SEC

        done = False
        while not done:
            if time.monotonic() > deadline:
                logger.warning(
                    "Discovery stream-drain timeout voor member %s; stop.", member_id
                )
                break
            item = await run_in_threadpool(ch.get, 0.05)
            if item is None and task.done() and ch.q.empty():
                done = True
                continue
            if item is None:
                continue
            event, data = item
            if event == "candidate":
                # Render de echte kandidaat als kosmische kaart (server-side).
                try:
                    finding = json.loads(data)
                except (ValueError, TypeError):
                    continue
                html = _render_str(
                    request, "discovery/_candidate.html", {"finding": finding}
                )
                yield _sse_event("candidate", html)
                # Choreografie-pauze (begrensd door het wall-clock-vangnet).
                await run_in_threadpool(time.sleep, 0.12)
            elif event == "done":
                yield _sse_event(
                    "done", _render_str(request, "discovery/_done.html", {"message": data})
                )
            else:  # search / reasoning
                yield _sse_event(event, str(escape(data)))

        if not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=1.0)
            except TimeoutError:
                pass

    return StreamingResponse(_gen(), media_type="text/event-stream")


# --------------------------------------------------------------------------- #
# 3. Koppel — render het voorgevulde draft-formulier (GEEN write)             #
# --------------------------------------------------------------------------- #


@router.post("/profiel/ai/ontdek/koppel", response_class=HTMLResponse)
def link_candidate(
    request: Request,
    title: str = Form(""),
    url: str = Form(""),
    type: str = Form("other"),
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Render een voorgevuld draft-formulier voor één bevestigde kandidaat.

    Géén DB-write hier — het lid bevestigt straks via het BESTAANDE endpoint:
    - project → ``POST /profiel/ai/offering`` (url+title → de screenshot/summary-
      enrichment pakt 'm daarna automatisch op);
    - media/blog/talk/social/other → ``POST /nieuws`` (url+title+rol-badge).
    De grounding-poort: een leeg/onveilige URL → geen koppeling.
    """
    title = title.strip()[:200]
    clean_url = safe_url(url.strip())
    if not title or not clean_url:
        return _render(
            request,
            "discovery/_done.html",
            {"message": "Deze kandidaat mist een geldige link."},
            status_code=400,
        )
    if type == "project":
        return _render(
            request,
            "discovery/_draft_offering.html",
            {"fields": {"title": title, "url": clean_url}},
        )
    # media/blog/talk/social/other → een nieuws-item met passende rol-badge.
    # blog = zelf geschreven; talk/media/social/overig = vermeld (lid past zelf aan).
    role = "geschreven" if type == "blog" else "vermeld" if type in ("talk", "media") else "gedeeld"
    return _render(
        request,
        "discovery/_draft_news.html",
        {"fields": {"title": title, "url": clean_url, "role": role}},
    )
