"""Tests for the wacht-UX SSE-events (W) — additief op de bestaande tekst-stream.

Harde regressie-garantie: de bestaande ``delta``/``done``-events blijven exact, en
de kritieke ai_profile-fixes (``_strip_citations`` + de komma-host-strip in
``_member_domains``/``_web_tools``) blijven werken. De nieuwe ``reasoning``- en
``fetch``-events zijn additief; oude clients negeren ze, en zonder thinking valt
het scherm terug op de tekst-stream (fallback-garantie).

Geen netwerk, geen Anthropic-key: de SDK wordt gemockt via ``FakeAnthropic`` /
``install_fake_anthropic`` (service-unit), en via een gepatchte ``stream_turn``
aan de service-grens (route-laag) — exact het patroon uit
``test_ai_profile_routes.py``.
"""

from __future__ import annotations

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from tests._ai_helpers import FakeAnthropic, install_fake_anthropic


# --------------------------------------------------------------------------- #
# Route fixtures (mirror test_ai_profile_routes.py)                           #
# --------------------------------------------------------------------------- #
@pytest.fixture
def route_engine():
    from app.models import Base
    from sqlalchemy import create_engine

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
def SessionTest(route_engine):
    return sessionmaker(bind=route_engine, autoflush=False, autocommit=False, future=True)


@pytest.fixture
def seed(SessionTest):
    from app.models import Member, MemberStatus

    s = SessionTest()
    approved = Member(email="builder@example.com", name="Bouwer", status=MemberStatus.approved)
    s.add(approved)
    s.commit()
    ids = {"approved": approved.id}
    s.close()
    return ids


@pytest.fixture
def make_client(route_engine, SessionTest, fake_image_generator):
    from app.db import get_db
    from app.deps import current_member, image_generator
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
        app.dependency_overrides[image_generator] = lambda: fake_image_generator
        return TestClient(app, base_url="https://testserver")

    yield _factory
    app.dependency_overrides.clear()


def _seed_turn(SessionTest, member_id: int) -> None:
    from app.models import AiChatTurn

    s = SessionTest()
    s.add(AiChatTurn(member_id=member_id, role="user", content_json='"hoi"'))
    s.commit()
    s.close()


# --------------------------------------------------------------------------- #
# delta/done intact — regressie-guard                                         #
# --------------------------------------------------------------------------- #
def test_stream_still_emits_deltas_and_done(make_client, seed, monkeypatch, SessionTest):
    """The wacht-UX patch must NOT break the existing delta + done events."""
    from app.services import ai_profile as ai_service

    _seed_turn(SessionTest, seed["approved"])

    class _Final:
        stop_reason = "end_turn"
        content = [{"type": "text", "text": "Hallo!"}]

    def _fake_stream_turn(messages, send, **kw):
        send("Hal")
        send("lo!")
        return _Final()

    monkeypatch.setattr(ai_service, "stream_turn", _fake_stream_turn)

    client = make_client(seed["approved"])
    with client.stream("GET", "/profiel/ai/stream") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = "".join(resp.iter_text())
    assert "event: delta" in body
    assert "Hal" in body and "lo!" in body
    assert "event: done" in body


# --------------------------------------------------------------------------- #
# reasoning-event                                                             #
# --------------------------------------------------------------------------- #
def test_stream_emits_reasoning_when_thinking_present(make_client, seed, monkeypatch, SessionTest):
    from app.services import ai_profile as ai_service

    _seed_turn(SessionTest, seed["approved"])

    class _Final:
        stop_reason = "end_turn"
        content = [{"type": "text", "text": "Klaar."}]

    def _fake_stream_turn(messages, send, *, on_thinking=None, on_tool_event=None, **kw):
        if on_thinking is not None:
            on_thinking("Ik denk na over de links...")
        send("Klaar.")
        return _Final()

    monkeypatch.setattr(ai_service, "stream_turn", _fake_stream_turn)

    client = make_client(seed["approved"])
    with client.stream("GET", "/profiel/ai/stream") as resp:
        body = "".join(resp.iter_text())
    assert "event: reasoning" in body
    assert "event: delta" in body
    assert "event: done" in body


def test_stream_without_thinking_falls_back_to_delta_done(
    make_client, seed, monkeypatch, SessionTest
):
    """Fallback-garantie: geen thinking -> geen reasoning-events, delta/done intact."""
    from app.services import ai_profile as ai_service

    _seed_turn(SessionTest, seed["approved"])

    class _Final:
        stop_reason = "end_turn"
        content = [{"type": "text", "text": "ok"}]

    def _fake_stream_turn(messages, send, *, on_thinking=None, on_tool_event=None, **kw):
        send("ok")  # never calls on_thinking
        return _Final()

    monkeypatch.setattr(ai_service, "stream_turn", _fake_stream_turn)

    client = make_client(seed["approved"])
    with client.stream("GET", "/profiel/ai/stream") as resp:
        body = "".join(resp.iter_text())
    assert "event: reasoning" not in body
    assert "event: delta" in body
    assert "event: done" in body


