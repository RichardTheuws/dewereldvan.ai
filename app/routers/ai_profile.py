"""AI-native profielbouw routes (F1-F3).

Flow (zie bouwcontract §4):

1. ``GET  /profiel/ai/bouwen``    — kosmische chat-bouwpagina (bestaande turns).
2. ``POST /profiel/ai/bericht``   — lid stuurt bericht; persist user-turn, start
   de (synchrone) Anthropic-stream in een thread, render een SSE-container.
3. ``GET  /profiel/ai/stream``    — SSE: tekst-deltas + terminerend ``done``-event
   met de gerenderde assistant-bubbel.
4. ``POST /profiel/ai/maak-draft``— stap-2 structured output -> persist DRAFT op
   het profiel (headline/bio/offerings/profile_links/needs/tags), ``ai_enriched``,
   ``ai_source_text``. Zet NOOIT ``visibility``.
5. ``POST /profiel/ai/cover``     — F2: cover via ImageGenerator (faalt gracieus).
6. ``POST /profiel/ai/draft/bewerken`` — lid bewerkt de draft-velden (htmx).
7. ``POST /profiel/ai/publiceren``— delegeert naar de bestaande zichtbaarheidsflow
   (consent vereist voor public), wist de conversatie, redirect naar het profiel.
8. ``POST /profiel/ai/opnieuw``   — nieuwe sessie (wis turns + ai-flags).

Alle routes draaien onder ``require_member`` (ingelogd + approved); CSRF loopt via
``hx-headers`` in ``base.html``. Auto-publiceren gebeurt NOOIT.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from markupsafe import escape
from sqlalchemy.orm import Session

from app.ai import ImageGenerator, cover_prompt
from app.config import settings
from app.db import get_db
from app.deps import image_generator, require_member
from app.models import Member, Offering, Profile, ProfileLink, ProfileLinkKind
from app.schemas.ai_profile import AcceptForm, ChatMessageForm
from app.services import ai_conversation, offering_slug, profile_service
from app.services import ai_profile as ai_service
from app.services import visibility as visibility_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ai-profile"])


def _render(request: Request, name: str, ctx: dict | None = None, **kw) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, name, ctx or {}, **kw)


def _render_str(request: Request, name: str, ctx: dict | None = None) -> str:
    """Render a template to a plain string (for embedding in an SSE event)."""
    tmpl = request.app.state.templates.get_template(name)
    context = {"request": request, **(ctx or {})}
    # Mirror the csrf context-processor so partials that need the token work.
    from app.csrf import get_csrf_token

    context.setdefault("csrf_token", get_csrf_token(request))
    return tmpl.render(context)


# --------------------------------------------------------------------------- #
# 1. Build page                                                               #
# --------------------------------------------------------------------------- #


@router.get("/profiel/ai/bouwen", response_class=HTMLResponse)
def build_page(
    request: Request,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """De kosmische chat-bouwpagina; herlaadt bestaande turns."""
    profile = profile_service.get_or_create_profile(db, member)
    db.commit()
    messages = ai_conversation.load_messages(db, member)
    turns = _renderable_turns(messages)
    has_draft = bool(profile.ai_enriched)
    from app.services import photo_service

    return _render(
        request,
        "ai/build.html",
        {
            "profile": profile,
            "turns": turns,
            "has_history": bool(turns),
            "has_draft": has_draft,
            "ai_enabled": settings.ai_enrich_enabled,
            "photo": photo_service.photo_or_initials(profile),
        },
    )


def _renderable_turns(messages: list[dict]) -> list[dict]:
    """Reduceer Anthropic-messages tot wat we in de chat tonen (tekst-only)."""
    out: list[dict] = []
    for m in messages:
        text = _extract_text(m.get("content"))
        if not text:
            continue
        out.append({"role": m.get("role", "assistant"), "text": text})
    return out


def _extract_text(content) -> str:
    """Trek de zichtbare tekst uit een content-blok (string of blok-lijst)."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts).strip()
    return ""


# --------------------------------------------------------------------------- #
# 2. Member message -> start stream                                           #
# --------------------------------------------------------------------------- #


