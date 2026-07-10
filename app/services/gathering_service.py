"""Gathering-service — de datumprikker (PRD-samenkomen, fase 1).

Een lid start een prikker met een handvol kandidaat-datums; leden stemmen per
datum ja/misschien/nee (één stem per datum+lid, race-veilig via savepoint — recept
``idea_service.vote``). De maker kiest de winnende datum, waarna de prikker
**samenklapt tot een gewoon agenda-event** (``post_service.create_event``) en de
ja-stemmers als ``EventAttendance`` (attending) worden overgezet — nul nieuwe
event-infra downstream.

"Auto-selectie van geïnteresseerden" leunt op de bestaande interesse-graaf
(``graph_service`` / gedeelde tags/tools) — géén locatie in fase 1. Alle poorten
(publiek/besloten) erven van ``members_service.list_public_profiles``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.models import (
    EventAttendanceRole,
    EventCategory,
    EventFrequency,
    Gathering,
    GatheringDate,
    GatheringInvite,
    GatheringState,
    GatheringVote,
    GatheringVoteChoice,
    Member,
    Post,
    Profile,
    Visibility,
)
from app.security import naive_utc, utcnow
from app.services import (
    attendance_service,
    geo_service,
    graph_service,
    members_service,
    post_service,
)

__all__ = [
    "GatheringRateLimited",
    "check_rate_limit",
    "create",
    "get",
    "list_active",
    "vote",
    "VoteResult",
    "DateTally",
    "GatheringTally",
    "tally",
    "resolve",
    "cancel",
    "SuggestedMaker",
    "suggest_interested",
    "MAX_DATE_OPTIONS",
]

# Een prikker met te veel opties wordt onleesbaar (en onmogelijk te kiezen). Bewust
# krap — een handvol avonden, niet een kalender.
MAX_DATE_OPTIONS = 8


class GatheringRateLimited(RuntimeError):
    """Het lid overschreed de prikker-rate-limit binnen het uur-venster."""


def _recent_count(db: Session, member_id: int, now: datetime) -> int:
    window_start = naive_utc(now) - timedelta(hours=1)
    return (
        db.scalar(
            select(func.count())
            .select_from(Gathering)
            .where(
                Gathering.creator_member_id == member_id,
                Gathering.created_at >= window_start,
            )
        )
        or 0
    )


def check_rate_limit(db: Session, member: Member, *, now: datetime | None = None) -> None:
    """Raise ``GatheringRateLimited`` als het lid het uur-budget overschreed
    (hergebruikt de post-drempel — zelfde spirit: dempt rommel, geen muur)."""
    now = now or utcnow()
    if _recent_count(db, member.id, now) >= settings.rate_limit_post_per_hour:
        raise GatheringRateLimited()


# --------------------------------------------------------------------------- #
# Aanmaken                                                                     #
# --------------------------------------------------------------------------- #


def create(
    db: Session,
    *,
    creator: Member,
    title: str,
    date_options: list[datetime],
    description: str | None = None,
    location_hint: str | None = None,
    interest: str | None = None,
    invited_member_ids: list[int] | None = None,
) -> Gathering:
    """Maak één datumprikker met ≥1 kandidaat-datum. Caller toetste rate-limit.

    Datums worden ontdubbeld + gesorteerd + gecapt op ``MAX_DATE_OPTIONS``. Lege
    titel/datums is een ``ValueError`` (de router valideert al, dit is de vangrail).
    Verleden-datums worden gedropt (je prikt vooruit)."""
    clean_title = (title or "").strip()[:200]
    if not clean_title:
        raise ValueError("titel is verplicht")

    now = naive_utc(utcnow())
    seen: set[datetime] = set()
    dates: list[datetime] = []
    for d in date_options or []:
        if d is None:
            continue
        dn = naive_utc(d)
        if dn <= now or dn in seen:
            continue
        seen.add(dn)
        dates.append(dn)
    dates.sort()
    dates = dates[:MAX_DATE_OPTIONS]
    if not dates:
        raise ValueError("minstens één datum in de toekomst is verplicht")

    gathering = Gathering(
        creator_member_id=creator.id,
        title=clean_title,
        description=(description or None),
        location_hint=(location_hint or "").strip()[:200] or None,
        interest=(interest or "").strip()[:120] or None,
        state=GatheringState.open,
    )
    for pos, dt in enumerate(dates):
        gathering.dates.append(GatheringDate(starts_at=dt, position=pos))
    db.add(gathering)
    db.flush()

    for mid in dict.fromkeys(invited_member_ids or []):
        if mid == creator.id:
            continue
        db.add(GatheringInvite(gathering_id=gathering.id, member_id=mid))
    db.flush()
    return gathering


def get(db: Session, gathering_id: int) -> Gathering | None:
    """Eén prikker met datums eager-geladen, of ``None``."""
    return db.scalar(
        select(Gathering)
        .where(Gathering.id == gathering_id)
        .options(selectinload(Gathering.dates))
    )


def list_active(db: Session, *, limit: int = 50) -> list[Gathering]:
    """Open prikkers, nieuwste eerst (voor een overzicht/index)."""
    return list(
        db.scalars(
            select(Gathering)
            .where(Gathering.state == GatheringState.open)
            .options(selectinload(Gathering.dates))
            .order_by(Gathering.created_at.desc())
            .limit(limit)
        )
    )


# --------------------------------------------------------------------------- #
# Stemmen (uniek per datum+lid — race-veilig via savepoint)                    #
# --------------------------------------------------------------------------- #


class VoteResult:
    """Uitkomst van een stem-poging: ``created`` is ``False`` als het lid al op
    deze datum had gestemd (dan updaten we de keuze, geen dubbele rij)."""

    __slots__ = ("created", "choice")

    def __init__(self, created: bool, choice: GatheringVoteChoice) -> None:
        self.created = created
        self.choice = choice


def vote(
    db: Session,
    *,
    member: Member,
    date: GatheringDate,
    choice: GatheringVoteChoice,
) -> VoteResult:
    """Zet (of wijzig) de stem van ``member`` op één kandidaat-datum.

    De uniekheid is HARD via ``uq_gathering_vote_date_member``. We proberen de
    insert in een savepoint; een ``IntegrityError`` (race / dubbele submit) rolt
    naar dat savepoint terug (buitenste sessie blijft intact) en dan updaten we de
    bestaande rij — geen 500, geen dubbele stem. Spiegelt ``idea_service.vote``."""
    try:
        with db.begin_nested():
            db.add(
                GatheringVote(
                    gathering_date_id=date.id, member_id=member.id, choice=choice
                )
            )
            db.flush()
        return VoteResult(created=True, choice=choice)
    except IntegrityError:
        row = db.scalar(
            select(GatheringVote).where(
                GatheringVote.gathering_date_id == date.id,
                GatheringVote.member_id == member.id,
            )
        )
        if row is not None:
            row.choice = choice
            db.flush()
        return VoteResult(created=False, choice=choice)


# --------------------------------------------------------------------------- #
# Stand opmaken (N+1-vrij)                                                      #
# --------------------------------------------------------------------------- #


@dataclass
class DateTally:
    """De stand van één kandidaat-datum, klaar voor de constellatie."""

    date: GatheringDate
    yes: int = 0
    maybe: int = 0
    no: int = 0
    viewer_choice: str | None = None

    @property
    def score(self) -> int:
        """Rangschik-score: 'ik kan' telt vol, 'misschien' half (afgerond omlaag)."""
        return self.yes * 2 + self.maybe


@dataclass
class GatheringTally:
    """De volledige stand van een prikker: per datum + wie leidt + totaal-stemmers."""

    dates: list[DateTally] = field(default_factory=list)
    leader_date_ids: list[int] = field(default_factory=list)
    voter_count: int = 0

    @property
    def has_votes(self) -> bool:
        return self.voter_count > 0

    @property
    def is_tie(self) -> bool:
        return len(self.leader_date_ids) > 1


def tally(db: Session, gathering: Gathering, *, viewer: Member | None = None) -> GatheringTally:
    """De stand van een prikker in één query (geen N+1). ``leader_date_ids`` bevat
    de datum(s) met de hoogste ja-telling (>0); meer dan één = gelijkspel (de maker
    kiest, we klappen nooit stil samen)."""
    date_ids = [d.id for d in gathering.dates]
    out = GatheringTally(dates=[DateTally(date=d) for d in gathering.dates])
    by_id = {dt.date.id: dt for dt in out.dates}
    if not date_ids:
        return out

    rows = db.scalars(
        select(GatheringVote).where(GatheringVote.gathering_date_id.in_(date_ids))
    ).all()
    viewer_id = viewer.id if viewer is not None else None
    voters: set[int] = set()
    for r in rows:
        dt = by_id.get(r.gathering_date_id)
        if dt is None:
            continue
        if r.choice == GatheringVoteChoice.yes:
            dt.yes += 1
        elif r.choice == GatheringVoteChoice.maybe:
            dt.maybe += 1
        else:
            dt.no += 1
        voters.add(r.member_id)
        if viewer_id is not None and r.member_id == viewer_id:
            dt.viewer_choice = r.choice.value
    out.voter_count = len(voters)

    best = max((dt.yes for dt in out.dates), default=0)
    if best > 0:
        out.leader_date_ids = [dt.date.id for dt in out.dates if dt.yes == best]
    return out


# --------------------------------------------------------------------------- #
# Samenklappen tot een agenda-event / annuleren                                #
# --------------------------------------------------------------------------- #


def resolve(
    db: Session,
    *,
    gathering: Gathering,
    date: GatheringDate,
    actor: Member,
) -> Post:
    """Klap de prikker samen op de gekozen datum → een gewoon agenda-event.

    Maakt een ``Post`` (kind=event, ``next_at`` = de gekozen datum), zet de maker
    als organisator en elke ja-stemmer op die datum als 'ik ga' (``attending``).
    Vanaf hier nemen de bestaande RSVP/agenda-flows het over. Idempotent: een al
    ``resolved`` prikker geeft z'n bestaande event terug (geen tweede event)."""
    if gathering.state == GatheringState.resolved and gathering.resolved_post_id:
        existing = db.get(Post, gathering.resolved_post_id)
        if existing is not None:
            return existing

    post = post_service.create_event(
        db,
        member=actor,
        title=gathering.title,
        frequency=EventFrequency.eenmalig,
        category=EventCategory.meetup,
        description=gathering.description,
        location=gathering.location_hint,
        next_at=naive_utc(date.starts_at),
    )
    gathering.state = GatheringState.resolved
    gathering.resolved_post_id = post.id

    # De maker organiseert; elke ja-stemmer op de gekozen datum 'gaat'.
    attendance_service.set_role(
        db, member=actor, post=post, role=EventAttendanceRole.organizing
    )
    yes_voter_ids = db.scalars(
        select(GatheringVote.member_id).where(
            GatheringVote.gathering_date_id == date.id,
            GatheringVote.choice == GatheringVoteChoice.yes,
        )
    ).all()
    for mid in yes_voter_ids:
        if mid == actor.id:
            continue
        voter = db.get(Member, mid)
        if voter is not None:
            attendance_service.set_role(
                db, member=voter, post=post, role=EventAttendanceRole.attending
            )
    db.flush()
    return post


