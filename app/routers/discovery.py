"""Discovery-routes — de footprint-ontdekking als achtergrond-job + live-tail.

De expliciete profiel-actie "Zal ik je online opzoeken en je profiel aanvullen?"
start een **achtergrond-job** (``discovery_job_service``) die ``footprint_service.
discover`` draait en de gegronde bevindingen persisteert naar ``DiscoveryRun``. De
ontdekking duurt minuten; daarom houden we 'm NIET in de request: de SSE-route
*tailt* de gepersisteerde run. Wie wegklikt verliest niets — terugkeren toont het
bewaarde resultaat, en een seintje (in-app chip + e-mail) haalt het lid terug.
Per kaart: hoge confidence crystalliseert live mét undo; twijfel → 1-klik "klopt
dit?"-bevestigrij. NIETS wordt op het profiel gepersisteerd zonder de drempel/klik.

Self-only (AVG): elke route opereert UITSLUITEND op het profiel van het ingelogde
lid (``require_member``). CSRF via ``hx-headers``. ``Last-Event-ID`` laat de tail
na een reconnect hervatten zonder kaarten te herhalen.

Fase 1b — de crystalliseer/bevestig-laag: een vondst met hoge confidence
(``footprint_service.HIGH_CONFIDENCE``) crystalliseert live mét undo; een
twijfelgeval gaat naar de 1-klik "klopt dit?"-bevestigrij. Crystalliseren maakt
een ECHTE entiteit (project -> Offering + enrich; anders -> nieuws-Post).

Routes:
1. ``POST /profiel/ai/ontdek``           — start/hervat de job, of toon meteen het
   bewaarde resultaat (terugkeren). ``force`` = opnieuw zoeken.
2. ``GET  /profiel/ai/ontdek/stream``    — tail de run over SSE (candidate/done).
3. ``POST /profiel/ai/ontdek/koppel``    — render het voorgevulde draft-formulier voor
   één kandidaat (GEEN write; "aanpassen voor je koppelt").
4. ``POST /profiel/ai/ontdek/crystalliseer`` — koppel één vondst écht (Offering/nieuws),
   geef de "toegevoegd · ongedaan maken"-kaart terug. Self-only.
5. ``POST /profiel/ai/ontdek/ongedaan``  — maak een zojuist gecrystalliseerde vondst
   ongedaan (verwijdert de entiteit, self-only) → re-koppel-affordance.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import require_member
from app.models import Member
from app.services import (
    discovery_job_service,
    footprint_service,
    profile_service,
    project_enrich_service,
)

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


def _sse_event(event: str | None, data: str, *, event_id: int | None = None) -> str:
    """Format one SSE event. Multi-line ``data`` is split into ``data:`` lines.

    ``event_id`` zet het SSE ``id:``-veld → de browser stuurt het bij een
    reconnect terug als ``Last-Event-ID``, zodat de tail hervat zonder al
    getoonde kaarten te herhalen."""
    id_line = f"id: {event_id}\n" if event_id is not None else ""
    prefix = f"event: {event}\n" if event else ""
    lines = "".join(f"data: {line}\n" for line in data.split("\n"))
    return f"{id_line}{prefix}{lines}\n"


# Tail-parameters: de live-view tailt de gepersisteerde run. De job draait
# losgekoppeld in een thread, dus de tail mag rustig pollen en heeft een ruime
# wall-clock-veiligheidsklep (niet de oude 2-min-cap die het einde miste).
_TAIL_POLL_SEC: float = 1.2
_TAIL_MAX_SEC: float = 600.0


def _snapshot(member_id: int) -> tuple[str | None, list[dict]]:
    """(status, findings) van de run in een EIGEN sessie (voor de async tail).

    Aparte helper zodat de tail niet de request-sessie minutenlang vasthoudt —
    en zodat tests 'm kunnen patchen zonder DB.
    """
    from app.db import SessionLocal

    with SessionLocal() as db:
        return discovery_job_service.snapshot(db, member_id)


def _media_done(member_id: int) -> bool:
    """Of de media-verdieping al liep (eigen sessie, voor de async tail)."""
    from app.db import SessionLocal

    with SessionLocal() as db:
        return discovery_job_service.media_done(db, member_id)


def _candidate_html(request: Request, finding: dict) -> str:
    return _render_str(
        request,
        "discovery/_candidate.html",
        {
            "finding": finding,
            "auto": footprint_service.is_high_confidence(finding.get("confidence")),
        },
    )


# --------------------------------------------------------------------------- #
# 1. Start — (her)start de job, of toon meteen een afgerond resultaat          #
# --------------------------------------------------------------------------- #


@router.post("/profiel/ai/ontdek", response_class=HTMLResponse)
def start(
    request: Request,
    force: str = Form(""),
    verdieping: str = Form(""),
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Start/hervat de ontdekking, of toon een al-afgerond resultaat (self-only).

    - ``verdieping="media"`` → gerichte media-pass die de bestaande findings AANVULT
      (append) en de live-host rendert.
    - Geen/failed run, of ``force`` ("opnieuw zoeken") → start een achtergrond-job
      en render de live-host (de SSE tailt de run).
    - Lopende run → render de live-host (reconnect op de lopende job).
    - Afgeronde run (done/empty) zonder ``force`` → toon meteen het bewaarde
      resultaat (terugkeren) en markeer 'm als gezien (stilt de "klaar"-chip).
    """
    if not settings.ai_enrich_enabled:
        return _render(
            request, "discovery/_done.html",
            {"message": "AI-ontdekking staat momenteel uit."}, status_code=200,
        )
    profile_service.get_or_create_profile(db, member)
    db.commit()

    # Verdieping: gerichte media-pass die aanvult op wat er al is.
    if verdieping.strip() == "media":
        discovery_job_service.start(db, member, focus="media", append=True)
        return _render(request, "discovery/_stream_host.html", {})

    run = discovery_job_service.get_run(db, member.id)
    restart = bool(force.strip())

    if run is not None and not restart and run.status in (
        discovery_job_service.STATUS_DONE,
        discovery_job_service.STATUS_EMPTY,
    ):
        # Terugkeren: toon het bewaarde resultaat (geen nieuwe zoektocht).
        findings = discovery_job_service.findings_of(run)
        discovery_job_service.mark_seen(db, run)
        db.commit()
        return _render(
            request,
            "discovery/_result.html",
            {
                "findings": findings,
                "high": footprint_service.HIGH_CONFIDENCE,
                "resumed": True,
                "media_done": "media" in discovery_job_service.passes_of(run),
            },
        )

    if run is None or restart or run.status == discovery_job_service.STATUS_FAILED:
        discovery_job_service.start(db, member)

    return _render(request, "discovery/_stream_host.html", {})