@router.post("/profiel/ai/bericht", response_class=HTMLResponse)
def post_message(
    request: Request,
    message: str = Form(""),
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Persist het lid-bericht en render de SSE-container voor het AI-antwoord.

    Het zware werk (de agentische Anthropic-turn) gebeurt in de GET ``/stream``-
    handler; deze POST legt alleen de user-turn vast en geeft een fragment terug
    dat (a) de lid-bubbel toont en (b) een ``EventSource`` opent via de htmx
    ``sse``-extensie.
    """
    if not settings.ai_enrich_enabled:
        return _render(
            request,
            "ai/_chat_message.html",
            {"role": "system", "text": "AI-profielbouw staat momenteel uit."},
            status_code=200,
        )

    try:
        data = ChatMessageForm(message=message)
    except ValueError:
        return _render(
            request,
            "ai/_chat_message.html",
            {"role": "system", "text": "Typ eerst een bericht."},
            status_code=400,
        )

    # Rate-limit per lid (telt user-turns in een uur-venster).
    try:
        ai_service.check_enrich_rate_limit(db, member)
    except ai_service.EnrichmentRateLimited:
        return _render(
            request,
            "ai/_chat_message.html",
            {
                "role": "system",
                "text": (
                    "Je hebt het uur-limiet bereikt. Probeer het over een uur "
                    "opnieuw."
                ),
            },
            status_code=429,
        )

    ai_conversation.append_turn(db, member, "user", data.message)
    db.commit()

    return _render(
        request,
        "ai/_message_sent.html",
        {"user_text": data.message},
    )


# --------------------------------------------------------------------------- #
# 3. SSE stream — runs the agentic turn, streams deltas, persists assistant   #
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
    """Server-Sent Events: tekst-deltas, dan een ``done``-event met de bubbel.

    De sync Anthropic-SDK draait in een threadpool (``stream_turn`` blokkeert),
    waarbij elke delta in een queue wordt geduwd; de async generator pompt die
    queue leeg naar de browser. Na afloop wordt de assistant-turn gepersisteerd
    (volledige content incl. tool/thinking-blokken) en de finale bubbel als
    ``done``-event gerenderd. ``refusal`` wordt netjes afgevangen (geen
    ``content[0]`` zonder ``stop_reason``-check).
    """
    messages = ai_conversation.load_messages(db, member)
    # Drie aparte _Channel-instanties — het bestaande sentinel/timeout-protocol
    # blijft per kanaal ongewijzigd. ``text_ch`` voert de bestaande tekst-deltas
    # (byte-identiek), ``think_ch`` de live-redenering (reasoning) en ``tool_ch``
    # de per-link fetch-status (STRETCH). De thinking/tool-kanalen zijn additief:
    # oude clients negeren de extra event-soorten, en stream_turn valt zonder
    # callbacks terug op exact het oude gedrag.
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
        except Exception:  # noqa: BLE001 — surface as a system message, no traceback
            logger.exception("AI stream_turn faalde voor member %s", member_id)
            return None
        finally:
            # Sluit ALLE kanalen zodat geen enkele drain-lus blijft hangen.
            text_ch.close()
            think_ch.close()
            tool_ch.close()

    async def _gen():
        if not settings.ai_enrich_enabled:
            yield _sse_event("done", "")
            return

        # Kick off the blocking producer CONCURRENTLY (as a task, so it actually
        # runs while we drain deltas) and stream deltas as they arrive.
        import asyncio
        import time

        from app.services.ai_conversation import CHANNEL_TIMEOUT_SEC

        task = asyncio.ensure_future(run_in_threadpool(_run))
        deadline = time.monotonic() + CHANNEL_TIMEOUT_SEC

        # Eén drain-lus over de drie kanalen via korte, niet-blokkerende polls
        # (blokkerende channel-read off de event-loop met korte timeout, zodat we
        # tussen de kanalen kunnen rouleren). De reasoning- en fetch-events worden
        # additief uitgestuurd; ``delta`` blijft exact zoals voorheen (geescaped).
        # De producer-task signaleert einde door alle kanalen te sluiten -> alle
        # drains lopen leeg -> we breken eruit (of het wall-clock-vangnet grijpt).
        text_done = think_done = tool_done = False
        streamed_parts: list[str] = []  # accumuleer tekst-deltas voor de done-bubbel
        while not (text_done and think_done and tool_done):
            # Absolute wall-clock vangnet (zoals de oude _Channel.get-timeout):
            # blokkeert ``stream_turn`` oncontroleerbaar (SDK/netwerk-stall zonder
            # dat de finally->close() draait), dan flipt ``task.done()`` nooit en
            # zou deze lus eindeloos pollen. Na CHANNEL_TIMEOUT_SEC breken we eruit
            # zodat de SSE-verbinding + threadpool-worker niet permanent vastzitten.
            if time.monotonic() > deadline:
                logger.warning(
                    "AI stream-drain timeout (%.0fs) voor member %s; stop.",
                    CHANNEL_TIMEOUT_SEC,
                    member_id,
                )
                break
            # Thinking eerst surfacen (de wacht-UX-redenering loopt vóór de tekst).
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
                    # Escape each delta so the live-stream bubble (htmx sse-swap
                    # inserts the payload as HTML, not text) renders model output
                    # as plain text. This closes the prompt-injection -> DOM-XSS
                    # path and makes the live bubble match the final autoescaped
                    # bubble (no markup flash). BYTE-IDENTIEK aan het oude gedrag.
                    streamed_parts.append(item)
                    yield _sse_event("delta", str(escape(item)))
                    continue

        # Normaal is de task hier al klaar (sentinel-terminatie). Brak de lus af op
        # het wall-clock-vangnet terwijl de producer nog hangt, dan zou ``await
        # task`` opnieuw blokkeren — vang dat af met een korte grace en val terug
        # op de "er ging iets mis"-bubbel i.p.v. de SSE-respons te laten hangen.
        if task.done():
            final = await task
        else:
            try:
                final = await asyncio.wait_for(asyncio.shield(task), timeout=1.0)
            except TimeoutError:
                final = None

        # Decide the final bubble + persist the assistant turn.
        if final is None:
            html = _render_str(
                request,
                "ai/_chat_message.html",
                {"role": "system", "text": "Er ging iets mis. Probeer het opnieuw."},
            )
        elif getattr(final, "stop_reason", None) == "refusal":
            html = _render_str(
                request,
                "ai/_chat_message.html",
                {
                    "role": "refusal",
                    "text": (
                        "De assistent kon hier niet op ingaan. Herformuleer je "
                        "vraag of geef andere informatie."
                    ),
                },
            )
        else:
            assistant_text = _extract_text(getattr(final, "content", None))
            # De volledige reply kan over meerdere pause_turn-iteraties zijn
            # gestreamd; ``final`` (laatste iteratie) mist 'm dan, waardoor de
            # done-bubbel een lege "…" toonde en de vervolgvraag "verdween". Val
            # terug op de tekst die het lid ECHT zag stromen.
            streamed_text = "".join(streamed_parts).strip()
            ai_conversation.append_turn(
                db, member, "assistant", getattr(final, "content", assistant_text)
            )
            db.commit()
            html = _render_str(
                request,
                "ai/_chat_message.html",
                {"role": "assistant", "text": assistant_text or streamed_text or "…"},
            )
        yield _sse_event("done", html)

    return StreamingResponse(_gen(), media_type="text/event-stream")


# --------------------------------------------------------------------------- #
# 4. Make draft (structured output -> persist)                                #
# --------------------------------------------------------------------------- #


@router.post("/profiel/ai/maak-draft", response_class=HTMLResponse)
def make_draft(
    request: Request,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Stap 2: structured output -> persisteer als DRAFT (visibility ONGEWIJZIGD)."""
    if not settings.ai_enrich_enabled:
        return _render(
            request,
            "ai/_draft_preview.html",
            {"error": "AI-profielbouw staat momenteel uit.", "profile": None},
            status_code=200,
        )

    profile = profile_service.get_or_create_profile(db, member)
    messages = ai_conversation.load_messages(db, member)
    if not messages:
        return _render(
            request,
            "ai/_draft_preview.html",
            {
                "error": "Vertel eerst iets over jezelf in de chat hierboven.",
                "profile": profile,
            },
            status_code=400,
        )

    try:
        draft = ai_service.finalize_draft(messages)
    except ai_service.EnrichmentRefused:
        db.rollback()
        return _render(
            request,
            "ai/_draft_preview.html",
            {
                "error": (
                    "Het profiel kon niet opgesteld worden. Geef wat meer "
                    "informatie en probeer opnieuw."
                ),
                "profile": profile,
            },
            status_code=200,
        )
    except Exception:  # noqa: BLE001
        logger.exception("finalize_draft faalde voor member %s", member.id)
        db.rollback()
        return _render(
            request,
            "ai/_draft_preview.html",
            {
                "error": "Er ging iets mis bij het opstellen. Probeer het opnieuw.",
                "profile": profile,
            },
            status_code=200,
        )

    _persist_draft(db, profile, draft, source_messages=messages)
    db.commit()
    db.refresh(profile)
    return _render(
        request,
        "ai/_draft_preview.html",
        {"profile": profile, "saved": True},
    )


def _persist_draft(
    db: Session,
    profile: Profile,
    draft: ai_service.DraftProfile,
    *,
    source_messages: list[dict],
) -> None:
    """Map ``DraftProfile`` onto the data model as a DRAFT.

    - ``headline``/``bio`` -> profile columns.
    - ``seeking``         -> a single Need (replaces AI-seeded needs is overkill;
                             we append one if non-empty and not already present).
    - ``projects``        -> Offering (url/image_url/description).
    - ``roles``           -> ProfileLink kind=affiliation.
    - ``tags``            -> profile tags (via profile_service).

    Offerings worden op positie *gereconcilieerd* (niet clear+recreate): een
    bestaand project op index *i* blijft dezelfde rij — bij een gewijzigde titel
    loopt het via ``offering_slug.rename_to`` zodat de oude ``/projecten/{slug}``
    een 301 naar de nieuwe houdt (linkwaarde-behoud), bij een ongewijzigde titel
    blijft de slug exact gelijk. Zo wist een regenerate nooit de slug-historie en
    breekt geen geïndexeerde project-URL. ``visibility`` blijft ongemoeid.
    """
    profile.headline = draft.headline
    if draft.bio:
        profile.bio = draft.bio
    profile.ai_enriched = True
    # Store the raw member text (the user turns) for audit / regenerate.
    user_texts = [
        _extract_text(m.get("content"))
        for m in source_messages
        if m.get("role") == "user"
    ]
    profile.ai_source_text = "\n\n".join(t for t in user_texts if t) or None

    # Projects -> offerings, gereconcilieerd op positie (behoud rij + slug-historie).
    _reconcile_offerings(db, profile, draft.projects)

    # Roles -> profile_links (affiliation).
    profile.profile_links.clear()
    db.flush()
    for i, role in enumerate(draft.roles):
        profile.profile_links.append(
            ProfileLink(
                label=role.label,
                url=role.url,
                description=role.description,
                image_url=role.image_url,
                kind=ProfileLinkKind.affiliation,
                position=i,
            )
        )

    # Seeking -> a Need (only when non-empty; append, don't duplicate verbatim).
    if draft.seeking:
        existing = {(n.title or "").strip() for n in profile.needs}
        if draft.seeking.strip() not in existing:
            profile.needs.append(_make_need(draft.seeking, len(profile.needs)))

    # Tags.
    if draft.tags:
        profile_service.set_tags(db, profile, ", ".join(draft.tags))

    profile_service.recompute_completeness(profile)
    db.flush()


def _reconcile_offerings(
    db: Session, profile: Profile, projects: list
) -> None:
    """Match bestaande offerings op positie met de nieuwe draft-projecten.

    Per index *i*: hergebruik de bestaande rij (behoud id + slug-historie). Is de
    titel gewijzigd → ``offering_slug.rename_to`` (schrijft de oude slug in de
    history-tabel + houdt het 301-pad live). Is de titel gelijk → de slug blijft
    onveranderd. Extra projecten worden nieuw aangemaakt (krijgen een verse slug);
    weggevallen projecten worden verwijderd (delete-orphan). De 301-machinerie
    wordt zo daadwerkelijk langs het publiceer-/regenerate-pad gebruikt.
    """
    existing = sorted(profile.offerings, key=lambda o: (o.position, o.id or 0))

    for i, project in enumerate(projects):
        if i < len(existing):
            offering = existing[i]
            if (offering.title or "") != project.name:
                # Titel wijzigt → rename_to legt de oude slug vast voor de 301.
                offering_slug.rename_to(db, offering, project.name)
            offering.description = project.description
            offering.url = project.url
            offering.image_url = project.image_url
            offering.position = i
        else:
            offering = Offering(
                title=project.name,
                description=project.description,
                url=project.url,
                image_url=project.image_url,
                position=i,
            )
            profile.offerings.append(offering)

    # Weggevallen projecten (de staart) verwijderen.
    for offering in existing[len(projects):]:
        profile.offerings.remove(offering)

    db.flush()
    # Garandeer een slug op elke (ook nieuwe) offering.
    for offering in profile.offerings:
        offering_slug.ensure_slug(db, offering)


def _make_need(seeking: str, position: int):
    from app.models import Need

    return Need(title=seeking[:160], description=None, position=position)


# --------------------------------------------------------------------------- #
# 5. Cover (F2)                                                               #
# --------------------------------------------------------------------------- #


@router.post("/profiel/ai/cover", response_class=HTMLResponse)
def generate_cover(
    request: Request,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
    generator: ImageGenerator = Depends(image_generator),
) -> HTMLResponse:
    """Genereer een cover op basis van de profiel-essentie (faalt gracieus)."""
    profile = profile_service.get_or_create_profile(db, member)
    prompt = cover_prompt(
        profile.bio or profile.headline, [t.name for t in profile.tags]
    )
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
        {"profile": profile, "cover_error": cover_error},
    )


