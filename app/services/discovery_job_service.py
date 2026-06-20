"""Discovery als achtergrond-job — ontkoppel de (minutenlange) ontdekking.

De footprint-ontdekking duurt minuten (echte web-search + weging). Te lang om
iemand op één verbinding vast te houden, en de oude inline-SSE-stream sneuvelde
op de 2-min-drain-cap (``CHANNEL_TIMEOUT_SEC``) vóór het einde. Daarom draait de
engine hier in een **achtergrond-thread** (eigen sessie, zoals
``project_enrich_service.trigger_async``) die de bevindingen wegschrijft naar
``DiscoveryRun``. De live-view *tailt* die rij over SSE; wie wegklikt verliest
niets — bij terugkeer staat het resultaat er nog, en een **in-app seintje** (de
``chip_discovery``-chip in de canvas) haalt het lid terug.

Notificatie-kanaal: bewust **geen e-mail** (e-mail alleen nog voor de magic-link).
De notificatie is nu de pull-based in-app chip; een lid-gekozen push-kanaal
(Telegram, en uitbreidbaar) komt via een aparte notificatie-voorkeurslaag.

Self-only (de caller dwingt ``require_member`` + het eigen profiel af). Best-effort:
een fout markeert de run ``failed`` en breekt nooit de app/thread. Gegated op
``settings.ai_enrich_enabled`` (via ``footprint_service.discover``).
"""

from __future__ import annotations

import json
import logging
import threading

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db import SessionLocal
from app.models import DiscoveryRun, Member
from app.security import naive_utc, utcnow
from app.services import footprint_service, profile_service

logger = logging.getLogger(__name__)

__all__ = [
    "STATUS_RUNNING",
    "STATUS_DONE",
    "STATUS_EMPTY",
    "STATUS_FAILED",
    "start",
    "run_job",
    "get_run",
    "snapshot",
    "mark_seen",
    "unseen_result_count",
    "findings_of",
]

STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_EMPTY = "empty"
STATUS_FAILED = "failed"

# Een job die langer loopt dan dit (de engine hangt) wordt door de tail als
# verlopen behandeld; de thread-guard (engine MAX_PAUSE_TURNS) bewaakt de bovenkant.
_inflight: set[int] = set()
_inflight_lock = threading.Lock()


# --------------------------------------------------------------------------- #
# Lezen (live-tail + terugkeer-view + chip)                                   #
# --------------------------------------------------------------------------- #


def get_run(db: Session, member_id: int) -> DiscoveryRun | None:
    return db.scalar(select(DiscoveryRun).where(DiscoveryRun.member_id == member_id))


def findings_of(run: DiscoveryRun | None) -> list[dict]:
    """De gepersisteerde finding-dicts van een run (leeg bij None/onleesbaar)."""
    if run is None or not run.findings_json:
        return []
    try:
        data = json.loads(run.findings_json)
    except (ValueError, TypeError):
        return []
    return [f for f in data if isinstance(f, dict)]


def snapshot(db: Session, member_id: int) -> tuple[str | None, list[dict]]:
    """(status, findings) voor de live-tail — None-status = (nog) geen run."""
    run = get_run(db, member_id)
    if run is None:
        return None, []
    return run.status, findings_of(run)


def is_running(run: DiscoveryRun | None) -> bool:
    return run is not None and run.status == STATUS_RUNNING


def mark_seen(db: Session, run: DiscoveryRun) -> None:
    """Markeer een afgeronde run als gezien (stilt de "klaar"-chip)."""
    if run.seen_at is None:
        run.seen_at = naive_utc(utcnow())
        db.flush()


def unseen_result_count(db: Session, member_id: int) -> int:
    """Aantal findings van een AFGERONDE, nog niet geziene run (0 = geen chip)."""
    run = get_run(db, member_id)
    if run is None or run.status not in (STATUS_DONE,) or run.seen_at is not None:
        return 0
    return len(findings_of(run))


# --------------------------------------------------------------------------- #
# Starten (request-thread) + draaien (achtergrond-thread)                     #
# --------------------------------------------------------------------------- #


def start(
    db: Session, member: Member, *, focus: str = "broad", append: bool = False
) -> DiscoveryRun:
    """(Her)start de ontdekking voor ``member`` en spawn de achtergrond-thread.

    ``focus`` = "broad" (eigen werk) of "media" (verdieping naar vermeldingen óver
    de persoon). ``append`` houdt bestaande findings (verdieping vult aan i.p.v.
    overschrijven); zonder append wordt de run vers gereset. Status → ``running``,
    ``seen_at`` reset zodat het klaar-seintje opnieuw afgaat. De caller commit NIET;
    wij committen hier zodat de thread de verse rij ziet. Dubbel-werk-guard via
    ``_inflight``.
    """
    run = get_run(db, member.id)
    if run is None:
        run = DiscoveryRun(member_id=member.id, status=STATUS_RUNNING)
        db.add(run)
    else:
        run.status = STATUS_RUNNING
        if not append:
            run.findings_json = None
        run.error = None
        run.finished_at = None
        run.seen_at = None
    db.flush()
    db.commit()

    member_id = member.id
    with _inflight_lock:
        if member_id in _inflight:
            return run  # job loopt al — geen tweede thread
        _inflight.add(member_id)

    threading.Thread(
        target=run_job,
        args=(member_id,),
        kwargs={"focus": focus, "append": append},
        name=f"discover-{member_id}-{focus}",
        daemon=True,
    ).start()
    return run


