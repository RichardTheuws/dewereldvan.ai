"""Concierge routes (Fase 1) — intent-oppervlak + gegronde SSE-stroom.

Hergebruikt het profielbouw-SSE-patroon 1:1 (``_sse_event`` + ``_Channel`` +
threadpool-drain). Routes (PRD §4.2):

1. ``POST /concierge/bericht``       — persist het lid-bericht, open de stream.
2. ``GET  /concierge/stream``        — SSE: reasoning/fetch/delta + ``card``-events
   (server-side gerenderde echte makerkaarten op slug → grounding-poort).
3. ``POST /concierge/nudge/dismiss`` — persisteer een dismiss (30 dagen stil).
4. ``POST /concierge/founder/verhaal`` — sla het ontstaansverhaal van een
   founder op (``member.origin_story``), wis de welkomst-flag.
5. ``GET  /concierge/index``         — de lichte makers-instant-index
   (display_name + tags, public+approved) zodat het frontend de client-side
   instant-laag lazy kan vullen zonder elke route te wijzigen.

GROUNDING: makerkaarten worden server-side uit de DB op slug gerenderd (een
verzonnen naam levert geen slug → geen kaart). De AVG-poort zit in de bron
(``members_service._public_base`` → public+approved). CSRF/auth ongewijzigd:
``/concierge/bericht``/``/nudge/dismiss``/``/founder/verhaal`` zijn POST's met de
bestaande CSRF-discipline; ``my_status``/founder vereisen een ingelogd lid.

De Concierge-conversatie hergebruikt de ``AiChatTurn``-state NIET (die is van de
profielbouw); de berichten leven per-stream in het verzoek. Voor Fase 1 voeren we
de conversatie als één user-turn de stream in (de frontend stuurt de vraag mee
bij ``/concierge/bericht`` en de stream leest 'm uit een korte sessie-buffer).
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from markupsafe import escape
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal, get_db
from app.deps import current_member, require_member
from app.models import Member
from app.services import (
    ai_conversation,
    concierge_service,
    emphasis_service,
    members_service,
    nudge_service,
    photo_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["concierge"])

# Sessie-sleutel waarin het laatste Concierge-bericht tot de stream geparkeerd
# staat (één vraag per opening; de stream consumeert 'm).
_SESSION_MSG_KEY = "concierge_pending_message"
# De founder-welkomst-flag (gezet bij login in auth.verify).
_SESSION_FOUNDER_KEY = "concierge_founder_welcome"


# --------------------------------------------------------------------------- #
# Render helpers                                                              #
# --------------------------------------------------------------------------- #


def _render_str(request: Request, name: str, ctx: dict | None = None) -> str:
    tmpl = request.app.state.templates.get_template(name)
    context = {"request": request, **(ctx or {})}
    return tmpl.render(context)


def _sse_event(event: str | None, data: str) -> str:
    """Format één SSE-event (mirror van ai_profile._sse_event)."""
    lines = "".join(f"data: {line}\n" for line in data.split("\n"))
    prefix = f"event: {event}\n" if event else ""
    return f"{prefix}{lines}\n"


def _card_html(request: Request, profile, *, shared_tags: list[str] | None = None) -> str:
    """Render één echte kosmische makerkaart server-side uit de DB (grounding).

    Gebruikt dezelfde helpers als de ledengids (``emphasis_class``/``photo_for``)
    zodat de kaart identiek is aan de constellatie. Valt terug op
    ``members/_member_star.html`` als de Concierge-wrapper nog niet bestaat.
    ``shared_tags`` (van ``connect``) levert de rustige "waarom"-regel.
    """
    ctx = {
        "profile": profile,
        "emphasis_class": emphasis_service.emphasis_class,
        "photo_for": photo_service.photo_or_initials,
        "shared_tags": shared_tags or [],
    }
    try:
        return _render_str(request, "concierge/_card.html", ctx)
    except Exception:  # noqa: BLE001 — wrapper optioneel; ster-kaart is de bron
        return _render_str(request, "members/_member_star.html", ctx)


# --------------------------------------------------------------------------- #
# 1. Bericht -> open de stream                                                #
# --------------------------------------------------------------------------- #


@router.post("/concierge/bericht", response_class=HTMLResponse)
def post_message(
    request: Request,
    message: str = Form(""),
    member: Member | None = Depends(current_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Parkeer de vraag in de sessie en render de SSE-host (gekloond patroon).

    Anoniem mag ook vragen (ontdekken); ``connect``/``my_status`` blijven per
    constructie leeg voor anoniem (geen viewer-profiel). De stream zelf opent via
    ``GET /concierge/stream``.
    """
    text = (message or "").strip()
    request.session[_SESSION_MSG_KEY] = text[:2000]
    return _render(request, "concierge/_stream.html", {})


