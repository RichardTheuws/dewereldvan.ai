"""AI-steekproef (PRD hub §4.4 deel 2) — met een nep-client, geen netwerk."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.config import settings
from app.models import AiProbe, Offering, OfferingKind, Tag, Visibility
from app.services import ai_probe_service
from sqlalchemy import func, select


class FakeClient:
    """Geeft een vast antwoord; optioneel eerst een pause_turn."""

    def __init__(self, text, urls=(), pause_first=False):
        self.calls = 0
        self._text, self._urls, self._pause = text, list(urls), pause_first
        self.messages = self

    def create(self, **kw):
        self.calls += 1
        if self._pause and self.calls == 1:
            return SimpleNamespace(stop_reason="pause_turn", content=[
                {"type": "server_tool_use", "id": "s1", "name": "web_search", "input": {}}])
        cites = [{"type": "web_search_result_location", "url": u} for u in self._urls]
        return SimpleNamespace(stop_reason="end_turn", content=[
            {"type": "text", "text": self._text, "citations": cites}])


@pytest.fixture
def maker(db, make_member, make_profile):
    p = make_profile(make_member(), display_name="Mila de Graaf", headline="AI-trainer voor zorg",
                     visibility=Visibility.public)
    p.tags.append(Tag(slug="zorg", name="zorg"))
    db.add(Offering(profile_id=p.id, title="Workshop", kind=OfferingKind.workshop))
    db.flush()
    db.refresh(p)
    return p


@pytest.fixture
def ai_on(monkeypatch):
    monkeypatch.setattr(settings, "ai_enrich_enabled", True)


def test_questions_from_public_listing(maker):
    qs = ai_probe_service.questions_for(maker)
    assert qs[0] == "Welke AI-trainers in Nederland of België kun je aanraden voor zorg?"
    assert "AI-trainer voor zorg" in qs[1]


def test_questions_respect_hidden_makes(db, maker):
    maker.public_sections = ["bio"]
    db.flush()
    qs = ai_probe_service.questions_for(maker)
    assert len(qs) == 1 and "aanraden" not in qs[0]  # geen discipline uit besloten werk


def test_evaluate_mentions_and_hub(maker):
    a = ai_probe_service.ProbeAnswer("Probeer Mila de Graaf.", ["https://dewereldvan.ai/leden/mila"])
    assert ai_probe_service.evaluate(maker, a) == (True, True)
    b = ai_probe_service.ProbeAnswer("Probeer bureau X.", ["https://x.nl"])
    assert ai_probe_service.evaluate(maker, b) == (False, False)


def test_ask_handles_pause_turn():
    client = FakeClient("Mila de Graaf", ["https://dewereldvan.ai/x"], pause_first=True)
    ans = ai_probe_service.ask("vraag", client=client)
    assert client.calls == 2 and ans.sources == ["https://dewereldvan.ai/x"]


def test_run_month_is_idempotent(db, maker, ai_on, monkeypatch):
    monkeypatch.setattr(db, "commit", db.flush)  # binnen de test-transactie blijven
    client = FakeClient("Mila de Graaf geeft trainingen.", ["https://dewereldvan.ai/leden/mila"])
    assert ai_probe_service.run_month(db, month="2026-11", client=client) == 2
    assert ai_probe_service.run_month(db, month="2026-11", client=client) == 0
    assert client.calls == 2
    rows = ai_probe_service.latest_for(db, maker.id)
    assert len(rows) == 2 and all(r.mentioned and r.hub_cited for r in rows)


def test_run_month_respects_limit_and_closed(db, maker, ai_on, monkeypatch):
    monkeypatch.setattr(db, "commit", db.flush)
    maker.visibility = Visibility.members
    db.flush()
    assert ai_probe_service.run_month(db, month="2026-11", client=FakeClient("x")) == 0
    maker.visibility = Visibility.public
    db.flush()
    assert ai_probe_service.run_month(db, month="2026-12", client=FakeClient("x"), limit=1) == 1


def test_run_month_off_without_ai(db, maker, monkeypatch):
    monkeypatch.setattr(settings, "ai_enrich_enabled", False)
    client = FakeClient("x")
    assert ai_probe_service.run_month(db, client=client) == 0 and client.calls == 0
    assert db.scalar(select(func.count(AiProbe.id))) == 0