# --------------------------------------------------------------------------- #
# fetch-event (STRETCH)                                                        #
# --------------------------------------------------------------------------- #
def test_stream_emits_fetch_events(make_client, seed, monkeypatch, SessionTest):
    from app.services import ai_profile as ai_service

    _seed_turn(SessionTest, seed["approved"])

    class _Final:
        stop_reason = "end_turn"
        content = [{"type": "text", "text": "klaar"}]

    def _fake_stream_turn(messages, send, *, on_thinking=None, on_tool_event=None, **kw):
        if on_tool_event is not None:
            on_tool_event({"host": "theuws.com", "state": "ok"})
            on_tool_event({"host": "kapot.example", "state": "err"})
        send("klaar")
        return _Final()

    monkeypatch.setattr(ai_service, "stream_turn", _fake_stream_turn)

    client = make_client(seed["approved"])
    with client.stream("GET", "/profiel/ai/stream") as resp:
        body = "".join(resp.iter_text())
    assert "event: fetch" in body
    assert '"state": "ok"' in body or '"state":"ok"' in body
    assert '"state": "err"' in body or '"state":"err"' in body


# --------------------------------------------------------------------------- #
# service-unit: stream_turn surfaces thinking, keeps the critical fixes       #
# --------------------------------------------------------------------------- #
def test_stream_turn_sends_text_and_surfaces_thinking(monkeypatch):
    """on_thinking receives thinking blocks; send receives exactly the deltas."""
    from app.services import ai_profile as ai_service

    fake = FakeAnthropic(
        deltas=["Hoi ", "daar."],
        assistant_content=[
            {"type": "thinking", "thinking": "Eerst de links checken."},
            {"type": "text", "text": "Hoi daar."},
        ],
    )

    sent: list[str] = []
    thoughts: list[str] = []
    with install_fake_anthropic(monkeypatch, fake):
        final = ai_service.stream_turn(
            [{"role": "user", "content": "hoi"}],
            sent.append,
            on_thinking=thoughts.append,
        )

    assert sent == ["Hoi ", "daar."]
    assert thoughts == ["Eerst de links checken."]
    assert getattr(final, "stop_reason", None) == "end_turn"


def test_stream_turn_keeps_allowed_domains_and_strips_citations(monkeypatch):
    """The critical fixes survive the wacht-UX patch.

    - ``_member_domains`` strips a trailing comma so ``theuws.com`` (not
      ``theuws.com,``) lands in ``allowed_domains`` — the komma-host-strip.
    - server-tool-result ``citations`` are stripped before the API call.
    """
    from app.services import ai_profile as ai_service

    fake = FakeAnthropic(deltas=["ok"])

    # A user turn with a trailing comma after the URL (the regex would otherwise
    # capture "theuws.com,") + a prior assistant web_fetch result carrying the
    # forbidden ``citations`` input field.
    messages = [
        {"role": "user", "content": "Bekijk https://theuws.com, dat is mijn site."},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "web_fetch_tool_result",
                    "tool_use_id": "tu_1",
                    "citations": [{"url": "https://theuws.com"}],
                    "content": {"type": "document"},
                }
            ],
        },
    ]

    with install_fake_anthropic(monkeypatch, fake):
        ai_service.stream_turn(messages, lambda _t: None)

    assert fake.stream_kwargs, "stream(...) was never called"
    kwargs = fake.stream_kwargs[0]

    # allowed_domains is scoped to the member's host, comma stripped.
    tools = kwargs["tools"]
    fetch_tools = [t for t in tools if t.get("name") == "web_fetch"]
    assert fetch_tools, "web_fetch tool missing"
    assert fetch_tools[0].get("allowed_domains") == ["theuws.com"]

    # citations are stripped from the messages actually sent to the API.
    sent_messages = kwargs["messages"]
    for m in sent_messages:
        content = m.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "web_fetch_tool_result":
                    assert "citations" not in block


def test_stream_turn_without_callbacks_is_unchanged(monkeypatch):
    """No callbacks -> exactly the old behaviour (text deltas only)."""
    from app.services import ai_profile as ai_service

    fake = FakeAnthropic(deltas=["a", "b", "c"])
    sent: list[str] = []
    with install_fake_anthropic(monkeypatch, fake):
        ai_service.stream_turn([{"role": "user", "content": "hoi"}], sent.append)
    assert sent == ["a", "b", "c"]