def cancel(db: Session, *, gathering: Gathering) -> Gathering:
    """Blaas een open prikker af (idempotent). Een al opgeloste prikker raken we
    niet aan — die leeft verder als agenda-event."""
    if gathering.state == GatheringState.open:
        gathering.state = GatheringState.cancelled
        db.flush()
    return gathering


# --------------------------------------------------------------------------- #
# Auto-selectie van geïnteresseerden (interesse-graaf — géén locatie in fase 1) #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SuggestedMaker:
    """Eén voorgestelde deelnemer + de eerlijke grond van het voorstel.

    ``distance_band`` is een grove afstandsband ("<25 km"/"~25–50 km") als zowel de
    maker als de kandidaat een opt-in-gebied heeft en ze dichtbij zijn ("Dichtbij",
    fase 2) — anders ``None`` (dan telt puur de interesse-graaf)."""

    profile: Profile
    reason: str
    distance_band: str | None = None


def _profiles_matching_interest(db: Session, interest: str) -> list[Profile]:
    """Publieke profielen die ``interest`` als tag óf tool voeren (poort-veilig)."""
    seen: dict[int, Profile] = {}
    for key in ("tag", "tool"):
        for p in members_service.list_public_profiles(db, **{key: interest}):
            seen.setdefault(p.id, p)
    return list(seen.values())