def _render(request: Request, name: str, ctx: dict | None = None, **kw) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, name, ctx or {}, **kw)


# --------------------------------------------------------------------------- #
# 2. SSE stream — reasoning/fetch/delta + card-events                         #
# --------------------------------------------------------------------------- #


@router.get("/concierge/stream")
async def stream(
    request: Request,
    member: Member | None = Depends(current_member),
    db: Session = Depends(get_db),
):
    """Server-Sent Events voor de Concierge-stroom.

    ``reasoning`` (thinking-glow) → ``fetch`` (tool-status fetch-line) → ``delta``
    (woord-voor-woord, HTML-escaped) → ``card`` (server-side gerenderde echte
    makerkaart op slug) → ``done``. Faal-takken leveren altijd een nette ``done``.
    """
    pending = (request.session.get(_SESSION_MSG_KEY) or "").strip()
    member_id = member.id if member is not None else None

    text_ch = ai_conversation._Channel()
    think_ch = ai_conversation._Channel()
    tool_ch = ai_conversation._Channel()
    card_ch = ai_conversation._Channel()
    nav_ch = ai_conversation._Channel()

    messages = [{"role": "user", "content": pending or "Hallo"}]

    def _run() -> object | None:
        try:
            return concierge_service.stream_concierge(
                messages,
                text_ch.send,
                db=db,
                viewer=member,
                on_card=card_ch.send,
                on_navigate=nav_ch.send,
                on_thinking=think_ch.send,
                on_tool_event=lambda e: tool_ch.send(json.dumps(e)),
            )
        except Exception:  # noqa: BLE001 — surface as a friendly message
            logger.exception("Concierge stream faalde voor member %s", member_id)
            return None
        finally:
            text_ch.close()
            think_ch.close()
            tool_ch.close()
            card_ch.close()
            nav_ch.close()

    async def _gen():
        if not settings.ai_enrich_enabled:
            yield _sse_event("done", "")
            return

        import asyncio
        import time

        from app.services.ai_conversation import CHANNEL_TIMEOUT_SEC

        task = asyncio.ensure_future(run_in_threadpool(_run))
        deadline = time.monotonic() + CHANNEL_TIMEOUT_SEC

        text_done = think_done = tool_done = card_done = nav_done = False
        while not (
            text_done and think_done and tool_done and card_done and nav_done
        ):
            if time.monotonic() > deadline:
                logger.warning(
                    "Concierge stream-drain timeout voor member %s; stop.",
                    member_id,
                )
                break
            if not think_done:
                item = await run_in_threadpool(think_ch.get, 0.02)
                if item is None and task.done() and think_ch.q.empty():
                    think_done = True
                elif item is not None:
                    yield _sse_event("reasoning", str(escape(item)))
                    continue
            if not tool_done:
                item = await run_in_threadpool(tool_ch.get, 0.02)
                if item is None and task.done() and tool_ch.q.empty():
                    tool_done = True
                elif item is not None:
                    yield _sse_event("fetch", _format_fetch(item))
                    continue
            if not nav_done:
                url = await run_in_threadpool(nav_ch.get, 0.02)
                if url is None and task.done() and nav_ch.q.empty():
                    nav_done = True
                elif url is not None:
                    # Alleen een interne (relatieve) path; de browser valideert
                    # nogmaals tegen open-redirect.
                    if isinstance(url, str) and url.startswith("/"):
                        yield _sse_event("navigate", url)
                    continue
            if not card_done:
                signal = await run_in_threadpool(card_ch.get, 0.02)
                if signal is None and task.done() and card_ch.q.empty():
                    card_done = True
                elif signal is not None:
                    html = await run_in_threadpool(_render_card_by_signal, signal)
                    if html:
                        yield _sse_event("card", html)
                        # Choreografie-pauze (begrensd door het wall-clock-vangnet).
                        await run_in_threadpool(time.sleep, 0.08)
                    continue
            if not text_done:
                item = await run_in_threadpool(text_ch.get, 0.02)
                if item is None and task.done() and text_ch.q.empty():
                    text_done = True
                elif item is not None:
                    yield _sse_event("delta", str(escape(item)))
                    continue

        if task.done():
            final = await task
        else:
            try:
                final = await asyncio.wait_for(asyncio.shield(task), timeout=1.0)
            except TimeoutError:
                final = None

        if final is not None and getattr(final, "stop_reason", None) == "refusal":
            yield _sse_event(
                "delta",
                str(
                    escape(
                        "Daar kan ik niet op ingaan. Stel je vraag gerust anders."
                    )
                ),
            )

        # Vraag verbruikt; volgende opening begint schoon.
        request.session.pop(_SESSION_MSG_KEY, None)
        yield _sse_event("done", "")

    def _render_card_by_signal(signal: object) -> str | None:
        """Grounding-poort: render een kaart in een EIGEN, kortlevende sessie.

        De tool-loop (``_run``) draait al op de request-``db`` in de threadpool;
        deze drain-thread mag die Session NIET aanraken (één SQLAlchemy Session is
        niet thread-safe). Daarom opent elke kaart-render zijn eigen
        ``SessionLocal``. De grounding-poort blijft: alleen een echte public+
        approved slug levert een profiel → een kaart. ``signal`` is een slug-str
        (search) of een dict ``{"slug": ..., "shared_tags": [...]}`` (connect).
        """
        if isinstance(signal, dict):
            slug = signal.get("slug") or ""
            shared_tags = signal.get("shared_tags") or []
        else:
            slug = str(signal)
            shared_tags = []
        with SessionLocal() as card_db:
            profile = concierge_service._public_profile_by_slug(card_db, slug)
            if profile is None:
                return None
            return _card_html(request, profile, shared_tags=shared_tags)

    return StreamingResponse(_gen(), media_type="text/event-stream")


