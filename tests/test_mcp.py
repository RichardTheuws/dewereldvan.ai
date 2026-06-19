"""Tests voor de MCP-laag: persoonlijke tokens + de tools (gescoped tot het lid).

De MCP-tools openen hun eigen ``SessionLocal`` en lezen het lid uit een contextvar
(de auth-middleware zet die per request). In de test patchen we ``SessionLocal``
naar de wegwerp-engine en zetten we de contextvar handmatig — zo testen we de
tool-logica + scoping zonder een draaiende server (de live-handshake is apart
gerookt). De protocol-laag (FastMCP Streamable HTTP) is van de SDK; wij testen
onze wrappers.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import sessionmaker

from tests._route_helpers import make_route_engine


@pytest.fixture
def route_engine():
    eng = make_route_engine()
    yield eng
    eng.dispose()


@pytest.fixture
def SessionTest(route_engine):
    return sessionmaker(bind=route_engine, autoflush=False, autocommit=False, future=True)


def _member(s, email="a@x.nl", name="Alice"):
    from app.models import Member, MemberStatus

    m = Member(email=email, name=name, status=MemberStatus.approved)
    s.add(m)
    s.commit()
    return m


# --------------------------------------------------------------------------- #
# token_service                                                                #
# --------------------------------------------------------------------------- #
def test_token_generate_resolve_revoke(SessionTest):
    from app.services import token_service

    s = SessionTest()
    m = _member(s)
    raw, token = token_service.generate(s, m, label="Claude Code")
    s.commit()
    assert raw.startswith("dwv_")
    # de ruwe token staat NIET in de DB (alleen de hash)
    assert token.token_hash != raw

    resolved = token_service.resolve(s, raw)
    s.commit()
    assert resolved is not None and resolved.id == m.id
    assert token_service.resolve(s, "dwv_onzin") is None
    assert token_service.resolve(s, "geen-prefix") is None

    assert token_service.revoke(s, token.id, m) is True
    s.commit()
    assert token_service.resolve(s, raw) is None  # ingetrokken → dood
    s.close()


def test_token_resolve_requires_approved(SessionTest):
    from app.models import MemberStatus
    from app.services import token_service

    s = SessionTest()
    m = _member(s)
    raw, _ = token_service.generate(s, m, label="x")
    s.commit()
    m.status = MemberStatus.suspended
    s.commit()
    assert token_service.resolve(s, raw) is None  # geschorst → geen toegang
    s.close()


# --------------------------------------------------------------------------- #
# MCP-tools (gescoped via de contextvar)                                       #
# --------------------------------------------------------------------------- #
@pytest.fixture
def as_member(SessionTest, monkeypatch):
    """Patch SessionLocal in mcp_server naar de test-engine en geef een helper om
    een lid 'in te loggen' via de contextvar."""
    import app.mcp_server as mcp

    monkeypatch.setattr(mcp, "SessionLocal", SessionTest)

    def _login(member_id):
        mcp._member_id.set(member_id)

    return _login


def test_tool_wie_ben_ik_and_writes(SessionTest, as_member):
    import app.mcp_server as mcp

    s = SessionTest()
    m = _member(s)
    mid = m.id
    s.close()
    as_member(mid)

    me = mcp.wie_ben_ik()
    assert me["naam"] == "Alice"
    assert me["projecten"] == []

    r = mcp.voeg_project_toe("Voice agent platform", "wij bouwen voice agents")
    assert r["ok"] is True
    r2 = mcp.voeg_zoekvraag_toe("spraak-datasets")
    assert r2["ok"] is True

    me2 = mcp.wie_ben_ik()
    assert "Voice agent platform" in me2["projecten"]
    assert "spraak-datasets" in me2["zoekvragen"]


def test_tool_requires_login(SessionTest, as_member):
    import app.mcp_server as mcp

    as_member(None)  # geen lid in de contextvar
    assert "fout" in mcp.wie_ben_ik()
    assert "fout" in mcp.voeg_project_toe("X")


def test_tool_zoek_makers_scoped_public(SessionTest, as_member):
    import app.mcp_server as mcp
    from app.models import Offering, Profile, Visibility

    s = SessionTest()
    a = _member(s, "a@x.nl", "Alice")
    b = _member(s, "b@x.nl", "Bob")
    aid = a.id
    pb = Profile(member_id=b.id, slug="bob", display_name="Bob",
                 visibility=Visibility.public, completeness=50)
    s.add(pb)
    s.flush()
    s.add(Offering(profile_id=pb.id, title="Voice agent platform"))
    s.commit()
    s.close()
    as_member(aid)

    res = mcp.zoek_makers("voice")
    assert any(r["naam"] == "Bob" for r in res)


# --------------------------------------------------------------------------- #
# De concierge legt de MCP-koppeling uit (geen "onbekend onderwerp")          #
# --------------------------------------------------------------------------- #
def test_concierge_explains_mcp_connect():
    from app.services import concierge_service as cs

    # direct onderwerp + synoniemen → gegronde uitleg, géén fout
    for topic in ("verbind", "mcp", "ai-tool", "claude code", "cursor"):
        r = cs.tool_explain({"topic": topic})
        assert "error" not in r, topic
        assert "MCP" in r["text"] and "/profiel/verbind" in r["text"]

    # navigate-route bestaat
    nav = cs.tool_navigate.__wrapped__ if hasattr(cs.tool_navigate, "__wrapped__") else None
    assert cs._ROUTE_TABLE["verbind"][0] == "/profiel/verbind"
    # en het zit in de surface-enum-vrije navigate-tabel; explain-tool noemt 'verbind'
    explain_tool = next(t for t in cs.TOOLS if t["name"] == "explain")
    assert "verbind" in explain_tool["description"]


# --------------------------------------------------------------------------- #
# AVG: token mee-gewist bij accountverwijdering                                #
# --------------------------------------------------------------------------- #
def test_account_deletion_removes_tokens(SessionTest):
    from app.models import Member
    from app.models.personal_token import PersonalToken
    from app.services import token_service
    from app.services.account_deletion import delete_member_completely

    s = SessionTest()
    m = _member(s)
    token_service.generate(s, m, label="x")
    s.commit()
    assert s.query(PersonalToken).count() == 1
    delete_member_completely(s, s.get(Member, m.id))
    s.commit()
    assert s.query(PersonalToken).count() == 0
    s.close()
