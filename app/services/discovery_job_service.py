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


def start(db: Session, member: Member) -> DiscoveryRun:
    """(Her)start de ontdekking voor ``member`` en spawn de achtergrond-thread.

    Upsert: één run per lid — een nieuwe zoektocht reset de bestaande rij naar
    ``running`` (oude findings/tijdstempels gewist). De caller commit NIET; wij
    committen hier zodat de thread de verse rij ziet. Dubbel-werk-guard via
    ``_inflight`` (een al lopende job wordt niet herstart).
    """
    run = get_run(db, member.id)
    if run is None:
        run = DiscoveryRun(member_id=member.id, status=STATUS_RUNNING)
        db.add(run)
    else:
        run.status = STATUS_RUNNING
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
        target=run_job, args=(member_id,), name=f"discover-{member_id}", daemon=True
    ).start()
    return run


def run_job(
    member_id: int,
    *,
    session_factory: sessionmaker = SessionLocal,
    client=None,
) -> None:
    """Draai de ontdekking in een EIGEN sessie en persisteer de bevindingen.

    Schrijft elke binnenkomende kandidaat meteen naar de run (progressive persist:
    de tail toont ze zodra ze er zijn) en finaliseert de status op het eind.
    Het seintje is de pull-based in-app chip (``chip_discovery``), gedreven door
    de run-status — geen actieve verzending (bewust geen e-mail). Best-effort:
    vangt alles, markeert ``failed`` en stuurt nooit de thread om zeep. Synchroon
    aanroepbaar in tests (geef ``session_factory`` + ``client``).
    """
    try:
        with session_factory() as db:
            run = get_run(db, member_id)
            member = db.get(Member, member_id)
            if run is None or member is None:
                return
            profile = profile_service.get_or_create_profile(db, member)
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
                run.findings_json = json.dumps(collected)
                db.commit()

            findings = footprint_service.discover(profile, _on_event, client=client)

            # Finaliseer op de gesaneerde retourlijst (canon), niet op de losse events.
            run = get_run(db, member_id)
            if run is None:
                return
            run.findings_json = json.dumps([f.as_event() for f in findings])
            run.status = STATUS_DONE if findings else STATUS_EMPTY
            run.finished_at = naive_utc(utcnow())
            db.commit()
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
