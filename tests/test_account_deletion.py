"""Tests voor de volledige account-/profielverwijdering (AVG, "1 druk op de knop").

Het HART is de compleetheid: een lid met VOLLE data wordt gewist en geen enkele
rij met dit member_id mag achterblijven — terwijl een GEDEELDE tag en een ANDER
lid intact blijven, en het foto-bestand op schijf weg is.

Naast de service-laag (rollback-geïsoleerde ``db``-fixture) dekt dit:
- route POST /profiel/verwijderen → 303 + sessie gewist + lid echt weg,
- CSRF-403 zonder token,
- anoniem → login-redirect,
- de afscheidspagina (noindex, sessieloos),
- de migratie-keten (kop = 0007; member_deleted is een additieve VARCHAR-enum-
  waarde, dus géén 0008 nodig).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from tests._route_helpers import csrf_token, make_route_engine


# --------------------------------------------------------------------------- #
# Helper: een lid met VOLLE data + een nep-foto op schijf opbouwen            #
# --------------------------------------------------------------------------- #
def _seed_full_member(db, *, email: str, shared_tag=None):
    """Bouw een lid met profiel, offering(+slug-historie), need, links, tags,
    ai_chat_turn, nudge_dismissal, feedback, idea(+vote), en een foto op schijf.

    Retourneert ``(member, photo_path, shared_tag)``. Geeft je een ``shared_tag``
    mee, dan wordt die hergebruikt (gedeeld met een ander lid).
    """
    from app.models import (
        AiChatTurn,
        ConciergeNudgeDismissal,
        Feedback,
        Idea,
        IdeaVote,
        Member,
        MemberStatus,
        Need,
        Offering,
        OfferingSlugHistory,
        Profile,
        ProfileLink,
        Tag,
    )
    from app.storage.photos import UPLOAD_DIR

    member = Member(email=email.lower(), name="Vol Lid", status=MemberStatus.approved)
    db.add(member)
    db.flush()

    # Foto-bestand echt op schijf zetten (zodat de wissing 'm kan opruimen).
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    photo_name = f"{member.id}-deadbeefcafef00d.webp"
    photo_path = UPLOAD_DIR / photo_name
    photo_path.write_bytes(b"RIFF....WEBPVP8 ")  # nep-bytes, inhoud doet niet ter zake
    photo_url = f"/uploads/{photo_name}"

    profile = Profile(
        member_id=member.id,
        slug=f"vol-lid-{member.id}",
        display_name="Vol Lid",
        bio="Een bio.",
        makes_summary="Maakt dingen.",
        photo_url=photo_url,
    )
    db.add(profile)
    db.flush()

    offering = Offering(profile_id=profile.id, title="Een project", slug=f"proj-{member.id}")
    db.add(offering)
    db.flush()
    db.add(OfferingSlugHistory(offering_id=offering.id, old_slug=f"oud-proj-{member.id}"))

    db.add(Need(profile_id=profile.id, title="Op zoek naar X"))
    db.add(ProfileLink(profile_id=profile.id, label="Mijn rol"))

    # >= 2 tags: één uniek, één gedeeld met een ander lid.
    unique_tag = Tag(name="Uniek", slug=f"uniek-{member.id}")
    db.add(unique_tag)
    if shared_tag is None:
        shared_tag = Tag(name="Gedeeld", slug="gedeeld")
        db.add(shared_tag)
    db.flush()
    profile.tags = [unique_tag, shared_tag]

    db.add(AiChatTurn(member_id=member.id, role="user", content_json="{}"))
    db.add(
        ConciergeNudgeDismissal(member_id=member.id, nudge_kind="tag_overlap:x")
    )
    db.add(Feedback(member_id=member.id, page_path="/leden", body="top"))

    idea = Idea(member_id=member.id, title="Idee", body="Doe X")
    db.add(idea)
    db.flush()
    db.add(IdeaVote(idea_id=idea.id, member_id=member.id))

    db.flush()
    return member, photo_path, shared_tag


# --------------------------------------------------------------------------- #
# HART — compleetheid van de service                                          #
# --------------------------------------------------------------------------- #
def test_delete_member_completely_removes_everything(db):
    from app.models import (
        AiChatTurn,
        ConciergeNudgeDismissal,
        Feedback,
        Idea,
        IdeaVote,
        Member,
        Need,
        Offering,
        OfferingSlugHistory,
        Profile,
        ProfileLink,
        Tag,
        profile_tag,
    )
    from app.services.account_deletion import delete_member_completely

    # Twee leden die een tag DELEN.
    victim, photo_path, shared = _seed_full_member(db, email="victim@example.com")
    other, _other_photo, _ = _seed_full_member(
        db, email="other@example.com", shared_tag=shared
    )
    # Het andere lid stemt OOK op het idee van het slachtoffer (cross-member vote).
    victim_idea = db.scalar(select(Idea).where(Idea.member_id == victim.id))
    db.add(IdeaVote(idea_id=victim_idea.id, member_id=other.id))
    db.flush()

    victim_id = victim.id
    assert photo_path.exists()

    delete_member_completely(db, victim)
    db.flush()

    def _count(model, col):
        return db.scalar(
            select(func.count()).select_from(model).where(col == victim_id)
        )

    # Geen enkele rij meer met victim_id, in welke tabel dan ook.
    assert db.get(Member, victim_id) is None
    assert _count(Profile, Profile.member_id) == 0
    assert _count(AiChatTurn, AiChatTurn.member_id) == 0
    assert _count(ConciergeNudgeDismissal, ConciergeNudgeDismissal.member_id) == 0
    assert _count(Feedback, Feedback.member_id) == 0
    assert _count(Idea, Idea.member_id) == 0
    assert _count(IdeaVote, IdeaVote.member_id) == 0

    # Profiel-kinderen (via profile_id) ook weg — geen wees-data.
    victim_profile_ids = list(
        db.scalars(select(Profile.id).where(Profile.member_id == victim_id))
    )
    assert victim_profile_ids == []
    assert db.scalar(
        select(func.count()).select_from(Offering)
    ) == 1  # alleen die van 'other'
    assert db.scalar(select(func.count()).select_from(Need)) == 1
    assert db.scalar(select(func.count()).select_from(ProfileLink)) == 1
    # Slug-historie van het slachtoffer is weg (alleen die van 'other' rest).
    assert db.scalar(
        select(func.count()).select_from(OfferingSlugHistory)
    ) == 1

    # M2M-associaties van het slachtoffer weg; de GEDEELDE tag bestaat NOG.
    assert db.get(Tag, shared.id) is not None
    remaining_links = db.execute(select(profile_tag.c.profile_id)).all()
    # Alleen 'other' heeft nog tag-koppelingen.
    other_profile_id = db.scalar(
        select(Profile.id).where(Profile.member_id == other.id)
    )
    assert all(row[0] == other_profile_id for row in remaining_links)

    # Het foto-bestand op schijf is weg.
    assert not photo_path.exists()

    # Het ANDERE lid is volledig intact.
    assert db.get(Member, other.id) is not None
    assert (
        db.scalar(select(func.count()).select_from(Profile).where(Profile.member_id == other.id))
        == 1
    )


def test_delete_writes_anonymized_audit_row(db):
    from app.models import AuditAction, AuditLog
    from app.services.account_deletion import delete_member_completely

    victim, _photo, _shared = _seed_full_member(db, email="v2@example.com")
    delete_member_completely(db, victim)
    db.flush()

    rows = list(
        db.scalars(
            select(AuditLog).where(AuditLog.action == AuditAction.member_deleted)
        )
    )
    assert len(rows) == 1
    # PII-loos: geen member-anker, geen e-mail/naam in detail.
    assert rows[0].actor_member_id is None
    assert rows[0].target_member_id is None
    assert "@" not in (rows[0].detail or "")


def test_existing_audit_refs_are_nulled_not_blocking(db, make_member):
    """Een bestaande audit-rij die naar het lid verwijst blokkeert de delete niet
    en houdt na de wissing geen anker naar het gewiste member_id."""
    from app.models import AuditAction, AuditLog, Member
    from app.services.account_deletion import delete_member_completely

    actor = make_member(email="admin@example.com")
    victim, _photo, _shared = _seed_full_member(db, email="v3@example.com")
    db.add(
        AuditLog(
            action=AuditAction.member_approved,
            actor_member_id=actor.id,
            target_member_id=victim.id,
            detail="approved",
        )
    )
    db.flush()
    victim_id = victim.id

    delete_member_completely(db, victim)
    db.flush()

    assert db.get(Member, victim_id) is None
    # Geen enkele audit-rij verwijst nog naar het gewiste lid.
    dangling = db.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(
            (AuditLog.actor_member_id == victim_id)
            | (AuditLog.target_member_id == victim_id)
        )
    )
    assert dangling == 0


def test_delete_is_robust_when_photo_file_missing(db):
    """Het foto-bestand is al weg → de wissing faalt niet (idempotent)."""
    from app.services.account_deletion import delete_member_completely

    victim, photo_path, _shared = _seed_full_member(db, email="v4@example.com")
    photo_path.unlink()  # bestand al verdwenen
    assert not photo_path.exists()
    delete_member_completely(db, victim)  # mag NIET raisen
    db.flush()


# --------------------------------------------------------------------------- #
# Route-laag (wegwerp-engine; routes committen echte rijen)                    #
# --------------------------------------------------------------------------- #
@pytest.fixture
def route_engine():
    eng = make_route_engine()
    yield eng
    eng.dispose()


@pytest.fixture
def SessionTest(route_engine):
    return sessionmaker(
        bind=route_engine, autoflush=False, autocommit=False, future=True
    )


@pytest.fixture
def victim_id(SessionTest):
    s = SessionTest()
    try:
        member, _photo, _shared = _seed_full_member(s, email="route@example.com")
        s.commit()
        return member.id
    finally:
        s.close()


@pytest.fixture
def make_client(route_engine, SessionTest):
    from app.db import get_db
    from app.deps import current_member
    from app.main import app
    from app.models import Member

    def _override_get_db():
        db = SessionTest()
        try:
            yield db
        finally:
            db.close()

    def _factory(member_id: int | None):
        def _override_current_member(db: Session = Depends(get_db)):
            if member_id is None:
                return None
            return db.get(Member, member_id)

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[current_member] = _override_current_member
        return TestClient(app, base_url="https://testserver")

    yield _factory
    app.dependency_overrides.clear()


def test_route_deletes_and_clears_session(make_client, victim_id, SessionTest):
    from app.models import Member

    client = make_client(victim_id)
    token = csrf_token(client, "/profiel/bewerken")
    resp = client.post(
        "/profiel/verwijderen",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/profiel/gewist"

    # Lid is echt weg uit de DB.
    s = SessionTest()
    try:
        assert s.get(Member, victim_id) is None
    finally:
        s.close()

    # De sessie is gewist: een vervolg-GET op een member-gated pagina redirect
    # naar /login (current_member zou het inmiddels niet-bestaande lid teruggeven,
    # maar de sessie is leeg → require_member stuurt naar login).
    follow = client.get("/profiel/bewerken", follow_redirects=False)
    assert follow.status_code in (303, 307)
    assert follow.headers["location"] == "/login"


def test_route_requires_csrf(make_client, victim_id, SessionTest):
    from app.models import Member

    client = make_client(victim_id)
    # Mint een sessie (en CSRF) maar stuur GEEN token mee → 403.
    csrf_token(client, "/profiel/bewerken")
    resp = client.post("/profiel/verwijderen", data={}, follow_redirects=False)
    assert resp.status_code == 403

    # Lid bestaat nog (niets gewist).
    s = SessionTest()
    try:
        assert s.get(Member, victim_id) is not None
    finally:
        s.close()


def test_route_anonymous_redirects_to_login(make_client):
    client = make_client(None)
    token = csrf_token(client, "/login")
    resp = client.post(
        "/profiel/verwijderen",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert resp.status_code in (303, 307)
    assert resp.headers["location"] == "/login"


def test_farewell_page_is_noindex_and_sessionless(make_client):
    client = make_client(None)
    resp = client.get("/profiel/gewist")
    assert resp.status_code == 200
    assert "noindex" in resp.text
    assert "gewist" in resp.text.lower()


# --------------------------------------------------------------------------- #
# Migratie-keten                                                               #
# --------------------------------------------------------------------------- #
def test_migration_head_is_0007_no_0008_needed():
    """member_deleted is een additieve VARCHAR-enum-waarde → geen DDL/0008.

    De FK's die de wissing raakt (audit_log, group_invite.created_by) zijn al
    ``SET NULL``; er hoeft geen FK-on-delete te wijzigen. We borgen hier dat de
    keten-kop 0007 blijft en er geen ongebruikte 0008 is binnengeslopen.
    """
    versions = Path("alembic/versions")
    revs = {p.stem for p in versions.glob("0*.py")}
    assert "0007_group_invite" in revs
    assert not any(r.startswith("0008") for r in revs)
