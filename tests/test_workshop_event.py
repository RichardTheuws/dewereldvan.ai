"""Workshop/sessie-detectie (pivot Fase C inc. 2) — datum + locatie uit een event-link.

Geen netwerk: Cloudflare-markdown gemonkeypatcht, de Claude-call is een in-memory
fake die een ``record_event``-tool_use teruggeeft als de call ``tools`` meestuurt
(zo bedient één fake zowel de samenvatting als de event-extractie).
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
    def __init__(self, event: dict, summary: str) -> None:
        self.event = event
        self.summary = summary

    def create(self, **kwargs):
        if "tools" in kwargs:
            return _Msg([_ToolUseBlock("record_event", self.event)])
        return _Msg([_TextBlock(self.summary)])


class FakeClient:
    def __init__(self, *, event: dict, summary: str = "Een workshop over RAG.") -> None:
        self.messages = _FakeCreate(event, summary)


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
# extract_event                                                               #
# --------------------------------------------------------------------------- #
def test_extract_event_returns_date_and_location(monkeypatch):
    monkeypatch.setattr(settings, "ai_enrich_enabled", True)
    client = FakeClient(event={"is_event": True, "date_iso": "2026-07-15", "location": "Online"})
    out = pe.extract_event("# Workshop RAG\n15 juli, online", client=client)
    assert out is not None
    event_at, location = out
    assert event_at == datetime(2026, 7, 15)
    assert location == "Online"


def test_extract_event_not_an_event_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "ai_enrich_enabled", True)
    client = FakeClient(event={"is_event": False})
    assert pe.extract_event("# Gewoon een project", client=client) is None


def test_extract_event_gated_off(monkeypatch):
    monkeypatch.setattr(settings, "ai_enrich_enabled", False)
    client = FakeClient(event={"is_event": True, "date_iso": "2026-07-15"})
    assert pe.extract_event("# Workshop", client=client) is None


def test_extract_event_no_markdown_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "ai_enrich_enabled", True)
    assert pe.extract_event(None, client=FakeClient(event={"is_event": True})) is None


# --------------------------------------------------------------------------- #
# enrich_offering — een event-link wordt een workshop                          #
# --------------------------------------------------------------------------- #
def test_enrich_offering_promotes_to_workshop(db, make_member, make_profile, monkeypatch):
    monkeypatch.setattr(settings, "ai_enrich_enabled", True)
    monkeypatch.setattr(browser_render_service, "configured", lambda: True)
    monkeypatch.setattr(browser_render_service, "screenshot", lambda u: None)
    monkeypatch.setattr(
        browser_render_service, "markdown",
        lambda u: "# Workshop: bouw een RAG-agent\nDi 15 juli 2026, online. Meld je aan.",
    )
    member = make_member(email="trainer@x.nl", name="Trainer")
    profile = make_profile(member, display_name="Trainer")
    off = profile_service.add_offering(db, profile, title="RAG-workshop", description=None)
    off.url = "https://trainer.nl/workshop-rag"
    db.flush()

    client = FakeClient(event={"is_event": True, "date_iso": "2026-07-15", "location": "Online"})
    changed = pe.enrich_offering(db, off, client=client)

    assert changed is True
    assert off.kind is OfferingKind.workshop
    assert off.event_at == datetime(2026, 7, 15)
    assert off.location == "Online"


def test_enrich_offering_plain_project_stays_project(db, make_member, make_profile, monkeypatch):
    monkeypatch.setattr(settings, "ai_enrich_enabled", True)
    monkeypatch.setattr(browser_render_service, "configured", lambda: True)
    monkeypatch.setattr(browser_render_service, "screenshot", lambda u: None)
    monkeypatch.setattr(browser_render_service, "markdown", lambda u: "# Een SaaS-product")
    member = make_member(email="maker@x.nl", name="Maker")
    profile = make_profile(member, display_name="Maker")
    off = profile_service.add_offering(db, profile, title="SaaS", description=None)
    off.url = "https://maker.nl/product"
    db.flush()

    client = FakeClient(event={"is_event": False}, summary="Een SaaS-product voor X.")
    pe.enrich_offering(db, off, client=client)

    assert off.kind is OfferingKind.project
    assert off.event_at is None
    assert off.summary == "Een SaaS-product voor X."
