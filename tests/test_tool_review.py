"""Tests voor de AI-tool-review-engine (doc 03, Fase A).

Geen netwerk, geen Anthropic-key:
- ``browser_render_service.markdown`` wordt gemockt (gegronde bron in-memory).
- Een fake Anthropic-client geeft via ``messages.create`` ÉÉN ``record_review``-
  tool-use terug (gespiegeld van test_news_briefing).
- De service draait op de rollback-geïsoleerde ``db``-fixture.

Dekt: de drempel (0 gebruikers → niet reviewen; ≥1 wel), geen url → no_source
(geen call), happy path (review gevuld, status ok, reviewed_at gezet, limitations
niet-leeg), refusal/parse-fail → status failed + oude review blijft staan,
``refresh_all`` idempotent (2e run zonder verouderde tools = 0), en de 90-daagse
cadans (een verouderde review wordt opnieuw geselecteerd).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from app.models import Tool
from app.security import naive_utc, utcnow
from app.services import tool_review_service
from sqlalchemy import select


# --------------------------------------------------------------------------- #
# Fake Anthropic met een record_review-tool-use (messages.create)             #
# --------------------------------------------------------------------------- #
class _Block:
    def __init__(self, **kw):
        self.__dict__.update(kw)

    def model_dump(self):
        return dict(self.__dict__)


class _FakeMsg:
    def __init__(self, stop_reason, content):
        self.stop_reason = stop_reason
        self.content = content


class _FakeMessages:
    def __init__(self, owner):
        self._owner = owner

    def create(self, **kwargs):
        owner = self._owner
        owner.calls.append(kwargs)
        step = owner.script[owner.call_idx]
        owner.call_idx += 1
        return _FakeMsg(step["stop_reason"], step["content"])


class FakeAnthropic:
    """Speelt een lijst van berichten af (één per ``messages.create``-call)."""

    def __init__(self, script):
        self.script = script
        self.call_idx = 0
        self.calls: list[dict] = []
        self.messages = _FakeMessages(self)


def _review_block(**fields):
    return _Block(type="tool_use", name="record_review", id="r1", input=fields)


def _good_fake(n=8):
    """Fake-client die ``n`` keer een goede review teruggeeft (één per create-call)."""
    return FakeAnthropic(
        [{"stop_reason": "end_turn", "content": [_review_block(**_GOOD_INPUT)]}]
        * n
    )


_GOOD_INPUT = {
    "one_liner": "Een agent-framework voor het bouwen van LLM-apps.",
    "good_for": ["RAG-pijplijnen", "agent-orchestratie"],
    "for_whom": "Solo-builders die snel willen prototypen.",
    "strengths": ["grote community", "veel integraties"],
    "limitations": ["abstractie-laag verbergt detail", "breaking changes"],
    "pricing_model": "open-source + betaalde cloud",
    "nlbe_relevance": None,
    "confidence": "high",
}


@pytest.fixture(autouse=True)
def _enable_and_mock(monkeypatch):
    """AI aan + markdown-bron gemockt (geen netwerk). SSRF-guard laten slagen."""
    monkeypatch.setattr(tool_review_service.settings, "ai_enrich_enabled", True)
    monkeypatch.setattr(
        tool_review_service.browser_render_service, "markdown",
        lambda url: "# Acme AI\nEen agent-framework. Pricing: gratis tier.",
    )
    # SSRF-guard: in de test mag elke (http-)URL door (geen DNS-afhankelijkheid).
    monkeypatch.setattr(
        tool_review_service.logo_service, "_safe_url",
        lambda url: bool(url) and url.startswith(("http://", "https://")),
    )


def _make_tool(db, *, name="Acme", url="https://acme.example", users=1):
    """Tool + optioneel ``users`` profielen die 'm koppelen."""
    from app.models import Member, MemberStatus, Profile

    tool = Tool(name=name, slug=name.lower().replace(" ", "-"), url=url)
    db.add(tool)
    db.flush()
    for i in range(users):
        m = Member(email=f"{name.lower()}-{i}@x.example", name=f"Lid {i}",
                   status=MemberStatus.approved)
        db.add(m)
        db.flush()
        p = Profile(member_id=m.id, slug=f"{name.lower()}-{i}", display_name=f"Lid {i}")
        p.tools.append(tool)
        db.add(p)
    db.flush()
    return tool


# --------------------------------------------------------------------------- #
# Drempel: 0 gebruikers wordt NIET gereviewd; ≥1 wel                           #
# --------------------------------------------------------------------------- #
def test_threshold_zero_users_not_reviewed(db):
    _make_tool(db, name="Lonely", url="https://lonely.example", users=0)
    fake = _good_fake()
    n = tool_review_service.refresh_all(db, client=fake)
    assert n == 0
    # Geen call gemaakt (drempel filterde de tool eruit).
    assert fake.call_idx == 0


def test_threshold_one_user_is_reviewed(db):
    _make_tool(db, name="Used", url="https://used.example", users=1)
    n = tool_review_service.refresh_all(db, client=_good_fake())
    assert n == 1
    refreshed = db.scalar(select(Tool).where(Tool.slug == "used"))
    assert refreshed.tool_review_status == "ok"


