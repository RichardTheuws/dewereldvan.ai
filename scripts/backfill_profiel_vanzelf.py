"""Eenmalige backfill (PRD-profiel-vanzelf §3.7) voor leden met een run van vóór v0.119.0.

Per lid: (1) koppel de bestaande vondsten met confidence ≥ 90 op de server, (2) draai de
snelle presence-ronde en vul het concept in de lege velden. Publiceert niets.

    docker exec -w /app -e PYTHONPATH=/app dewereldvan-app-web-1 \
        python scripts/backfill_profiel_vanzelf.py 40 43 44
"""

from __future__ import annotations

import sys

from app.db import SessionLocal
from app.models import Member
from app.services import discovery_job_service, profile_concept_service, profile_service


def backfill(member_id: int) -> None:
    with SessionLocal() as db:
        member = db.get(Member, member_id)
        run = discovery_job_service.get_run(db, member_id)
        if member is None or run is None:
            print(f"{member_id}: geen lid of geen run, overgeslagen")
            return
        profile = profile_service.get_or_create_profile(db, member)
        linked = [
            r for f in discovery_job_service.findings_of(run)
            if (r := profile_concept_service.auto_crystallize(db, profile, member, f))
        ]
        db.commit()
        status = run.status
    from app.services import project_enrich_service

    for r in linked:
        if r.kind == "offering":
            project_enrich_service.trigger_async(r.id)
    # Presence-ronde: append, zodat de bestaande vondsten blijven; status als voorheen.
    discovery_job_service.run_job(member_id, focus="presence", append=True, final=True)
    with SessionLocal() as db:
        member = db.get(Member, member_id)
        p = member.profile
        run = discovery_job_service.get_run(db, member_id)
        print(
            f"{member_id} {member.name}: {len(linked)} gekoppeld | kopregel={p.headline!r} | "
            f"bio={'ja' if p.bio else 'nee'} | werk={len(p.offerings)} | "
            f"zichtbaar={p.visibility.value} | run {status}→{run.status}"
        )


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        backfill(int(arg))
