"""graph_service — gegronde graaf-buren (strict uit DB, nul AI).

Unit + route: bewijst dat verbindingen UITSLUITEND uit gedeelde tags/tools komen,
correct gerangschikt/gelabeld zijn, en op het publieke profiel als "Verbonden in
de wereld" verschijnen.
"""

from __future__ import annotations

import pytest
from app.models import (
    Base,
    Member,
    MemberStatus,
    Profile,
    Tag,
    Tool,
    Visibility,
)
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def SessionTest(engine):
    return sessionmaker(bind=engine, autoflush=False, future=True)


def _profile(s, name, *, tags=(), tools=(), tag_objs=None, tool_objs=None):
    m = Member(email=f"{name.lower()}@x.nl", name=name, status=MemberStatus.approved)
    s.add(m)
    s.flush()
    p = Profile(
        member_id=m.id,
        slug=name.lower().replace(" ", "-"),
        display_name=name,
        visibility=Visibility.public,
        headline=f"Bouwt {name}-dingen",
    )
    for t in tags:
        p.tags.append(tag_objs[t])
    for t in tools:
        p.tools.append(tool_objs[t])
    s.add(p)
    s.flush()
    return p


# --------------------------------------------------------------------------- #
# Unit                                                                          #
# --------------------------------------------------------------------------- #
def test_related_members_pairs_on_shared_tag_and_tool(SessionTest):
    from app.services import graph_service

    with SessionTest() as s:
        tags = {k: Tag(slug=k, name=k) for k in ("rag", "voice")}
        tools = {k: Tool(slug=k, name=k) for k in ("cursor", "claude-code")}
        s.add_all(list(tags.values()) + list(tools.values()))
        s.flush()
        me = _profile(
            s, "Me", tags=["rag"], tools=["cursor"], tag_objs=tags, tool_objs=tools
        )
        # Deelt een tool (zwaarder gewogen).
        _profile(s, "Tool Buur", tools=["cursor"], tag_objs=tags, tool_objs=tools)
        # Deelt een tag.
        _profile(s, "Tag Buur", tags=["rag"], tag_objs=tags, tool_objs=tools)
        # Deelt niets.
        _profile(
            s, "Vreemde", tags=["voice"], tools=["claude-code"],
            tag_objs=tags, tool_objs=tools,
        )
        s.commit()

        related = graph_service.related_members(s, me)
        names = [r.profile.display_name for r in related]
        assert "Tool Buur" in names
        assert "Tag Buur" in names
        assert "Vreemde" not in names
        # Tool-overlap weegt zwaarder → Tool Buur vóór Tag Buur.
        assert names.index("Tool Buur") < names.index("Tag Buur")
        # Concreet, gegrond label.
        tool_row = next(r for r in related if r.profile.display_name == "Tool Buur")
        assert "cursor" in tool_row.shared_label


def test_related_members_empty_without_tags_or_tools(SessionTest):
    from app.services import graph_service

    with SessionTest() as s:
        me = _profile(s, "Kaal")
        _profile(s, "Ander", tags=[], tools=[])
        s.commit()
        assert graph_service.related_members(s, me) == []


def test_related_members_is_capped(SessionTest):
    from app.services import graph_service

    with SessionTest() as s:
        tags = {"shared": Tag(slug="shared", name="shared")}
        s.add(tags["shared"])
        s.flush()
        me = _profile(s, "Hub", tags=["shared"], tag_objs=tags)
        for i in range(8):
            _profile(s, f"Buur {i}", tags=["shared"], tag_objs=tags)
        s.commit()
        assert len(graph_service.related_members(s, me, limit=4)) == 4


def test_related_members_excludes_private_and_self(SessionTest):
    from app.services import graph_service

    with SessionTest() as s:
        tags = {"x": Tag(slug="x", name="x")}
        s.add(tags["x"])
        s.flush()
        me = _profile(s, "Self", tags=["x"], tag_objs=tags)
        # Besloten profiel met dezelfde tag mag NIET als buur lekken.
        m = Member(email="hidden@x.nl", name="Verborgen", status=MemberStatus.approved)
        s.add(m)
        s.flush()
        priv = Profile(
            member_id=m.id, slug="verborgen", display_name="Verborgen",
            visibility=Visibility.members,
        )
        priv.tags.append(tags["x"])
        s.add(priv)
        s.commit()
        names = [r.profile.display_name for r in graph_service.related_members(s, me)]
        assert "Self" not in names
        assert "Verborgen" not in names


def test_connection_counts_counts_shared_neighbours(SessionTest):
    from app.services import graph_service

    with SessionTest() as s:
        tags = {"x": Tag(slug="x", name="x")}
        s.add(tags["x"])
        s.flush()
        a = _profile(s, "A", tags=["x"], tag_objs=tags)
        b = _profile(s, "B", tags=["x"], tag_objs=tags)
        c = _profile(s, "C")  # geen tags/tools → graad 0
        s.commit()
        counts = graph_service.connection_counts([a, b, c])
        assert counts[a.id] == 1
        assert counts[b.id] == 1
        assert counts[c.id] == 0


# --------------------------------------------------------------------------- #
# Route — het publieke profiel toont de graaf-buren                            #
# --------------------------------------------------------------------------- #
def test_public_profile_shows_related_makers(engine, SessionTest):
    from app.db import get_db
    from app.main import app

    with SessionTest() as s:
        tools = {"cursor": Tool(slug="cursor", name="Cursor")}
        s.add(tools["cursor"])
        s.flush()
        _profile(s, "Hoofd Maker", tools=["cursor"], tool_objs=tools)
        _profile(s, "Buur Maker", tools=["cursor"], tool_objs=tools)
        s.commit()

    def _override_get_db():
        db = SessionTest()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    try:
        client = TestClient(app, base_url="https://testserver")
        resp = client.get("/leden/hoofd-maker")
        assert resp.status_code == 200
        body = resp.text
        assert "Verbonden in de wereld" in body
        assert "Buur Maker" in body
        assert "/leden/buur-maker" in body
        assert "deelt tool: cursor" in body
    finally:
        app.dependency_overrides.clear()
