"""Concierge proactieve laag (PRD §2.4) — pure-SQL kandidaat-selectie + dismiss.

**Géén LLM-call.** Deze service kiest deterministisch, met SQL, hoogstens één
proactieve suggestie die de Concierge toont *wanneer het lid zelf het oppervlak
opent met een leeg veld*. Geen autonome pop-up; wie nooit oproept, ziet niets.

Drie triggers (PRD §2.4):
1. ``profiel_bijna_af`` — eigen ``completeness`` ≥ 70 en < 100 (≥1 veld leeg).
2. ``tag_overlap``      — een ander publiek lid deelt ≥1 tag met de viewer.
3. ``nieuwe_makers``    — ≥1 nieuw approved+public lid sinds ``session.last_seen``.

Selectie-volgorde (regelgebaseerd): meeste gedeelde tags > recentheid > niet
eerder gedismissed. Eén suggestie per opening; geen sterke trigger → ``None``
(leeg, geen vulling).

Anoniem (uitgelogd, B=A): alleen de neutrale ``nieuwe_makers``-nudge; de
verbind-/profiel-nudges vereisen een eigen profiel en blijven leden-only.

Dismiss is blijvend per onderwerp: een ``ConciergeNudgeDismissal``-rij per
``(member, nudge_kind)`` houdt dezelfde suggestie ``DISMISS_DAYS`` dagen stil.
Voor anonieme bezoekers valt de dismiss terug op een cookie (router-laag).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    ConciergeNudgeDismissal,
    Member,
    MemberStatus,
    Profile,
    Visibility,
    profile_tag,
)
from app.security import naive_utc, utcnow

# Dismiss blijft 30 dagen geldig (PRD §2.4).
DISMISS_DAYS: int = 30

# Founder-welkomst valt onder dezelfde frequency-cap (PRD §5.2). Eén canonical
# spelling overal (sessie-flag, template, JS, dismiss): "founder_welcome".
FOUNDER_NUDGE_KIND: str = "founder_welcome"

# Profiel-bijna-af drempel (PRD §2.4).
_COMPLETENESS_MIN: int = 70


@dataclass(frozen=True)
class Nudge:
    """Eén proactieve suggestie. ``kind`` is de stabiele dismiss-identiteit."""

    kind: str  # bv. "profiel_bijna_af", "tag_overlap:mark-slug", "nieuwe_makers"
    message: str
    action_label: str
    action: str  # client-intent: "navigate:/...", "connect:{slug}", "founder"
    slug: str | None = None  # bij tag_overlap: de andere maker (voor de kaart)


# --------------------------------------------------------------------------- #
# Dismiss-state                                                                #
# --------------------------------------------------------------------------- #


def _active_dismissals(db: Session, member_id: int, now: datetime) -> set[str]:
    """De nudge-kinds die dit lid binnen ``DISMISS_DAYS`` heeft weggeklikt."""
    cutoff = naive_utc(now) - timedelta(days=DISMISS_DAYS)
    rows = db.scalars(
        select(ConciergeNudgeDismissal.nudge_kind).where(
            ConciergeNudgeDismissal.member_id == member_id,
            ConciergeNudgeDismissal.dismissed_at >= cutoff,
        )
    ).all()
    return set(rows)


def dismiss(
    db: Session,
    member: Member,
    nudge_kind: str,
    *,
    now: datetime | None = None,
) -> ConciergeNudgeDismissal:
    """Persisteer/ververs een dismiss voor ``(member, nudge_kind)``.

    Eén rij per member+kind: een herhaalde dismiss ververst ``dismissed_at``
    (de 30-dagen-klok herstart) i.p.v. een tweede rij te stapelen.
    """
    now = naive_utc(now or utcnow())
    row = db.scalar(
        select(ConciergeNudgeDismissal).where(
            ConciergeNudgeDismissal.member_id == member.id,
            ConciergeNudgeDismissal.nudge_kind == nudge_kind,
        )
    )
    if row is None:
        row = ConciergeNudgeDismissal(
            member_id=member.id, nudge_kind=nudge_kind, dismissed_at=now
        )
        db.add(row)
    else:
        row.dismissed_at = now
    db.flush()
    return row


# --------------------------------------------------------------------------- #
# Trigger-kandidaten (pure SQL)                                               #
# --------------------------------------------------------------------------- #


def _count_new_members(db: Session, since: datetime | None) -> int:
    """Aantal nieuwe approved+public profielen sinds ``since`` (None = alle)."""
    stmt = (
        select(func.count(func.distinct(Profile.id)))
        .select_from(Profile)
        .join(Member, Profile.member_id == Member.id)
        .where(
            Profile.visibility == Visibility.public,
            Member.status == MemberStatus.approved,
        )
    )
    if since is not None:
        stmt = stmt.where(Member.created_at >= naive_utc(since))
    return db.scalar(stmt) or 0


def _tag_overlap_candidate(
    db: Session, viewer: Member
) -> tuple[Profile, list[str]] | None:
    """Het meest-overlappende andere publieke lid (≥1 gedeelde tag) + tagnamen.

    Pure SQL: tel gedeelde tags per ander publiek profiel, sorteer op meeste
    overlap, dan recentheid. Retourneert (profiel, gedeelde_tagnamen) of None.
    """
    if viewer.profile is None or not viewer.profile.tags:
        return None
    own_tag_ids = [t.id for t in viewer.profile.tags]

    shared_count = func.count(profile_tag.c.tag_id).label("shared")
    stmt = (
        select(Profile, shared_count)
        .join(profile_tag, profile_tag.c.profile_id == Profile.id)
        .join(Member, Profile.member_id == Member.id)
        .where(
            profile_tag.c.tag_id.in_(own_tag_ids),
            Profile.id != viewer.profile.id,
            Profile.visibility == Visibility.public,
            Member.status == MemberStatus.approved,
        )
        .group_by(Profile.id)
        .order_by(shared_count.desc(), Profile.id.desc())
        .limit(1)
    )
    row = db.execute(stmt).first()
    if row is None:
        return None
    profile = row[0]
    shared_names = [t.name for t in profile.tags if t.id in set(own_tag_ids)]
    return profile, shared_names


# --------------------------------------------------------------------------- #
# Selectie — hoogstens één nudge                                              #
# --------------------------------------------------------------------------- #


def founder_welcome_nudge(viewer: Member) -> Nudge:
    """De eenmalige founder-welkomst (PRD §5.2).

    De actie opent de Concierge-stroom in 'vertel je ontstaansverhaal'-modus via
    het ``prompt``-veld (geen navigatie). ``kind`` is de canonical
    ``founder_welcome`` zodat sessie-flag, template, dismiss en JS overal gelijk
    spellen.
    """
    voornaam = (viewer.name or "").strip().split(" ")[0] if viewer.name else ""
    groet = f"Welkom terug, {voornaam}." if voornaam else "Welkom terug."
    return Nudge(
        kind=FOUNDER_NUDGE_KIND,
        message=(
            f"{groet} Jij stond aan de wieg van deze wereld — vertel je "
            "ontstaansverhaal, dan bewaren we het bij je profiel."
        ),
        action_label="vertel je verhaal",
        action="founder",
    )


def select_nudge(
    db: Session,
    viewer: Member | None,
    *,
    last_seen: datetime | None = None,
    dismissed_cookie_kinds: set[str] | None = None,
    now: datetime | None = None,
) -> Nudge | None:
    """Kies hoogstens één proactieve suggestie (PRD §2.4) — of ``None`` (leeg).

    Volgorde: tag-overlap (meeste gedeelde tags) > profiel-bijna-af > nieuwe
    makers. Reeds gedismisste kinds (DB voor leden, cookie-fallback voor anoniem)
    vallen af. Anoniem (geen viewer): alleen de neutrale ``nieuwe_makers``-nudge.
    """
    now = now or utcnow()
    cookie_dismissed = dismissed_cookie_kinds or set()

    # --- Anoniem: alleen de neutrale "N nieuwe makers" (PRD §8.B = A). ---
    if viewer is None:
        if "nieuwe_makers" in cookie_dismissed:
            return None
        return _maybe_new_members_nudge(db, last_seen)

    dismissed = _active_dismissals(db, viewer.id, now) | cookie_dismissed

    # --- 1. Tag-overlap (hoogste prioriteit: meeste gedeelde tags). ---
    candidate = _tag_overlap_candidate(db, viewer)
    if candidate is not None:
        profile, shared = candidate
        kind = f"tag_overlap:{profile.slug}"
        if kind not in dismissed and shared:
            onderwerp = shared[0]
            return Nudge(
                kind=kind,
                message=(
                    f"Jij en {profile.display_name} werken allebei aan "
                    f"{onderwerp}."
                ),
                action_label="stel je voor",
                action=f"connect:{profile.slug}",
                slug=profile.slug,
            )

    # --- 2. Eigen profiel bijna af (≥70, <100, ≥1 veld leeg). ---
    if viewer.profile is not None and "profiel_bijna_af" not in dismissed:
        pct = viewer.profile.completeness
        if _COMPLETENESS_MIN <= pct < 100:
            missing = _missing_label(viewer.profile)
            if missing:
                return Nudge(
                    kind="profiel_bijna_af",
                    message=(
                        f"Je profiel is bijna compleet — alleen {missing} "
                        f"ontbreekt nog."
                    ),
                    action_label="afmaken",
                    action="navigate:/profiel/ai/bouwen",
                )

    # --- 3. Nieuwe makers sinds vorig bezoek. ---
    if "nieuwe_makers" not in dismissed:
        nudge = _maybe_new_members_nudge(db, last_seen)
        if nudge is not None:
            return nudge

    return None  # geen sterke trigger → leeg, geen vulling.


def select_chips(
    db: Session,
    viewer: Member | None,
    *,
    view: str | None = None,
    last_seen: datetime | None = None,
    dismissed_cookie_kinds: set[str] | None = None,
    now: datetime | None = None,
) -> list[Nudge]:
    """Contextuele suggestie-chips voor de agent-canvas (Agent-Shell Fase 1).

    Hoogstens **3** deterministische chips, pure SQL (géén LLM). Dit is de
    "wegwijs maken zonder menu": de chips *zíjn* de navigatie. Aantallen komen
    UITSLUITEND uit echte SQL-tellingen (een verzonnen aantal is dezelfde
    hallucinatie-klasse als een verzonnen kaart).

    Actie-conventie:
      - ``ask:<prompt>``    → de chip spreekt de agent aan; die materialiseert de
        interface IN-STROOM (geen paginawissel). Past bij "de agent is de shell".
      - ``navigate:/pad``   → een echte link (bv. profiel afmaken op de AI-bouw-
        pagina, een eigen rijke flow buiten de canvas).

    Reeds weggeklikte kinds (DB voor leden, cookie-fallback) vallen af.
    """
    now = now or utcnow()
    cookie_dismissed = dismissed_cookie_kinds or set()
    dismissed = cookie_dismissed
    if viewer is not None:
        dismissed = _active_dismissals(db, viewer.id, now) | cookie_dismissed

    chips: list[Nudge] = []

    # 1. Tag-overlap (lid met profiel) → in-stroom introductie.
    if viewer is not None:
        candidate = _tag_overlap_candidate(db, viewer)
        if candidate is not None:
            profile, shared = candidate
            kind = f"tag_overlap:{profile.slug}"
            if kind not in dismissed and shared:
                chips.append(
                    Nudge(
                        kind=kind,
                        message=f"Stel je voor aan {profile.display_name}",
                        action_label=f"stel je voor aan {profile.display_name}",
                        action=f"ask:Stel me voor aan {profile.display_name}.",
                        slug=profile.slug,
                    )
                )

    # (Profielbouw zit niet in de chips: het prominente first-run-aanbod ín de
    #  canvas dekt dat in-stroom. De chips zijn de ontdek-laag.)

    # 3. Makers in de gids (gegrond op een echte telling) → in-stroom ledengrid.
    if "nieuwe_makers" not in dismissed:
        count = _count_new_members(db, last_seen)
        if count >= 1:
            chips.append(
                Nudge(
                    kind="nieuwe_makers",
                    message="Bekijk de makers",
                    action_label="bekijk de makers",
                    action="ask:Laat de makers zien.",
                )
            )

    # 4. Roadmap (altijd beschikbaar, laagste prioriteit) → in-stroom board.
    if "chip_roadmap" not in dismissed:
        chips.append(
            Nudge(
                kind="chip_roadmap",
                message="Bekijk de roadmap",
                action_label="bekijk de roadmap",
                action="ask:Laat de roadmap zien.",
            )
        )

    return chips[:3]


def _maybe_new_members_nudge(
    db: Session, last_seen: datetime | None
) -> Nudge | None:
    """De neutrale ``nieuwe_makers``-nudge, of None als er geen nieuwe zijn."""
    count = _count_new_members(db, last_seen)
    if count < 1:
        return None
    if last_seen is None:
        msg = f"{count} makers in de gids."
    else:
        woord = "maker" if count == 1 else "makers"
        msg = f"{count} nieuwe {woord} sinds je vorige bezoek."
    return Nudge(
        kind="nieuwe_makers",
        message=msg,
        action_label="bekijk",
        action="navigate:/leden",
    )


def _missing_label(profile: Profile) -> str | None:
    """Het eerste ontbrekende profiel-veld als leesbare NL-tekst, of None."""
    if not profile.needs:
        return "wat je zoekt"
    if not profile.offerings:
        return "een project"
    if not (profile.makes_summary and profile.makes_summary.strip()):
        return "wat je maakt"
    if not (profile.bio and profile.bio.strip()):
        return "je bio"
    if not profile.tags:
        return "onderwerpen"
    return None
