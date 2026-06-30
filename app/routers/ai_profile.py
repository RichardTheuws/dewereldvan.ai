"""AI-native, *levende* profielbouw routes (één flow).

Eén levende flow (zie ``docs/SPEC-living-profielbouw.md``):

    tekst → het profiel materialiseert zich live in de echte kosmische profielvorm
    → daarna volledig inline bijschaven.

Geen chat-ping-pong, geen aparte draft-preview, geen apart bewerk-formulier.

Routes (alle onder ``require_member`` — ingelogd + approved; CSRF via ``hx-headers``):

1. ``GET  /profiel/ai/bouwen``      — ``ai/live.html`` uit DB-staat (idempotent herstel).
2. ``POST /profiel/ai/bericht``     — persist user-turn, render ``ai/_materialize_stream.html``
   (SSE-host; GEEN chat-bubbel) in ``#denkpaneel``.
3. ``GET  /profiel/ai/stream``      — SSE: Fase 1 (reasoning/fetch/delta, ongewijzigd),
   dan Fase 2 (``finalize_draft`` → persist → per-veld ``f-*``-events die de
   profielvorm sectie-voor-sectie materialiseren), tot ``done``.
4. ``POST /profiel/ai/cover``       — cover via ImageGenerator (faalt gracieus).
5. Per-veld inline-edit endpoints (headline/bio/seeking/tags + offerings + rollen):
   GET ``…/bewerken`` → edit-form, GET ``…`` → lees-slot (cancel), PATCH → persist +
   lees-slot, POST/DELETE voor toevoegen/verwijderen. Marker-``bevestig``.
6. ``POST /profiel/ai/maak-draft``  — OVERGANG: rendert de levende vorm (``_live_form``)
   i.p.v. de oude preview; verdwijnt zodra de stream-variant groen test.
7. ``POST /profiel/ai/publiceren``  — delegeert naar de zichtbaarheidsflow (consent
   voor public), wist de conversatie, 303 naar het profiel.
8. ``POST /profiel/ai/opnieuw``     — nieuwe sessie (AVG-reset: turns + ai-flags + cover).

Auto-publiceren gebeurt NOOIT. SSE-deltas worden HTML-escaped (anti-XSS). URL-velden
lopen door ``safe_url``. Eigendoms-check op elke ``{id}`` (anders 404).
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import (
    HTMLResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from markupsafe import escape
from sqlalchemy.orm import Session

from app.ai import ImageGenerator, NoopImageGenerator
from app.config import settings
from app.db import get_db
from app.deps import image_generator, require_member
from app.models import (
    Member,
    Need,
    Offering,
    OfferingKind,
    Profile,
    ProfileLink,
    ProfileLinkKind,
)
from app.schemas.ai_profile import AcceptForm, ChatMessageForm
from app.services import (
    ai_conversation,
    cover_art_service,
    cover_service,
    offering_slug,
    photo_service,
    profile_link_service,
    profile_service,
    project_enrich_service,
    tool_review_service,
    tool_service,
)
from app.services import ai_profile as ai_service
from app.services import visibility as visibility_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ai-profile"])

def safe_url(value: str | None) -> str:
    """Lazy proxy naar de gedeelde ``safe_url``-filter (vermijdt circulaire import).

    ``app.main`` importeert deze router bij opstart, dus we kunnen ``safe_url`` niet
    op module-niveau uit ``app.main`` halen; lazy import binnen de call is veilig.
    """
    from app.main import safe_url as _safe_url

    return _safe_url(value)


# Velden die per-veld bewerkbaar zijn als losse tekst-slots.
_TEXT_FIELDS = {"headline", "bio", "seeking", "tags", "tools"}
# Maximale lengtes (spiegelen het datamodel / contract §A.1).
_MAXLEN = {
    "headline": 200,
    "bio": 4000,
    "seeking": 2000,
    "tags": 1000,
    "tools": 1000,
}


# --------------------------------------------------------------------------- #
# Render helpers                                                              #
# --------------------------------------------------------------------------- #


def _render(request: Request, name: str, ctx: dict | None = None, **kw) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, name, ctx or {}, **kw)


def _render_str(request: Request, name: str, ctx: dict | None = None) -> str:
    """Render a template to a plain string (for embedding in an SSE event)."""
    tmpl = request.app.state.templates.get_template(name)
    context = {"request": request, **(ctx or {})}
    from app.csrf import get_csrf_token

    context.setdefault("csrf_token", get_csrf_token(request))
    return tmpl.render(context)


def _emphasis_cls(profile: Profile) -> str:
    return f"emphasis-{profile.emphasis.value}"


def _form_ctx(request: Request, profile: Profile, **extra) -> dict:
    """Gedeelde context voor de levende vorm + slots."""
    return {
        "request": request,
        "profile": profile,
        "photo": photo_service.photo_or_initials(profile),
        "emphasis_cls": _emphasis_cls(profile),
        **extra,
    }


# --------------------------------------------------------------------------- #
# 1. Living build page                                                        #
# --------------------------------------------------------------------------- #


@router.get("/profiel/ai/bouwen", response_class=HTMLResponse)
def build_page(
    request: Request,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """De levende profielbouw-pagina; rendert de profielvorm uit DB-staat.

    Idempotent herstel: alles wat de stream materialiseert is gepersisteerd, dus
    een herlaad toont exact de huidige staat (geen verloren werk).
    """
    profile = profile_service.get_or_create_profile(db, member)
    db.commit()
    # Discovery-staat zodat de ontdek-CTA zich aanpast (geen "verse" knop tonen als
    # je jezelf al hebt opgezocht).
    from app.services import discovery_job_service

    drun = discovery_job_service.get_run(db, member.id)
    return _render(
        request,
        "ai/live.html",
        _form_ctx(
            request,
            profile,
            ai_enabled=settings.ai_enrich_enabled,
            uncertain=bool(profile.ai_enriched),
            discovery_done=drun is not None and drun.status in (
                discovery_job_service.STATUS_DONE, discovery_job_service.STATUS_EMPTY
            ),
            discovery_media_done="media" in discovery_job_service.passes_of(drun),
        ),
    )


# --------------------------------------------------------------------------- #
# 2. Member message -> open the materialize stream                            #
# --------------------------------------------------------------------------- #


@router.post("/profiel/ai/bericht", response_class=HTMLResponse)
def post_message(
    request: Request,
    message: str = Form(""),
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Persist het lid-bericht en open de SSE-materialisatie (geen chat-bubbel)."""
    if not settings.ai_enrich_enabled:
        return _render(
            request,
            "ai/_materialize_done.html",
            {"message": "AI-profielbouw staat momenteel uit."},
            status_code=200,
        )

    try:
        data = ChatMessageForm(message=message)
    except ValueError:
        return _render(
            request,
            "ai/_materialize_done.html",
            {"message": "Typ eerst iets over jezelf."},
            status_code=400,
        )

    try:
        ai_service.check_enrich_rate_limit(db, member)
    except ai_service.EnrichmentRateLimited:
        return _render(
            request,
            "ai/_materialize_done.html",
            {
                "message": (
                    "Je hebt het uur-limiet bereikt. Probeer het over een uur "
                    "opnieuw."
                )
            },
            status_code=429,
        )

    ai_conversation.append_turn(db, member, "user", data.message)
    db.commit()

    return _render(request, "ai/_materialize_stream.html", {})


