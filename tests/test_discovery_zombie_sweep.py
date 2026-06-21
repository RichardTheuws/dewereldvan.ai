"""Startup-vangnet voor zombie discovery-runs.

Een container-restart midden in een job laat de ``DiscoveryRun`` op ``running``
staan zonder levende thread die 'm afmaakt. ``sweep_orphaned_runs`` markeert die
verweesde runs bij app-start als ``failed`` zodat ze niet eeuwig "running" blijven.
"""

from __future__ import annotations

from app.models import DiscoveryRun
from app.services import discovery_job_service as svc


def _make_run(db, member_id: int, status: str) -> DiscoveryRun:
    run = DiscoveryRun(member_id=member_id, status=status)
    db.add(run)
    db.flush()
    return run


def test_running_run_becomes_failed(db, make_member):
    member = make_member(name="Zombie")
    _make_run(db, member.id, svc.STATUS_RUNNING)

    cleaned = svc.sweep_orphaned_runs(db)

    assert cleaned == 1
    run = svc.get_run(db, member.id)
    assert run.status == svc.STATUS_FAILED
    assert run.error == "onderbroken door herstart"
    assert run.finished_at is not None


def test_done_run_is_untouched(db, make_member):
    member = make_member(name="Klaar")
    _make_run(db, member.id, svc.STATUS_DONE)

    cleaned = svc.sweep_orphaned_runs(db)

    assert cleaned == 0
    run = svc.get_run(db, member.id)
    assert run.status == svc.STATUS_DONE
    assert run.error is None


def test_clean_state_returns_zero(db):
    assert svc.sweep_orphaned_runs(db) == 0


def test_sweep_is_idempotent(db, make_member):
    member = make_member(name="Tweemaal")
    _make_run(db, member.id, svc.STATUS_RUNNING)

    assert svc.sweep_orphaned_runs(db) == 1
    # Tweede sweep vindt geen verweesde run meer.
    assert svc.sweep_orphaned_runs(db) == 0
    assert svc.get_run(db, member.id).status == svc.STATUS_FAILED
