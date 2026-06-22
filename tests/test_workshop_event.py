"""Werk-item-classificatie (pivot Fase C inc. 2+3) — workshop + publicatie uit een link.

Eén Haiku-tool-call (``record_classification``) bepaalt: 'event' → workshop (datum +
locatie), 'article' → writing, 'other' → blijft project. Geen netwerk: Cloudflare-
markdown gemonkeypatcht, de Claude-call is een in-memory fake die een tool_use
teruggeeft als de call ``tools`` meestuurt (zo bedient één fake samenvatting + classificatie).
"""

from __future__ import annotations

from datetime import datetime

from app.config import settings
from app.models import Offering, OfferingKind
from app.services import browser_render_service, profile_service
from app.services import project_enrich_service as pe


# --------------------------------------------------------------------------- #
# Fakes — een tool_use-blok bij een call met ``tools``, anders platte tekst    #
# --------------------------------------------------------------------------- #
class _TextBlock:
    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class _ToolUseBlock:
    type = "tool_use"

    def __init__(self, name: str, data: dict) -> None:
        self.name = name
        self.input = data


class _Msg:
    def __init__(self, content) -> None:
        self.content = content


class _FakeCreate:
    def __init__(self, classification: dict, summary: str) -> None:
        self.classification = classification
        self.summary = summary

    def create(self, **kwargs):
        if "tools" in kwargs:
            return _Msg([_ToolUseBlock("record_classification", self.classification)])
        return _Msg([_TextBlock(self.summary)])


class FakeClient:
    def __init__(self, *, classification: dict, summary: str = "Een werk-item.") -> None:
        self.messages = _FakeCreate(classification, summary)


# --------------------------------------------------------------------------- #
# _parse_iso                                                                   #
# --------------------------------------------------------------------------- #
def test_parse_iso_date_only():
    assert pe._parse_iso("2026-07-15") == datetime(2026, 7, 15)


def test_parse_iso_with_time_and_z():
    assert pe._parse_iso("2026-07-15T19:00Z") == datetime(2026, 7, 15, 19, 0)


def test_parse_iso_garbage_is_none():
    assert pe._parse_iso("binnenkort") is None
    assert pe._parse_iso("") is None
    assert pe._parse_iso(None) is None


# --------------------------------------------------------------------------- #
# classify_work_item                                                          #
# --------------------------------------------------------------------------- #
def test_classify_event_returns_workshop(monkeypatch):
    monkeypatch.setattr(settings, "ai_enrich_enabled", True)
    client = FakeClient(classification={"category": "event", "date_iso": "2026-07-15", "location": "Online"})
    out = pe.classify_work_item("# Workshop RAG\n15 juli, online", client=client)
    assert out is not None
    assert out.kind is OfferingKind.workshop
    assert out.event_at == datetime(2026, 7, 15)
    assert out.location == "Online"


def test_classify_article_returns_writing(monkeypatch):
    monkeypatch.setattr(settings, "ai_enrich_enabled", True)
    client = FakeClient(classification={"category": "article"})
    out = pe.classify_work_item("# Mijn essay over AI-beleid", client=client)
    assert out is not None
    assert out.kind is OfferingKind.writing
    assert out.event_at is None and out.location is None


def test_classify_other_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "ai_enrich_enabled", True)
    client = FakeClient(classification={"category": "other"})
    assert pe.classify_work_item("# Een SaaS-product", client=client) is None


def test_classify_gated_off(monkeypatch):
    monkeypatch.setattr(settings, "ai_enrich_enabled", False)
    client = FakeClient(classification={"category": "event", "date_iso": "2026-07-15"})
    assert pe.classify_work_item("# Workshop", client=client) is None


def test_classify_no_markdown_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "ai_enrich_enabled", True)
    assert pe.classify_work_item(None, client=FakeClient(classification={"category": "event"})) is None


# --------------------------------------------------------------------------- #
# enrich_offering — een link wordt workshop / writing / blijft project         #
# --------------------------------------------------------------------------- #
def _offering(db, make_member, make_profile, *, email, title):
    member = make_member(email=email, name="Maker")
    profile = make_profile(member, display_name="Maker")
    off = profile_service.add_offering(db, profile, title=title, description=None)
    off.url = "https://maker.nl/x"
    db.flush()
    return off


def _mock_render(monkeypatch, markdown: str) -> None:
    monkeypatch.setattr(settings, "ai_enrich_enabled", True)
    monkeypatch.setattr(browser_render_service, "configured", lambda: True)
    monkeypatch.setattr(browser_render_service, "screenshot", lambda u: None)
    monkeypatch.setattr(browser_render_service, "markdown", lambda u: markdown)


def test_enrich_promotes_to_workshop(db, make_member, make_profile, monkeypatch):
    _mock_render(monkeypatch, "# Workshop: RAG-agent\nDi 15 juli 2026, online.")
    off = _offering(db, make_member, make_profile, email="t@x.nl", title="RAG-workshop")
    client = FakeClient(classification={"category": "event", "date_iso": "2026-07-15", "location": "Online"})
    assert pe.enrich_offering(db, off, client=client) is True
    assert off.kind is OfferingKind.workshop
    assert off.event_at == datetime(2026, 7, 15)
    assert off.location == "Online"


def test_enrich_promotes_to_writing(db, make_member, make_profile, monkeypatch):
    _mock_render(monkeypatch, "# Essay: de toekomst van AI-beleid\nEen gepubliceerd artikel.")
    off = _offering(db, make_member, make_profile, email="o@x.nl", title="AI-beleid-essay")
    client = FakeClient(classification={"category": "article"}, summary="Een essay over AI-beleid.")
    assert pe.enrich_offering(db, off, client=client) is True
    assert off.kind is OfferingKind.writing
    assert off.event_at is None


def test_enrich_plain_project_stays_project(db, make_member, make_profile, monkeypatch):
    _mock_render(monkeypatch, "# Een SaaS-product")
    off = _offering(db, make_member, make_profile, email="m@x.nl", title="SaaS")
    client = FakeClient(classification={"category": "other"}, summary="Een SaaS-product voor X.")
    pe.enrich_offering(db, off, client=client)
    assert off.kind is OfferingKind.project
    assert off.event_at is None
    assert off.summary == "Een SaaS-product voor X."