def suggest_interested(
    db: Session, gathering: Gathering, *, limit: int = 6
) -> list[SuggestedMaker]:
    """Wie zou hier graag bij willen zijn? Op de interesse-grond van de prikker
    (gedeelde tag/tool), of — bij een open prikker — op de graaf-buren van de maker.

    Sluit de maker + al-uitgenodigde + al-gestemde leden uit (geen dubbel aanbod).
    Puur op de publieke-profielen-poort → besloten/geschorst lekt nooit."""
    exclude: set[int] = set()
    if gathering.creator_member_id is not None:
        exclude.add(gathering.creator_member_id)
    exclude |= set(
        db.scalars(
            select(GatheringInvite.member_id).where(
                GatheringInvite.gathering_id == gathering.id
            )
        ).all()
    )
    date_ids = [d.id for d in gathering.dates]
    if date_ids:
        exclude |= set(
            db.scalars(
                select(GatheringVote.member_id).where(
                    GatheringVote.gathering_date_id.in_(date_ids)
                )
            ).all()
        )

    out: list[SuggestedMaker] = []
    if gathering.interest:
        for p in _profiles_matching_interest(db, gathering.interest):
            if p.member_id in exclude:
                continue
            out.append(SuggestedMaker(profile=p, reason=f"werkt ook met {gathering.interest}"))
    else:
        creator_profile = _creator_profile(db, gathering)
        if creator_profile is not None:
            for rm in graph_service.related_members(db, creator_profile, limit=limit * 2):
                if rm.profile.member_id in exclude:
                    continue
                out.append(SuggestedMaker(profile=rm.profile, reason=rm.shared_label))

    # "Dichtbij" (fase 2): heeft de maker een opt-in-gebied, verrijk dan de suggestie
    # met een grove afstandsband en zet nabije makers vooraan. Degradeert netjes:
    # zonder maker-locatie of zonder kandidaat-locatie blijft de interesse-graaf leidend.
    out = _annotate_distance(db, gathering, out)
    return out[:limit]


