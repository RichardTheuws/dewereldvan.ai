"""De hub als data (PRD hub §4.2): /makers.json, /llms.txt, JSON-LD, dofollow en de
anonieme MCP. Elk veld volgt de bezoekers-poort — wat besloten is, lekt hier niet.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from app.models import Base, Member, MemberStatus, Offering, OfferingKind, Profile, Visibility
from app.services import directory_service, seo_service
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def route_db():
    eng = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng, autoflush=False, future=True)
    with Session() as s:
        def add(email, name, slug, vis, **kw):
            m = Member(email=email, name=name, status=kw.pop("status", MemberStatus.approved))
            s.add(m)
            s.flush()
            p = Profile(member_id=m.id, slug=slug, display_name=name, visibility=vis, **kw)
            s.add(p)
            s.flush()
            return p

        mila = add("mila@x.nl", "Mila Maker", "mila", Visibility.public,
                   headline="AI-trainer", open_to=["trainingen"])
        s.add(Offering(profile_id=mila.id, title="RAG-workshop", kind=OfferingKind.workshop,
                       url="https://mila.example/workshop", slug="rag-workshop"))
        add("bo@x.nl", "Bo Besloten", "bo", Visibility.members, headline="Geheim")
        add("gs@x.nl", "Gus Geschorst", "gus", Visibility.public, status=MemberStatus.suspended)
        add("sec@x.nl", "Sem Sectie", "sem", Visibility.public, headline="Bouwer",
            open_to=["klantwerk"], public_sections=["bio"])
        s.commit()
    yield Session
    eng.dispose()


@pytest.fixture
def client(route_db):
    from app.db import get_db
    from app.main import app

    def _override():
        s = route_db()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override
    yield TestClient(app, base_url="https://testserver")
    app.dependency_overrides.clear()


def test_makers_json_only_public_and_safe(client):
    resp = client.get("/makers.json")
    assert resp.status_code == 200 and "max-age" in resp.headers["cache-control"]
    data = resp.json()
    names = {m["naam"] for m in data["makers"]}
    assert names == {"Mila Maker", "Sem Sectie"}  # besloten + geschorst vallen weg
    assert data["aantal"] == 2
    mila = next(m for m in data["makers"] if m["naam"] == "Mila Maker")
    assert mila["disciplines"] == ["Trainer"]
    assert mila["open_voor"] == ["Trainingen"]
    assert mila["contact"].endswith("/leden/mila/vraag")
    assert mila["werk"][0]["site"] == "https://mila.example/workshop"
    assert "@" not in json.dumps(data)  # nooit een e-mailadres


def test_makers_json_respects_hidden_sections(client):
    sem = next(m for m in client.get("/makers.json").json()["makers"] if m["naam"] == "Sem Sectie")
    assert "open_voor" not in sem and "werk" not in sem and sem["disciplines"] == []


def test_llms_txt(client):
    resp = client.get("/llms.txt")
    assert resp.status_code == 200 and resp.headers["content-type"].startswith("text/plain")
    body = resp.text
    assert body.startswith("# dewereldvan.ai")
    assert "/makers.json" in body and "/leden/mila" in body and "Trainers: 1" in body
    assert "Bo Besloten" not in body and "Gus" not in body


def test_jsonld_person_services_and_contact(route_db):
    with route_db() as s:
        from sqlalchemy import select

        mila = s.scalar(select(Profile).where(Profile.slug == "mila"))
        data = seo_service.jsonld_person(mila)
        services = [o["itemOffered"] for o in data["makesOffer"]
                    if o["itemOffered"]["@type"] == "Service"]
        assert services[0]["name"] == "Trainingen"
        assert data["hasOccupation"] == [{"@type": "Occupation", "name": "Trainer"}]
        assert data["contactPoint"]["url"].endswith("/leden/mila/vraag")
        sem = s.scalar(select(Profile).where(Profile.slug == "sem"))
        from app.services import visibility

        sem_data = seo_service.jsonld_person(sem, sections=visibility.visible_sections(sem, None))
        assert "makesOffer" not in sem_data and "hasOccupation" not in sem_data


def test_public_project_link_is_dofollow(client):
    html = client.get("/projecten/rag-workshop").text
    assert 'href="https://mila.example/workshop" target="_blank" rel="noopener"' in html


def test_search_public_excludes_closed(route_db):
    with route_db() as s:
        assert [r["naam"] for r in directory_service.search_public(s, "workshop")] == ["Mila Maker"]
        assert directory_service.search_public(s, "Geheim") == []


# --------------------------------------------------------------------------- #
# MCP anoniem                                                                  #
# --------------------------------------------------------------------------- #
def test_mcp_zoek_makers_anonymous_uses_public_directory(route_db, monkeypatch):
    import app.mcp_server as mcp

    monkeypatch.setattr(mcp, "SessionLocal", route_db)
    tok = mcp._member_id.set(None)
    try:
        res = mcp.zoek_makers("workshop")
    finally:
        mcp._member_id.reset(tok)
    assert res and res[0]["naam"] == "Mila Maker" and "contact" in res[0]


def _run_auth(headers: list[tuple[bytes, bytes]], ip="5.5.5.5"):
    import app.mcp_server as mcp

    seen: dict = {}

    async def inner(scope, receive, send):
        seen["member"] = mcp._member_id.get()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    sent: list = []

    async def send(msg):
        sent.append(msg)

    async def receive():
        return {"type": "http.request", "body": b""}

    scope = {"type": "http", "headers": headers, "client": (ip, 1)}
    asyncio.run(mcp._BearerAuth(inner)(scope, receive, send))
    return sent[0]["status"], seen


def test_mcp_no_token_passes_as_anonymous():
    status, seen = _run_auth([])
    assert status == 200 and seen["member"] is None


def test_mcp_bad_token_is_401(monkeypatch):
    import app.mcp_server as mcp

    monkeypatch.setattr(mcp.token_service, "resolve", lambda db, raw: None)
    status, _ = _run_auth([(b"authorization", b"Bearer dwv_fout")])
    assert status == 401


def test_mcp_anonymous_rate_limit(monkeypatch):
    import app.mcp_server as mcp

    monkeypatch.setattr(mcp, "_anon_hits", {})
    for _ in range(mcp.ANON_LIMIT_PER_MIN):
        assert _run_auth([], ip="7.7.7.7")[0] == 200
    assert _run_auth([], ip="7.7.7.7")[0] == 429
    assert _run_auth([], ip="8.8.8.8")[0] == 200