def _merge_dedup(existing: list[dict], fresh: list[dict]) -> list[dict]:
    """Voeg ``fresh`` toe aan ``existing``, gededupeerd op URL (bestaande blijven)."""
    seen = {f.get("url") for f in existing if isinstance(f, dict) and f.get("url")}
    merged = list(existing)
    for f in fresh:
        url = f.get("url") if isinstance(f, dict) else None
        if url and url in seen:
            continue
        if url:
            seen.add(url)
        merged.append(f)
    return merged


def run_job(
    member_id: int,
    *,
    session_factory: sessionmaker = SessionLocal,
    client=None,
    focus: str = "broad",
    append: bool = False,
) -> None:
    """Draai de ontdekking in een EIGEN sessie en persisteer de bevindingen.

    ``focus`` = "broad"/"media"; ``append`` voegt de nieuwe findings toe aan de
    bestaande (gededupeerd op URL — de verdieping vult aan i.p.v. te overschrijven).
    Het seintje is de pull-based in-app chip (``chip_discovery``) + een push naar het
    lid-gekozen kanaal. Best-effort: vangt alles, markeert ``failed``. Synchroon
    aanroepbaar in tests (geef ``session_factory`` + ``client``).
    """
    try:
        with session_factory() as db:
            run = get_run(db, member_id)
            member = db.get(Member, member_id)
            if run is None or member is None:
                return
            profile = profile_service.get_or_create_profile(db, member)
            base = findings_of(run) if append else []
            db.commit()

            collected: list[dict] = []

            def _on_event(event: str, data: str) -> None:
                # Alleen kandidaten persisteren; search/fetch/reasoning/done zijn
                # live-narratie (de tail leidt de fase zelf af uit de status).
                if event != "candidate":
                    return
                try:
                    collected.append(json.loads(data))
                except (ValueError, TypeError):
                    return
                run.findings_json = json.dumps(_merge_dedup(base, collected))
                db.commit()

            fresh = footprint_service.discover(
                profile, _on_event, client=client, focus=focus
            )
            fresh_dicts = [f.as_event() for f in fresh]
            merged = _merge_dedup(base, fresh_dicts)

            # Finaliseer op de gesaneerde retourlijst (canon), niet op de losse events.
            run = get_run(db, member_id)
            if run is None:
                return
            run.findings_json = json.dumps(merged)
            run.status = STATUS_DONE if merged else STATUS_EMPTY
            run.finished_at = naive_utc(utcnow())
            db.commit()

            # Push-seintje naar het lid-gekozen kanaal (no-op bij in-app: de
            # pull-chip dekt 't al). Best-effort; geen e-mail. Bij de verdieping
            # melden we alleen de NIEUW gevonden media.
            new_count = len(merged) - len(base)
            if new_count > 0:
                from app.services import notification_service

                if focus == "media":
                    woord = "media-vermelding" if new_count == 1 else "media-vermeldingen"
                    title, body = "Ik vond media over je", (
                        f"{new_count} {woord} gevonden — kies wat op je profiel mag."
                    )
                else:
                    woord = "vermelding" if new_count == 1 else "vermeldingen"
                    title, body = "Je ontdekking is klaar", (
                        f"Ik vond {new_count} mogelijke {woord} — kies wat op je profiel mag."
                    )
                notification_service.notify(
                    db, member, notification_service.Notification(
                        kind="discovery_ready",
                        title=title,
                        body=body,
                        url="/profiel/ai/ontdek/resultaat",
                        action_label="Bekijk je ontdekking",
                    )
                )
    except Exception:  # noqa: BLE001 — achtergrond-job mag nooit crashen
        logger.exception("Discovery-job faalde voor member %s", member_id)
        _mark_failed(member_id, session_factory)
    finally:
        with _inflight_lock:
            _inflight.discard(member_id)


def _mark_failed(member_id: int, session_factory: sessionmaker) -> None:
    try:
        with session_factory() as db:
            run = get_run(db, member_id)
            if run is not None and run.status == STATUS_RUNNING:
                run.status = STATUS_FAILED
                run.error = "engine-fout"
                run.finished_at = naive_utc(utcnow())
                db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("Discovery-job: kon run niet als failed markeren (%s)", member_id)