def _format_fetch(raw: str) -> str:
    """Vorm een tool-event-JSON om tot een leesbare fetch-line (PRD §2.3)."""
    try:
        ev = json.loads(raw)
    except (ValueError, TypeError):
        return raw
    tool = ev.get("tool", "")
    count = ev.get("count")
    state = ev.get("state", "ok")
    labels = {
        "search_members": "de gids doorzoeken",
        "connect": "een maker oppervlakken",
        "navigate": "de route bepalen",
        "explain": "het platform raadplegen",
        "my_status": "je profiel nakijken",
    }
    label = labels.get(tool, tool)
    if state == "err":
        return json.dumps({"label": label, "state": "err"})
    if count is not None:
        woord = "maker" if count == 1 else "makers"
        return json.dumps(
            {"label": f"{count} {woord} gevonden", "state": "ok"}
        )
    return json.dumps({"label": label, "state": "ok"})


# --------------------------------------------------------------------------- #
# 3a. Proactieve nudge — lazy fragment (alleen bij open oppervlak)            #
# --------------------------------------------------------------------------- #


def _nudge_view_model(nudge: nudge_service.Nudge) -> dict:
    """Map de ``Nudge``-dataclass op de velden die ``_nudge.html`` verwacht.

    Template-contract: ``kind``/``text``/``action`` + één van ``prompt``
    (vult het Concierge-veld) of ``url`` (navigeert). De ``action``-string van
    de service draagt het client-intent:
      - ``"navigate:/pad"``  → ``url`` (knop navigeert)
      - ``"connect:{slug}"`` → ``prompt`` (open de stream met een intro-vraag)
      - ``"founder"``        → ``prompt`` (open de stream in verhaal-modus)
    """
    vm: dict = {
        "kind": nudge.kind,
        "text": nudge.message,
        "action": nudge.action_label,
    }
    action = nudge.action or ""
    if action.startswith("navigate:"):
        vm["url"] = action.split(":", 1)[1]
    elif action.startswith("connect:"):
        slug = action.split(":", 1)[1]
        vm["prompt"] = f"Stel me voor aan {slug}."
    elif action == "founder":
        vm["prompt"] = "Ik vertel je graag het ontstaansverhaal van dewereldvan.ai."
    return vm