# --------------------------------------------------------------------------- #
# Geen url -> no_source, geen call                                             #
# --------------------------------------------------------------------------- #
def test_no_url_is_no_source_no_call(db):
    tool = _make_tool(db, name="NoUrl", url=None, users=1)
    fake = FakeAnthropic([])
    changed = tool_review_service.review(db, tool, client=fake)
    assert changed is True
    assert tool.tool_review_status == "no_source"
    assert tool.tool_review is None
    assert fake.call_idx == 0  # geen Claude-call


# --------------------------------------------------------------------------- #
# Happy path: review gevuld, status ok, reviewed_at gezet, limitations niet-leeg #
# --------------------------------------------------------------------------- #
def test_happy_path_fills_review(db):
    tool = _make_tool(db, name="Acme", url="https://acme.example", users=2)
    fake = FakeAnthropic([{"stop_reason": "end_turn",
                           "content": [_review_block(**_GOOD_INPUT)]}])
    changed = tool_review_service.review(db, tool, client=fake)
    assert changed is True
    assert tool.tool_review_status == "ok"
    assert tool.tool_reviewed_at is not None
    assert tool.tool_review["one_liner"].startswith("Een agent-framework")
    assert tool.tool_review["limitations"]  # niet-leeg
    assert tool.tool_review["confidence"] == "high"
    # tool_choice forceert de record_review-tool.
    assert fake.calls[0]["tool_choice"]["name"] == "record_review"
    # GEEN temperature/budget_tokens (anders 400 op Opus 4.8).
    assert "temperature" not in fake.calls[0]
    assert "budget_tokens" not in fake.calls[0]


# --------------------------------------------------------------------------- #
# Refusal -> failed, oude review blijft staan                                  #
# --------------------------------------------------------------------------- #
def test_refusal_keeps_old_review(db):
    tool = _make_tool(db, name="Refuse", url="https://refuse.example", users=1)
    old = dict(_GOOD_INPUT, one_liner="OUDE review")
    tool.tool_review = old
    tool.tool_review_status = "ok"
    old_at = naive_utc(utcnow()) - timedelta(days=1)
    tool.tool_reviewed_at = old_at
    db.flush()

    fake = FakeAnthropic([{"stop_reason": "refusal", "content": []}])
    changed = tool_review_service.review(db, tool, client=fake)
    assert changed is True
    assert tool.tool_review_status == "failed"
    # De oude review blijft INTACT (nooit met leeg overschrijven).
    assert tool.tool_review["one_liner"] == "OUDE review"
    assert tool.tool_reviewed_at == old_at


# --------------------------------------------------------------------------- #
# Parse-fail (lege limitations) -> failed, oude review blijft staan            #
# --------------------------------------------------------------------------- #
def test_empty_limitations_is_parse_fail(db):
    tool = _make_tool(db, name="Empty", url="https://empty.example", users=1)
    tool.tool_review = dict(_GOOD_INPUT, one_liner="BEHOUDEN")
    tool.tool_review_status = "ok"
    db.flush()

    bad = dict(_GOOD_INPUT, limitations=[])  # leeg = verboden -> parse-fail
    fake = FakeAnthropic([{"stop_reason": "end_turn",
                           "content": [_review_block(**bad)]}])
    changed = tool_review_service.review(db, tool, client=fake)
    assert changed is True
    assert tool.tool_review_status == "failed"
    assert tool.tool_review["one_liner"] == "BEHOUDEN"  # niet overschreven


# --------------------------------------------------------------------------- #
# refresh_all idempotent: 2e run zonder verouderde tools = 0                    #
# --------------------------------------------------------------------------- #
def test_refresh_all_idempotent(db):
    _make_tool(db, name="Idem", url="https://idem.example", users=1)
    first = tool_review_service.refresh_all(db, client=_good_fake())
    db.flush()
    assert first == 1
    second = tool_review_service.refresh_all(db, client=_good_fake())
    assert second == 0  # verse review -> niets meer te doen


# --------------------------------------------------------------------------- #
# 90-dagen-cadans: een verouderde review wordt opnieuw geselecteerd            #
# --------------------------------------------------------------------------- #
def test_stale_review_is_reselected(db):
    tool = _make_tool(db, name="Stale", url="https://stale.example", users=1)
    tool.tool_review = dict(_GOOD_INPUT)
    tool.tool_review_status = "ok"
    tool.tool_reviewed_at = naive_utc(utcnow()) - timedelta(days=91)  # > 90d
    db.flush()

    n = tool_review_service.refresh_all(db, client=_good_fake())
    assert n == 1  # verouderd -> opnieuw gereviewd

    # En een verse (recente) review wordt NIET geselecteerd.
    tool2 = _make_tool(db, name="Fresh", url="https://fresh.example", users=1)
    tool2.tool_review = dict(_GOOD_INPUT)
    tool2.tool_review_status = "ok"
    tool2.tool_reviewed_at = naive_utc(utcnow()) - timedelta(days=10)
    db.flush()
    assert tool_review_service._is_reviewable(db, tool2) is False
