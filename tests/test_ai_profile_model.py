"""Datamodel smoke for AI-native profielbouw (additive, cascade, enum round-trip).

Tests build the schema via ``Base.metadata.create_all`` (the conftest engine), so
they prove the *models* are coherent and SQLite-safe (``native_enum=False`` =>
VARCHAR + CHECK). The Alembic migration is kept 1:1 with the models and applied
only in prod; here we assert the model side that ships with it.
"""

from __future__ import annotations

from app.models import (
    AiChatTurn,
    Base,
    Member,
    MemberStatus,
    Offering,
    ProfileLink,
    ProfileLinkKind,
)
from app.services.profile_service import get_or_create_profile
from sqlalchemy import create_engine, event, func, inspect, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def _count(db: Session, model, **filters) -> int:
    """Count rows of ``model`` matching equality ``filters`` (short, readable)."""
    stmt = select(func.count()).select_from(model)
    for attr, value in filters.items():
        stmt = stmt.where(getattr(model, attr) == value)
    return db.scalar(stmt)


def _fk_engine():
    """A fresh in-memory engine with SQLite FK enforcement ON.

    The shared conftest engine leaves ``PRAGMA foreign_keys`` at its SQLite
    default (OFF), so ``ondelete="CASCADE"`` is not enforced at the DB level
    there. To faithfully reproduce the Postgres cascade (member -> profile ->
    profile_link / ai_chat_turn) this test owns an engine with FKs enabled.
    """
    eng = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(eng, "connect")
    def _enable_fk(dbapi_conn, _rec):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(eng)
    return eng


# --- Schema presence -----------------------------------------------------------
def test_new_tables_and_columns_exist(engine):
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    assert "profile_link" in tables
    assert "ai_chat_turn" in tables

    profile_cols = {c["name"] for c in insp.get_columns("profile")}
    assert {"headline", "cover_image_url", "ai_enriched", "ai_source_text"} <= profile_cols

    offering_cols = {c["name"] for c in insp.get_columns("offering")}
    assert {"url", "image_url"} <= offering_cols

    link_cols = {c["name"] for c in insp.get_columns("profile_link")}
    assert {"label", "url", "description", "image_url", "kind", "position"} <= link_cols


# --- ProfileLinkKind round-trip (VARCHAR+CHECK, SQLite-safe) --------------------
def test_profile_link_kind_round_trip(db, make_member):
    owner = make_member(email="link@example.com", status=MemberStatus.approved)
    profile = get_or_create_profile(db, owner)
    profile.profile_links.append(
        ProfileLink(label="Oprichter", kind=ProfileLinkKind.affiliation, position=0)
    )
    profile.profile_links.append(
        ProfileLink(label="Bouwt X", kind=ProfileLinkKind.build, position=1)
    )
    db.flush()
    db.expire_all()

    reloaded = db.scalars(
        select(ProfileLink)
        .where(ProfileLink.profile_id == profile.id)
        .order_by(ProfileLink.position)
    ).all()
    assert [link.kind for link in reloaded] == [
        ProfileLinkKind.affiliation,
        ProfileLinkKind.build,
    ]


def test_profile_link_kind_defaults_to_other(db, make_member):
    owner = make_member(email="def@example.com", status=MemberStatus.approved)
    profile = get_or_create_profile(db, owner)
    link = ProfileLink(label="Iets", position=0)
    profile.profile_links.append(link)
    db.flush()
    assert link.kind is ProfileLinkKind.other


# --- Cascades ------------------------------------------------------------------
def test_member_delete_cascades_profile_links_and_chat_turns():
    """member -> profile -> profile_links + ai_chat_turns all removed on delete.

    Exercises the DB-level ``ondelete="CASCADE"`` (FK enforcement on), matching
    production Postgres where deleting a member removes their profile and every
    dependent row (profile_links, offerings, ai_chat_turns) — AVG self-deletion.
    """
    eng = _fk_engine()
    db = sessionmaker(bind=eng, future=True)()
    try:
        owner = Member(
            email="cascade@example.com", name="Cascade", status=MemberStatus.approved
        )
        db.add(owner)
        db.flush()
        profile = get_or_create_profile(db, owner)
        profile.headline = "Test"
        profile.profile_links.append(
            ProfileLink(label="Rol", kind=ProfileLinkKind.affiliation)
        )
        profile.offerings.append(Offering(title="Project", url="https://p", position=0))
        db.add(AiChatTurn(member_id=owner.id, role="user", content_json='"hoi"'))
        db.commit()

        profile_id = profile.id
        member_id = owner.id
        assert _count(db, ProfileLink, profile_id=profile_id) == 1
        assert _count(db, AiChatTurn, member_id=member_id) == 1

        db.delete(owner)
        db.commit()

        assert db.get(Member, member_id) is None
        assert _count(db, ProfileLink, profile_id=profile_id) == 0
        assert _count(db, AiChatTurn, member_id=member_id) == 0
        assert _count(db, Offering, profile_id=profile_id) == 0
    finally:
        db.close()
        eng.dispose()


def test_profile_links_ordered_by_position(db, make_member):
    owner = make_member(email="order@example.com", status=MemberStatus.approved)
    profile = get_or_create_profile(db, owner)
    profile.profile_links.append(ProfileLink(label="tweede", position=2))
    profile.profile_links.append(ProfileLink(label="eerste", position=1))
    db.flush()
    db.expire(profile, ["profile_links"])
    assert [link.label for link in profile.profile_links] == ["eerste", "tweede"]


# --- Migration <-> model parity (revisions wired correctly) --------------------
def test_migration_revision_chain():
    """The 0003 migration is chained onto 0002 (additive, never breaks 0001/0002)."""
    import importlib.util
    from pathlib import Path

    path = (
        Path(__file__).resolve().parent.parent
        / "alembic"
        / "versions"
        / "0003_ai_profile.py"
    )
    spec = importlib.util.spec_from_file_location("_mig_0003", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == "0003_ai_profile"
    assert mod.down_revision == "0002_profile_consent"
    assert callable(mod.upgrade) and callable(mod.downgrade)


def test_offering_carries_url_and_image(db, make_member):
    owner = make_member(email="off@example.com", status=MemberStatus.approved)
    profile = get_or_create_profile(db, owner)
    profile.offerings.append(
        Offering(title="Site", url="https://x", image_url="https://i", position=0)
    )
    db.flush()
    db.expire_all()
    off = db.scalars(select(Offering).where(Offering.profile_id == profile.id)).one()
    assert off.url == "https://x"
    assert off.image_url == "https://i"