# --------------------------------------------------------------------------- #
# 3. SSE stream — Fase 1 (reasoning/fetch/delta) + Fase 2 (materialize fields) #
# --------------------------------------------------------------------------- #


def _sse_event(event: str | None, data: str) -> str:
    """Format one SSE event. Multi-line ``data`` is split into ``data:`` lines."""
    lines = "".join(f"data: {line}\n" for line in data.split("\n"))
    prefix = f"event: {event}\n" if event else ""
    return f"{prefix}{lines}\n"


@router.get("/profiel/ai/stream")
async def stream(
    request: Request,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
):
    """Server-Sent Events voor de levende-flow.

    Fase 1 (ongewijzigd t.o.v. de chat-flow): ``reasoning``/``fetch``/``delta``.
    De tekst-deltas worden geescaped (anti-XSS). De assistant-turn wordt vóór
    Fase 2 gepersisteerd zodat ``finalize_draft`` de complete history ziet.

    Fase 2 (zelfde threadpool-context, na de stream): ``finalize_draft`` →
    ``profile_service.persist_draft`` → ``db.refresh`` → per veld een uniek-benoemd ``f-*``-event
    met het serverside slot-fragment, met een korte choreografie-pauze ertussen.

    Faal-takken (nooit een kapotte vorm): refusal/rate-limit/exception/timeout →
    ``done`` met een nette melding; de profielvorm blijft de vorige (DB-)staat.
    """
    messages = ai_conversation.load_messages(db, member)
    text_ch = ai_conversation._Channel()
    think_ch = ai_conversation._Channel()
    tool_ch = ai_conversation._Channel()
    member_id = member.id

    def _run() -> object | None:
        try:
            return ai_service.stream_turn(
                messages,
                text_ch.send,
                on_thinking=think_ch.send,
                on_tool_event=lambda e: tool_ch.send(json.dumps(e)),
            )
        except Exception:  # noqa: BLE001 — surface as a friendly message, no traceback
            logger.exception("AI stream_turn faalde voor member %s", member_id)
            return None
        finally:
            text_ch.close()
            think_ch.close()
            tool_ch.close()

    async def _gen():
        if not settings.ai_enrich_enabled:
            yield _sse_event(
                "done",
                _render_str(
                    request,
                    "ai/_materialize_done.html",
                    {"message": "AI-profielbouw staat momenteel uit."},
                ),
            )
            return

        import asyncio
        import time

        from app.services.ai_conversation import CHANNEL_TIMEOUT_SEC

        task = asyncio.ensure_future(run_in_threadpool(_run))
        deadline = time.monotonic() + CHANNEL_TIMEOUT_SEC

        text_done = think_done = tool_done = False
        streamed_parts: list[str] = []
        while not (text_done and think_done and tool_done):
            if time.monotonic() > deadline:
                logger.warning(
                    "AI stream-drain timeout (%.0fs) voor member %s; stop.",
                    CHANNEL_TIMEOUT_SEC,
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
                    yield _sse_event("fetch", item)
                    continue
            if not text_done:
                item = await run_in_threadpool(text_ch.get, 0.02)
                if item is None and task.done() and text_ch.q.empty():
                    text_done = True
                elif item is not None:
                    streamed_parts.append(item)
                    yield _sse_event("delta", str(escape(item)))
                    continue

        if task.done():
            final = await task
        else:
            try:
                final = await asyncio.wait_for(asyncio.shield(task), timeout=1.0)
            except TimeoutError:
                final = None

        # --- Fase 1 afronding: persisteer de assistant-turn (history compleet) ---
        refused = False
        if final is None:
            done_msg = "Er ging iets mis. Probeer het opnieuw."
            # Geen Fase 2 op een mislukte/lege turn.
            yield _sse_event(
                "done",
                _render_str(
                    request, "ai/_materialize_done.html", {"message": done_msg}
                ),
            )
            return
        if getattr(final, "stop_reason", None) == "refusal":
            refused = True
        else:
            ai_conversation.append_turn(
                db, member, "assistant", getattr(final, "content", "")
            )
            db.commit()

        if refused:
            yield _sse_event(
                "done",
                _render_str(
                    request,
                    "ai/_materialize_done.html",
                    {
                        "message": (
                            "De assistent kon hier niet op ingaan. Herformuleer je "
                            "vraag of geef andere informatie."
                        )
                    },
                ),
            )
            return

        # --- Fase 2: finalize_draft -> persist -> per-veld materialisatie ---
        def _finalize() -> tuple[bool, str | None]:
            """Run finalize + persist in de threadpool. Returns (ok, error_message)."""
            fresh = ai_conversation.load_messages(db, member)
            if not fresh:
                return False, None
            try:
                draft = ai_service.finalize_draft(fresh)
            except ai_service.EnrichmentRefused:
                db.rollback()
                return False, (
                    "Het profiel kon niet opgesteld worden. Geef wat meer "
                    "informatie en probeer opnieuw."
                )
            except ai_service.EnrichmentRateLimited:
                db.rollback()
                return False, (
                    "Je hebt het uur-limiet bereikt. Probeer het over een uur "
                    "opnieuw."
                )
            except Exception:  # noqa: BLE001
                logger.exception("finalize_draft faalde voor member %s", member_id)
                db.rollback()
                return False, (
                    "Er ging iets mis bij het opstellen. Probeer het opnieuw."
                )
            profile = profile_service.get_or_create_profile(db, member)
            profile_service.persist_draft(db, profile, draft, source_messages=fresh)
            db.commit()
            db.refresh(profile)
            return True, None

        ok, err = await run_in_threadpool(_finalize)
        if not ok:
            yield _sse_event(
                "done",
                _render_str(
                    request,
                    "ai/_materialize_done.html",
                    {"message": err or "Er ging iets mis bij het opstellen."},
                ),
            )
            return

        # Per veld een sectie laten materialiseren (choreografie).
        profile = profile_service.get_or_create_profile(db, member)
        slot_events = [
            ("f-headline", "ai/slots/_headline.html", {"uncertain": True}),
            ("f-bio", "ai/slots/_bio.html", {}),
            ("f-roles", "ai/slots/_roles.html", {}),
            ("f-projects", "ai/slots/_projects.html", {}),
            ("f-seeking", "ai/slots/_seeking.html", {"uncertain": True}),
            ("f-tags", "ai/slots/_tags.html", {}),
            ("f-tools", "ai/slots/_tools.html", {}),
        ]
        for event, tmpl, extra in slot_events:
            html = _render_str(
                request,
                tmpl,
                _form_ctx(request, profile, materializing=True, **extra),
            )
            yield _sse_event(event, html)
            # Korte choreografie-pauze (begrensd door het wall-clock-vangnet).
            import time as _t

            await run_in_threadpool(_t.sleep, 0.08)

        yield _sse_event(
            "done", _render_str(request, "ai/_materialize_done.html", {})
        )

    return StreamingResponse(_gen(), media_type="text/event-stream")


# --------------------------------------------------------------------------- #
# 4. Draft persist (één bron) + transition route                              #
# --------------------------------------------------------------------------- #
# De draft-persist (``DraftProfile`` -> datamodel) leeft als één bron in
# ``profile_service.persist_draft`` (SPEC §F.1); zowel de stream-Fase-2 als de
# overgangsroute ``maak-draft`` roepen die aan, zodat ze niet divergeren.
# ``_make_need`` blijft lokaal voor de seeking-tekstslot-edit.


def _make_need(seeking: str, position: int) -> Need:
    return Need(title=seeking[:160], description=None, position=position)


@router.post("/profiel/ai/maak-draft", response_class=HTMLResponse)
def make_draft(
    request: Request,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """OVERGANG: structured output -> persist DRAFT -> render de levende vorm.

    Rendert ``ai/_live_form.html`` in ``#profielvorm`` (i.p.v. de oude preview).
    Verdwijnt zodra de stream-variant (Fase 2 hierboven) groen test. Beide paden
    delen ``profile_service.persist_draft`` zodat ze niet divergeren.
    """
    if not settings.ai_enrich_enabled:
        return _render(
            request,
            "ai/_materialize_done.html",
            {"message": "AI-profielbouw staat momenteel uit."},
            status_code=200,
        )

    profile = profile_service.get_or_create_profile(db, member)
    messages = ai_conversation.load_messages(db, member)
    if not messages:
        return _render(
            request,
            "ai/_materialize_done.html",
            {"message": "Vertel eerst iets over jezelf hierboven."},
            status_code=400,
        )

    try:
        draft = ai_service.finalize_draft(messages)
    except ai_service.EnrichmentRefused:
        db.rollback()
        return _render(
            request,
            "ai/_materialize_done.html",
            {
                "message": (
                    "Het profiel kon niet opgesteld worden. Geef wat meer "
                    "informatie en probeer opnieuw."
                )
            },
            status_code=200,
        )
    except Exception:  # noqa: BLE001
        logger.exception("finalize_draft faalde voor member %s", member.id)
        db.rollback()
        return _render(
            request,
            "ai/_materialize_done.html",
            {"message": "Er ging iets mis bij het opstellen. Probeer het opnieuw."},
            status_code=200,
        )

    profile_service.persist_draft(db, profile, draft, source_messages=messages)
    db.commit()
    db.refresh(profile)
    return _render(
        request,
        "ai/_live_form.html",
        _form_ctx(request, profile, uncertain=True),
    )


# --------------------------------------------------------------------------- #
# 5. Cover (faalt gracieus)                                                    #
# --------------------------------------------------------------------------- #


def _cover_ctx(request: Request, profile: Profile, **extra) -> dict:
    """Context voor het cover-kaartfragment (preview + studio-ingang)."""
    return {"request": request, "profile": profile, **extra}


def _studio_ctx(request: Request, profile: Profile, **extra) -> dict:
    """Context voor het hero-studio-paneel (chips + intentie + varianten)."""
    return {
        "request": request,
        "profile": profile,
        "steer_options": cover_art_service.steer_options(),
        # Eigen tags als motief-keuzes (geen vrije invoer — gecureerd).
        "motief_options": [t.name for t in profile.tags][:8],
        **extra,
    }


@router.post("/profiel/ai/cover", response_class=HTMLResponse)
def generate_cover(
    request: Request,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
    generator: ImageGenerator = Depends(image_generator),
) -> HTMLResponse:
    """Auto-cover: één sfeerbeeld uit de profiel-essentie (faalt gracieus).

    Dit is de AUTOMATIEK (vuurt één keer na materialisatie). Een vastgezette
    cover (``cover_locked``) wordt nooit door de automatiek overschreven — het lid
    stuurt zelf via de hero-studio.
    """
    profile = profile_service.get_or_create_profile(db, member)
    if profile.cover_locked:
        return _render(request, "ai/_cover.html", _cover_ctx(request, profile))
    # Gegronde art-director: vertaal de essentie van dít profiel naar een concrete
    # visuele metafoor in de kosmische stijl (valt terug op de deterministische
    # cover_prompt bij AI-uit/fout). Zo reflecteert het sfeerbeeld de pagina écht.
    prompt = cover_art_service.build_prompt(profile)
    try:
        result = generator.generate(prompt)
        url = getattr(result, "url", None)
    except Exception:  # noqa: BLE001 — cover is optioneel; nooit de flow breken
        logger.exception("Cover-generatie faalde voor member %s", member.id)
        url = None

    if url:
        profile.cover_image_url = url
        db.commit()
        db.refresh(profile)
        cover_error = None
    else:
        cover_error = (
            "De cover kon nu niet gegenereerd worden. Je profiel werkt prima "
            "zonder; probeer het later nog eens."
        )
    return _render(
        request,
        "ai/_cover.html",
        _cover_ctx(request, profile, cover_error=cover_error),
    )


@router.get("/profiel/ai/cover/kaart", response_class=HTMLResponse)
def cover_card(
    request: Request,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """De compacte cover-kaart (studio gesloten)."""
    profile = profile_service.get_or_create_profile(db, member)
    return _render(request, "ai/_cover.html", _cover_ctx(request, profile))


@router.get("/profiel/ai/cover/studio", response_class=HTMLResponse)
def cover_studio(
    request: Request,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Open het hero-studio-paneel (chips + intentie + varianten + vastzetten)."""
    profile = profile_service.get_or_create_profile(db, member)
    return _render(request, "ai/_cover_studio.html", _studio_ctx(request, profile))


@router.post("/profiel/ai/cover/varianten", response_class=HTMLResponse)
def cover_variants(
    request: Request,
    accent: str = Form(""),
    energie: str = Form(""),
    motief: str = Form(""),
    intentie: str = Form(""),
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
    generator: ImageGenerator = Depends(image_generator),
) -> HTMLResponse:
    """Genereer een constellatie van cover-varianten met optionele lid-sturing.

    Transient: alleen de gerenderde URLs leven in het antwoord; pas een gekozen
    variant landt in de DB. Negeert ``cover_locked`` bewust (expliciete maker-actie).
    """
    profile = profile_service.get_or_create_profile(db, member)
    selected = {
        "accent": accent or None,
        "energie": energie or None,
        "motief": motief or None,
        "intentie": (intentie or "").strip()[: cover_art_service._INTENTIE_MAX] or None,
    }

    # Backend uit (geen FAL_KEY) → eerlijke "covers staan uit"-staat, geen lege kaders.
    if isinstance(generator, NoopImageGenerator):
        return _render(
            request,
            "ai/_cover_varianten.html",
            _studio_ctx(request, profile, variants=[], selected=selected, backend_off=True),
        )

    try:
        cover_service.check_cover_rate_limit(db, member.id)
    except cover_service.CoverRateLimited:
        return _render(
            request,
            "ai/_cover_varianten.html",
            _studio_ctx(
                request,
                profile,
                variants=[],
                selected=selected,
                rate_limited=True,
            ),
        )

    steer = cover_art_service.CoverSteer(
        accent=selected["accent"],
        energie=selected["energie"],
        motief=selected["motief"],
        intentie=selected["intentie"],
    )
    prompt = cover_art_service.build_prompt(profile, steer=steer)
    try:
        images = generator.generate_many(prompt, cover_service.VARIANT_COUNT)
    except Exception:  # noqa: BLE001 — varianten zijn optioneel; nooit de flow breken
        logger.exception("Cover-varianten faalden voor member %s", member.id)
        images = []
    variants = [im.url for im in images if getattr(im, "url", None)]

    # Eén audit-/rate-limit-rij per klik (niet per beeld), alleen bij een echte poging.
    cover_service.record_cover_generation(db, member.id)
    db.commit()
    db.refresh(profile)

    return _render(
        request,
        "ai/_cover_varianten.html",
        _studio_ctx(
            request,
            profile,
            variants=variants,
            selected=selected,
            cover_error=None if variants else (
                "De varianten konden nu niet gemaakt worden. Probeer het zo nog eens."
            ),
        ),
    )


@router.post("/profiel/ai/cover/kies", response_class=HTMLResponse)
def cover_pick(
    request: Request,
    url: str = Form(""),
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Kies een variant als cover. Accepteert alleen een vertrouwde fal-URL."""
    profile = profile_service.get_or_create_profile(db, member)
    if cover_service.is_trusted_cover_url(url):
        profile.cover_image_url = url.strip()
        db.commit()
        db.refresh(profile)
        pick_error = None
    else:
        pick_error = "Die afbeelding kon niet gekozen worden. Genereer er gerust een nieuwe."
    return _render(
        request, "ai/_cover_studio.html", _studio_ctx(request, profile, pick_error=pick_error)
    )


@router.post("/profiel/ai/cover/vastzetten", response_class=HTMLResponse)
def cover_lock(
    request: Request,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Toggle ``cover_locked`` — beschermt de gekozen cover tegen de automatiek."""
    profile = profile_service.get_or_create_profile(db, member)
    profile.cover_locked = not profile.cover_locked
    db.commit()
    db.refresh(profile)
    return _render(request, "ai/_cover_studio.html", _studio_ctx(request, profile))


# --------------------------------------------------------------------------- #
# 6a. Per-veld inline-edit: tekst-slots (headline/bio/seeking/tags)           #
# --------------------------------------------------------------------------- #


def _slot_response(
    request: Request, profile: Profile, naam: str, *, uncertain: bool = False
) -> HTMLResponse:
    """Render het lees-slot voor ``naam`` + een OOB completeness-update."""
    body = _render_str(
        request,
        f"ai/slots/_{naam}.html",
        _form_ctx(request, profile, uncertain=uncertain),
    )
    oob = _render_str(request, "ai/_status_oob.html", {"profile": profile})
    return HTMLResponse(body + oob)


@router.get("/profiel/ai/veld/{naam}/bewerken", response_class=HTMLResponse)
def edit_field(
    request: Request,
    naam: str,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    if naam not in _TEXT_FIELDS:
        raise HTTPException(status_code=404)
    profile = profile_service.get_or_create_profile(db, member)
    return _render(
        request, f"ai/slots/_{naam}_edit.html", _form_ctx(request, profile)
    )


@router.get("/profiel/ai/veld/{naam}", response_class=HTMLResponse)
def read_field(
    request: Request,
    naam: str,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Cancel-render: terug naar het lees-slot (marker dooft op cancel niet weg)."""
    if naam not in _TEXT_FIELDS:
        raise HTTPException(status_code=404)
    profile = profile_service.get_or_create_profile(db, member)
    uncertain = naam in ("headline", "seeking") and bool(profile.ai_enriched)
    return _render(
        request,
        f"ai/slots/_{naam}.html",
        _form_ctx(request, profile, uncertain=uncertain),
    )


def _patch_text_field(db: Session, profile: Profile, naam: str, value: str) -> None:
    """Pas één tekst-veld toe op het profiel (afkappen op max-lengte)."""
    value = (value or "").strip()
    if naam in _MAXLEN:
        value = value[: _MAXLEN[naam]]
    if naam == "headline":
        profile.headline = value or None
    elif naam == "bio":
        profile.bio = value or None
    elif naam == "seeking":
        # Vervang ALLEEN de primaire Need (needs[0]); overige needs blijven behouden
        # (``needs`` is delete-orphan — een ``clear()`` zou ze stil allemaal wissen).
        primary = profile.needs[0] if profile.needs else None
        if value:
            if primary is not None:
                primary.title = value[:160]
                primary.description = None
            else:
                profile.needs.append(_make_need(value, 0))
        elif primary is not None:
            profile.needs.remove(primary)
    elif naam == "tags":
        profile_service.set_tags(db, profile, value)
    elif naam == "tools":
        tool_service.set_tools(db, profile, value)
    profile_service.recompute_completeness(profile)
    db.flush()


@router.patch("/profiel/ai/veld/{naam}", response_class=HTMLResponse)
def patch_field(
    request: Request,
    naam: str,
    value: str = Form(""),
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    if naam not in _TEXT_FIELDS:
        raise HTTPException(status_code=404)
    profile = profile_service.get_or_create_profile(db, member)
    _patch_text_field(db, profile, naam, value)
    db.commit()
    db.refresh(profile)
    # Warme trigger (doc 03 §1): koppelt het lid een tool zonder review, start de
    # AI-review async (geen UX-vertraging; no-op zonder Cloudflare → vangnet = nachtjob).
    if naam == "tools":
        tool_review_service.trigger_for_profile_tools(profile)
    # Na een bewuste edit verdwijnt de "afgeleid"-marker voor dit veld.
    return _slot_response(request, profile, naam, uncertain=False)


@router.post("/profiel/ai/veld/{naam}/bevestig", response_class=HTMLResponse)
def confirm_field(
    request: Request,
    naam: str,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """"Klopt" — render het lees-slot zonder de onzekerheids-marker (geen wijziging)."""
    if naam not in _TEXT_FIELDS:
        raise HTTPException(status_code=404)
    profile = profile_service.get_or_create_profile(db, member)
    return _slot_response(request, profile, naam, uncertain=False)


# --------------------------------------------------------------------------- #
# 6b. Per-veld inline-edit: offerings (projecten)                             #
# --------------------------------------------------------------------------- #


def _owned_offering(db: Session, profile: Profile, offering_id: int) -> Offering:
    offering = db.get(Offering, offering_id)
    if offering is None or offering.profile_id != profile.id:
        raise HTTPException(status_code=404)
    return offering


def _offering_card(request: Request, profile: Profile, item: Offering) -> HTMLResponse:
    body = _render_str(
        request, "ai/slots/_offering_card.html", {"request": request, "item": item}
    )
    oob = _render_str(request, "ai/_status_oob.html", {"profile": profile})
    return HTMLResponse(body + oob)


@router.post("/profiel/ai/offering", response_class=HTMLResponse)
def add_offering_route(
    request: Request,
    title: str = Form(""),
    description: str = Form(""),
    url: str = Form(""),
    image_url: str = Form(""),
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Voeg een (leeg) project toe; her-render de hele projecten-sectie."""
    profile = profile_service.get_or_create_profile(db, member)
    offering = profile_service.add_offering(
        db, profile, title=title.strip() or "Nieuw project", description=description.strip() or None
    )
    offering.url = safe_url(url) or None
    offering.image_url = safe_url(image_url) or None
    offering_slug.ensure_slug(db, offering)
    profile_service.recompute_completeness(profile)
    db.commit()
    # Direct (achtergrond) verrijken zodra er een link is — geen UX-vertraging.
    if offering.url:
        project_enrich_service.trigger_async(offering.id)
    db.refresh(profile)
    body = _render_str(
        request, "ai/slots/_projects.html", _form_ctx(request, profile)
    )
    oob = _render_str(request, "ai/_status_oob.html", {"profile": profile})
    return HTMLResponse(body + oob)


@router.get("/profiel/ai/offering/{offering_id}/bewerken", response_class=HTMLResponse)
def edit_offering(
    request: Request,
    offering_id: int,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    profile = profile_service.get_or_create_profile(db, member)
    item = _owned_offering(db, profile, offering_id)
    return _render(
        request, "ai/slots/_offering_edit.html", {"request": request, "item": item}
    )


@router.get("/profiel/ai/offering/{offering_id}", response_class=HTMLResponse)
def read_offering(
    request: Request,
    offering_id: int,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    profile = profile_service.get_or_create_profile(db, member)
    item = _owned_offering(db, profile, offering_id)
    return _render(
        request, "ai/slots/_offering_card.html", {"request": request, "item": item}
    )


@router.patch("/profiel/ai/offering/{offering_id}", response_class=HTMLResponse)
def patch_offering(
    request: Request,
    offering_id: int,
    title: str = Form(""),
    description: str = Form(""),
    url: str = Form(""),
    image_url: str = Form(""),
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    profile = profile_service.get_or_create_profile(db, member)
    item = profile_service.update_offering(
        db,
        profile,
        offering_id,
        title=title,
        description=description,
        url=url,
        image_url=image_url,
    )
    if item is None:
        raise HTTPException(status_code=404)
    db.commit()
    # Een gewijzigde link nullt de verrijking (zie update_offering) → her-genereer
    # 'm direct in de achtergrond; een ontbrekende verrijking vult zo ook aan. Alleen
    # voor 'project'-items: een video/audio-embed heeft een speler, geen screenshot.
    if (
        item.kind == OfferingKind.project
        and item.url
        and (item.screenshot_url is None or item.summary is None)
    ):
        project_enrich_service.trigger_async(item.id)
    db.refresh(profile)
    db.refresh(item)
    return _offering_card(request, profile, item)


@router.delete("/profiel/ai/offering/{offering_id}", response_class=HTMLResponse)
def delete_offering(
    request: Request,
    offering_id: int,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    profile = profile_service.get_or_create_profile(db, member)
    if not profile_service.remove_offering(db, profile, offering_id):
        raise HTTPException(status_code=404)
    db.commit()
    db.refresh(profile)
    oob = _render_str(request, "ai/_status_oob.html", {"profile": profile})
    return HTMLResponse(oob)


# --------------------------------------------------------------------------- #
# 6c. Per-veld inline-edit: rollen (ProfileLink kind=affiliation)             #
# --------------------------------------------------------------------------- #


def _owned_role(db: Session, profile: Profile, role_id: int) -> ProfileLink:
    link = db.get(ProfileLink, role_id)
    if (
        link is None
        or link.profile_id != profile.id
        or link.kind is not ProfileLinkKind.affiliation
    ):
        raise HTTPException(status_code=404)
    return link


@router.post("/profiel/ai/rol", response_class=HTMLResponse)
def add_role(
    request: Request,
    label: str = Form(""),
    url: str = Form(""),
    description: str = Form(""),
    image_url: str = Form(""),
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Voeg een (lege) rol toe; her-render de hele rollen-sectie."""
    profile = profile_service.get_or_create_profile(db, member)
    profile_link_service.add(
        db,
        profile,
        label=label.strip() or "Nieuwe rol",
        url=url,
        description=description,
        image_url=image_url,
    )
    db.commit()
    db.refresh(profile)
    body = _render_str(request, "ai/slots/_roles.html", _form_ctx(request, profile))
    oob = _render_str(request, "ai/_status_oob.html", {"profile": profile})
    return HTMLResponse(body + oob)


@router.get("/profiel/ai/rol/{role_id}/bewerken", response_class=HTMLResponse)
def edit_role(
    request: Request,
    role_id: int,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    profile = profile_service.get_or_create_profile(db, member)
    link = _owned_role(db, profile, role_id)
    return _render(
        request, "ai/slots/_role_edit.html", {"request": request, "link": link}
    )


@router.get("/profiel/ai/rol/{role_id}", response_class=HTMLResponse)
def read_role(
    request: Request,
    role_id: int,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    profile = profile_service.get_or_create_profile(db, member)
    link = _owned_role(db, profile, role_id)
    return _render(
        request, "ai/slots/_role_card.html", {"request": request, "link": link}
    )


@router.patch("/profiel/ai/rol/{role_id}", response_class=HTMLResponse)
def patch_role(
    request: Request,
    role_id: int,
    label: str = Form(""),
    url: str = Form(""),
    description: str = Form(""),
    image_url: str = Form(""),
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    profile = profile_service.get_or_create_profile(db, member)
    link = _owned_role(db, profile, role_id)  # 404 op vreemd id / niet-affiliation
    profile_link_service.update(
        db,
        profile,
        role_id,
        label=label,
        url=url,
        description=description,
        image_url=image_url,
    )
    db.commit()
    db.refresh(profile)
    db.refresh(link)
    body = _render_str(
        request, "ai/slots/_role_card.html", {"request": request, "link": link}
    )
    oob = _render_str(request, "ai/_status_oob.html", {"profile": profile})
    return HTMLResponse(body + oob)


@router.delete("/profiel/ai/rol/{role_id}", response_class=HTMLResponse)
def delete_role(
    request: Request,
    role_id: int,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    profile = profile_service.get_or_create_profile(db, member)
    _owned_role(db, profile, role_id)  # 404 op vreemd id / niet-affiliation
    profile_link_service.remove(db, profile, role_id)
    db.commit()
    db.refresh(profile)
    oob = _render_str(request, "ai/_status_oob.html", {"profile": profile})
    return HTMLResponse(oob)


# --------------------------------------------------------------------------- #
# 7. Publish                                                                   #
# --------------------------------------------------------------------------- #


@router.post("/profiel/ai/publiceren")
def publish(
    request: Request,
    visibility: str = Form("members"),
    consent: str = Form(""),
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
):
    """Bevestig + publiceer. Delegeert naar de zichtbaarheidsflow (consent voor public).

    Zet zelf NOOIT ``visibility``; ``change_visibility`` dwingt consent af voor
    ``public`` (AVG). Bij ``ConsentRequired`` swapt het publiceer-dok een melding.
    Na succes: wis de conversatie + 303 naar de publieke profielpagina.
    """
    profile = profile_service.get_or_create_profile(db, member)
    AcceptForm(consent=bool(consent))

    from app.models import Visibility

    target = Visibility.public if visibility == "public" else Visibility.members
    try:
        visibility_service.change_visibility(
            db, profile, target, actor=member, consent=bool(consent)
        )
    except visibility_service.ConsentRequired:
        db.rollback()
        return _render(
            request,
            "ai/_publish_panel.html",
            {
                "profile": profile,
                "error": "Vink de toestemming aan om je profiel openbaar te maken.",
            },
            status_code=400,
        )

    ai_conversation.clear_turns(db, member)
    db.commit()
    # htmx onderschept de POST: geef een client-side redirect (HX-Redirect) zodat de
    # browser écht navigeert i.p.v. de volledige profielpagina in het kleine
    # publiceer-paneel te swappen. Native (no-JS) form-post valt terug op een 303.
    target_url = f"/leden/{profile.slug}"
    if request.headers.get("HX-Request"):
        return Response(status_code=204, headers={"HX-Redirect": target_url})
    return RedirectResponse(url=target_url, status_code=status.HTTP_303_SEE_OTHER)


# --------------------------------------------------------------------------- #
# 8. Restart (AVG-reset)                                                       #
# --------------------------------------------------------------------------- #


@router.post("/profiel/ai/opnieuw")
def restart(
    request: Request,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
):
    """Wis de conversatie + AI-flags + cover en begin een nieuwe bouw-sessie."""
    profile = profile_service.get_or_create_profile(db, member)
    ai_conversation.clear_turns(db, member)
    profile.ai_enriched = False
    profile.ai_source_text = None
    profile.cover_image_url = None
    profile.cover_locked = False
    db.commit()
    return RedirectResponse(
        url="/profiel/ai/bouwen", status_code=status.HTTP_303_SEE_OTHER
    )