def _annotate_distance(
    db: Session, gathering: Gathering, makers: list[SuggestedMaker]
) -> list[SuggestedMaker]:
    """Voeg een grove afstandsband toe (maker↔kandidaat, haversine) en sorteer
    nabij-eerst. Raakt de volgorde niet aan als de maker geen gebied heeft."""
    origin = _creator_area(db, gathering)
    if origin is None:
        return makers
    o_lat, o_lng = origin

    annotated: list[tuple[float, SuggestedMaker]] = []
    for m in makers:
        p = m.profile
        km: float | None = None
        b: str | None = None
        if p.area_lat is not None and p.area_lng is not None:
            km = geo_service.haversine_km(o_lat, o_lng, p.area_lat, p.area_lng)
            b = geo_service.band(km)
        annotated.append(
            (km if km is not None else float("inf"),
             SuggestedMaker(profile=p, reason=m.reason, distance_band=b))
        )
    # Nabije makers (mét band) eerst, op afstand oplopend; de rest houdt z'n volgorde.
    annotated_sorted = sorted(
        enumerate(annotated),
        key=lambda t: (t[1][1].distance_band is None, t[1][0], t[0]),
    )
    return [sm for _, (_, sm) in annotated_sorted]


def _creator_area(db: Session, gathering: Gathering) -> tuple[float, float] | None:
    """Het middelpunt van het opt-in-gebied van de maker (elke zichtbaarheid), of
    ``None`` als de maker geen locatie heeft aangezet."""
    if gathering.creator_member_id is None:
        return None
    prof = db.scalar(
        select(Profile).where(Profile.member_id == gathering.creator_member_id)
    )
    if prof is None or prof.area_lat is None or prof.area_lng is None:
        return None
    return (prof.area_lat, prof.area_lng)


def _creator_profile(db: Session, gathering: Gathering) -> Profile | None:
    if gathering.creator_member_id is None:
        return None
    return db.scalar(
        select(Profile).where(
            Profile.member_id == gathering.creator_member_id,
            Profile.visibility == Visibility.public,
        )
    )