# --------------------------------------------------------------------------- #
# 6. Edit draft fields                                                        #
# --------------------------------------------------------------------------- #


@router.post("/profiel/ai/draft/bewerken", response_class=HTMLResponse)
def edit_draft(
    request: Request,
    headline: str = Form(""),
    bio: str = Form(""),
    seeking: str = Form(""),
    tags: str = Form(""),
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Lid bewerkt de kern-draftvelden in de preview (htmx swap)."""
    profile = profile_service.get_or_create_profile(db, member)
    profile.headline = headline.strip() or None
    profile.bio = bio.strip() or None
    if tags.strip():
        profile_service.set_tags(db, profile, tags)
    # Seeking maps to the first/primary need; replace it.
    seeking = seeking.strip()
    profile.needs.clear()
    db.flush()
    if seeking:
        profile.needs.append(_make_need(seeking, 0))
    profile_service.recompute_completeness(profile)
    db.commit()
    db.refresh(profile)
    return _render(
        request,
        "ai/_draft_preview.html",
        {"profile": profile, "saved": True},
    )


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
    """Bevestig de draft. Delegeert naar de bestaande zichtbaarheidsflow.

    Zet zelf NOOIT ``visibility``; ``change_visibility`` dwingt consent af voor
    ``public`` (AVG). Bij ``ConsentRequired`` toont de preview een nette melding.
    Na succes: wis de conversatie en stuur door naar de publieke profielpagina.
    """
    profile = profile_service.get_or_create_profile(db, member)
    AcceptForm(consent=bool(consent))  # shape-validate the consent flag

    from app.models import Visibility

    target = (
        Visibility.public if visibility == "public" else Visibility.members
    )
    try:
        visibility_service.change_visibility(
            db, profile, target, actor=member, consent=bool(consent)
        )
    except visibility_service.ConsentRequired:
        db.rollback()
        return _render(
            request,
            "ai/_draft_preview.html",
            {
                "profile": profile,
                "error": (
                    "Vink de toestemming aan om je profiel openbaar te maken."
                ),
            },
            status_code=400,
        )

    ai_conversation.clear_turns(db, member)
    db.commit()
    return RedirectResponse(
        url=f"/leden/{profile.slug}", status_code=status.HTTP_303_SEE_OTHER
    )


# --------------------------------------------------------------------------- #
# 8. Restart                                                                   #
# --------------------------------------------------------------------------- #


@router.post("/profiel/ai/opnieuw")
def restart(
    request: Request,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
):
    """Wis de conversatie + AI-flags en begin een nieuwe bouw-sessie.

    De knop belooft dat 'het gesprek en de concept-velden van deze AI-sessie
    worden gewist', dus wissen we ook de opgeslagen ruwe lid-invoer
    (``ai_source_text``) en de in deze sessie gegenereerde cover — anders blijft
    persoonlijke tekst stilletjes in de DB staan (AVG-retentie).
    """
    profile = profile_service.get_or_create_profile(db, member)
    ai_conversation.clear_turns(db, member)
    profile.ai_enriched = False
    profile.ai_source_text = None
    profile.cover_image_url = None
    db.commit()
    return RedirectResponse(
        url="/profiel/ai/bouwen", status_code=status.HTTP_303_SEE_OTHER
    )