# --------------------------------------------------------------------------- #
# 1b. Resultaat-deeplink — de "klaar"-chip landt hier op het bewaarde resultaat #
# --------------------------------------------------------------------------- #


@router.get("/profiel/ai/ontdek/resultaat", response_class=HTMLResponse)
def result_page(
    request: Request,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
):
    """Toon het bewaarde ontdekkings-resultaat (de in-app chip linkt hierheen).

    Afgeronde run (done/empty) → de resultaatpagina (markeert ``seen_at``, stilt
    de chip). Nog lopend / niets / mislukt → terug naar de bouwpagina (daar kan
    het lid de live-ontdekking starten of reconnecten). Self-only.
    """
    run = discovery_job_service.get_run(db, member.id)
    if run is None or run.status not in (
        discovery_job_service.STATUS_DONE,
        discovery_job_service.STATUS_EMPTY,
    ):
        return RedirectResponse("/profiel/ai/bouwen", status_code=303)
    findings = discovery_job_service.findings_of(run)
    media_done = "media" in discovery_job_service.passes_of(run)
    discovery_job_service.mark_seen(db, run)
    db.commit()
    return _render(
        request,
        "discovery/resultaat.html",
        {"findings": findings, "media_done": media_done},
    )


# --------------------------------------------------------------------------- #
# 2. SSE-tail — volg de gepersisteerde run (job draait losgekoppeld)           #
# --------------------------------------------------------------------------- #