@router.get("/concierge/nudge", response_class=HTMLResponse)
def nudge_fragment(
    request: Request,
    member: Member | None = Depends(current_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Het gerenderde proactieve-nudge-fragment (of leeg) — PRD §2.4.

    Wordt door het JS-eiland gefetcht wanneer het oppervlak met een leeg veld
    opent. Eén nudge max; geen sterke trigger → leeg (geen vulling). De
    founder-welkomst (eenmalige sessie-flag) heeft voorrang en opent de stroom in
    'vertel je ontstaansverhaal'-modus.
    """
    # Founder-welkomst (PRD §5.2): de eenmalige flag, alleen voor een herkende
    # founder die zijn verhaal nog niet vastlegde.
    founder_flag = bool(request.session.get(_SESSION_FOUNDER_KEY))
    if (
        founder_flag
        and member is not None
        and member.is_founder
        and member.origin_story is None
    ):
        nudge = nudge_service.founder_welcome_nudge(member)
        return _render(
            request, "concierge/_nudge.html", {"nudge": _nudge_view_model(nudge)}
        )

    cookie_kinds = set(request.session.get("concierge_dismissed", []))
    nudge = nudge_service.select_nudge(
        db, member, dismissed_cookie_kinds=cookie_kinds
    )
    if nudge is None:
        return HTMLResponse("")
    return _render(
        request, "concierge/_nudge.html", {"nudge": _nudge_view_model(nudge)}
    )


# --------------------------------------------------------------------------- #
# 3. Nudge dismiss (30 dagen stil)                                            #
# --------------------------------------------------------------------------- #


@router.post("/concierge/nudge/dismiss")
def dismiss_nudge(
    request: Request,
    nudge_kind: str = Form(""),
    member: Member | None = Depends(current_member),
    db: Session = Depends(get_db),
):
    """Persisteer een dismiss. Ingelogd → DB-rij; anoniem → sessie-cookie-set."""
    kind = (nudge_kind or "").strip()[:120]
    if not kind:
        return JSONResponse({"ok": False}, status_code=400)

    if member is not None:
        nudge_service.dismiss(db, member, kind)
        db.commit()
    else:
        dismissed = set(request.session.get("concierge_dismissed", []))
        dismissed.add(kind)
        request.session["concierge_dismissed"] = sorted(dismissed)

    # Wis de eenmalige founder-welkomst-flag óók bij dismiss van de founder-nudge,
    # zodat 'later' de welkomst niet bij elke paginaload terugbrengt.
    if kind == nudge_service.FOUNDER_NUDGE_KIND:
        request.session.pop(_SESSION_FOUNDER_KEY, None)
    return JSONResponse({"ok": True})


# --------------------------------------------------------------------------- #
# 4. Founder ontstaansverhaal opslaan                                         #
# --------------------------------------------------------------------------- #


@router.post("/concierge/founder/verhaal")
def save_origin_story(
    request: Request,
    verhaal: str = Form(""),
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
):
    """Sla het ontstaansverhaal op (alleen een herkende founder), wis de flag."""
    if not member.is_founder:
        return JSONResponse({"ok": False, "reden": "geen oprichter"}, status_code=403)
    text = (verhaal or "").strip()
    if not text:
        return JSONResponse({"ok": False, "reden": "leeg"}, status_code=400)
    member.origin_story = text[:8000]
    db.commit()
    request.session.pop(_SESSION_FOUNDER_KEY, None)
    return JSONResponse({"ok": True})


# --------------------------------------------------------------------------- #
# 5. Makers-instant-index (lichte client-side index)                          #
# --------------------------------------------------------------------------- #


# De vaste route-rijen voor de instant-laag (PRD §2.2). Het JS leest
# ``{label, url, keywords}``; "mijn profiel" verschijnt alleen voor een ingelogd lid.
_INSTANT_ROUTES: list[dict] = [
    {"label": "Leden", "url": "/leden", "keywords": ["leden", "gids", "makers", "wie"]},
    {"label": "Ideeën", "url": "/ideeen", "keywords": ["ideeen", "ideeën", "ideeenbus", "idee"]},
    {"label": "Roadmap", "url": "/roadmap", "keywords": ["roadmap", "planning", "gepland"]},
]
_INSTANT_ROUTE_PROFILE: dict = {
    "label": "Mijn profiel",
    "url": "/profiel/ai/bouwen",
    "keywords": ["profiel", "mijn", "bewerken", "afmaken"],
}


@router.get("/concierge/index")
def instant_index(
    member: Member | None = Depends(current_member),
    db: Session = Depends(get_db),
):
    """De lichte makers-index voor de client-side instant-laag (PRD §2.2).

    Levert ``routes`` (de vaste navigatie-rijen, met "mijn profiel" voor een
    ingelogd lid) én ``members`` (``name`` + ``tags`` + ``slug`` van public+
    approved profielen) — door dezelfde AVG-poort als de ledengids. Het JS in
    ``_concierge.html`` leest ``routes[].label/url/keywords`` en
    ``members[].name/slug/tags``. Geen LLM, één query.
    """
    routes = list(_INSTANT_ROUTES)
    if member is not None:
        routes.append(_INSTANT_ROUTE_PROFILE)

    profiles = members_service.list_public_profiles(db)
    items = [
        {
            "slug": p.slug,
            "name": p.display_name,
            "tags": [t.name for t in p.tags],
        }
        for p in profiles
    ]
    return JSONResponse({"routes": routes, "members": items})