@router.get("/profiel/ai/ontdek/stream")
async def stream(
    request: Request,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
):
    """Tail de ``DiscoveryRun`` over SSE (self-only).

    De achtergrond-job vult de run; deze generator leest 'm periodiek en zendt
    nieuwe kandidaten als kosmische kaarten + een afsluitende ``done``. ``Last-
    Event-ID`` (reconnect) laat de tail hervatten zonder kaarten te herhalen. De
    job loopt door als het lid wegklikt — terugkeren toont het bewaarde resultaat.
    """
    member_id = member.id

    async def _gen():
        if not settings.ai_enrich_enabled:
            yield _sse_event(
                "done",
                _render_str(request, "discovery/_done.html",
                            {"message": "AI-ontdekking staat momenteel uit."}),
            )
            return

        import asyncio
        import time

        try:
            sent = int(request.headers.get("last-event-id", "") or 0)
        except (TypeError, ValueError):
            sent = 0

        deadline = time.monotonic() + _TAIL_MAX_SEC
        while time.monotonic() < deadline:
            status, findings = await run_in_threadpool(_snapshot, member_id)

            while sent < len(findings):
                html = _candidate_html(request, findings[sent])
                sent += 1
                yield _sse_event("candidate", html, event_id=sent)

            if status is None or status == discovery_job_service.STATUS_RUNNING:
                await asyncio.sleep(_TAIL_POLL_SEC)
                continue

            # Terminale status → afsluitende melding (+ verdiepings-aanbod) en stop.
            if status == discovery_job_service.STATUS_FAILED:
                msg = "Er ging iets mis bij het zoeken. Probeer het later opnieuw."
            elif len(findings):
                msg = f"Ik vond {len(findings)} mogelijke vermeldingen."
            else:
                msg = "Ik kon online niets met zekerheid aan jou koppelen."
            done_html = _render_str(request, "discovery/_done.html", {"message": msg})
            if status == discovery_job_service.STATUS_DONE and findings:
                # Bied de gerichte media-verdieping aan (opt-in) — of toon dat 'ie al
                # liep. De partial past zich aan op ``media_done`` (geen dode knop).
                done_html += _render_str(
                    request, "discovery/_deepen_offer.html",
                    {"media_done": await run_in_threadpool(_media_done, member_id)},
                )
            yield _sse_event("done", done_html)
            return

        # Veiligheidsklep: job loopt nog na de ruime tail-deadline.
        yield _sse_event(
            "done",
            _render_str(
                request, "discovery/_done.html",
                {"message": "Dit duurt langer dan verwacht — kijk gerust rond; ik "
                            "zet je resultaat klaar en geef een seintje in de app "
                            "zodra het klaar is."},
            ),
        )

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


# --------------------------------------------------------------------------- #
# 4. Crystalliseer — koppel één vondst écht (Offering/nieuws), met undo        #
# --------------------------------------------------------------------------- #


@router.post("/profiel/ai/ontdek/crystalliseer", response_class=HTMLResponse)
def crystallize_candidate(
    request: Request,
    title: str = Form(""),
    url: str = Form(""),
    type: str = Form("other"),
    confidence: int = Form(0),
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Koppel één vondst écht aan het profiel en geef de undo-kaart terug.

    Eén chokepoint voor zowel de auto-crystallisatie (hoge confidence, de kaart
    POST op ``load``) als de 1-klik-bevestiging uit de "klopt dit?"-rij. project →
    ``Offering`` (+ achtergrond-enrich), anders → nieuws-``Post`` met rol-badge.
    Self-only (``require_member`` + het eigen profiel). Grounding-poort: een
    leeg/onveilig URL → geen koppeling.
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
    profile = profile_service.get_or_create_profile(db, member)
    result = footprint_service.crystallize(
        db, profile, member, title=title, url=clean_url, ftype=type
    )
    db.commit()
    # Een gekoppeld project pikt automatisch de screenshot+samenvatting op.
    if result.kind == "offering":
        project_enrich_service.trigger_async(result.id)
    return _render(
        request,
        "discovery/_crystallized.html",
        {
            "result": {"kind": result.kind, "id": result.id},
            "finding": {"title": title, "url": clean_url, "type": type},
        },
    )


# --------------------------------------------------------------------------- #
# 5. Ongedaan — verwijder een zojuist gecrystalliseerde entiteit (self-only)   #
# --------------------------------------------------------------------------- #


@router.post("/profiel/ai/ontdek/ongedaan", response_class=HTMLResponse)
def undo_candidate(
    request: Request,
    kind: str = Form(""),
    id: int = Form(0),
    title: str = Form(""),
    url: str = Form(""),
    type: str = Form("other"),
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Maak een zojuist gecrystalliseerde koppeling ongedaan (self-only).

    Verwijdert de Offering/nieuws-Post (eigendom afgedwongen in de service) en
    geeft een nette "ongedaan gemaakt"-kaart terug die de vondst nog laat
    her-koppelen (de fields reizen mee). Idempotent: een al verdwenen entiteit
    levert dezelfde kaart (geen 404-ruis in de live-flow).
    """
    profile = profile_service.get_or_create_profile(db, member)
    footprint_service.undo_crystallize(db, profile, member, kind=kind, entity_id=id)
    db.commit()
    return _render(
        request,
        "discovery/_undone.html",
        {"finding": {"title": title.strip()[:200], "url": safe_url(url.strip()), "type": type}},
    )
