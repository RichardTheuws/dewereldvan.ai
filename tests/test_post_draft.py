"""Post-draft-service — agenda/nieuws-concept uit één vrije input (link/tekst).

Geen netwerk: Cloudflare-markdown gemonkeypatcht, de Claude-call is een in-memory
fake die een tool_use teruggeeft. Kernen: URL-extractie, gegronde mapping, en de
harde grondingsregel — nooit een verzonnen datum.
"""

from __future__ import annotations

from app.config import settings
from app.services import browser_render_service
from app.services import post_draft_service as pd


class _ToolUseBlock:
    type = "tool_use"

    def __init__(self, name, data):
        self.name = name
        self.input = data


class _Msg:
    def __init__(self, content):
        self.content = content


class _FakeCreate:
    def __init__(self, name, data):
        self._name = name
        self._data = data

    def create(self, **kwargs):
        return _Msg([_ToolUseBlock(self._name, self._data)])


class FakeClient:
    def __init__(self, *, name, data):
        self.messages = _FakeCreate(name, data)


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #
def test_extract_url_and_first_line():
    assert pd._extract_url("kijk op https://aimelo.nl/events, leuk") == "https://aimelo.nl/events"
    assert pd._extract_url("geen link hier") is None
    # _first_line slaat een pure URL-regel over (geen titel).
    assert pd._first_line("https://aimelo.nl\nAimelo meetup") == "Aimelo meetup"


# --------------------------------------------------------------------------- #
# Fail-safe (AI uit) — werkt altijd, geen verzinsels                          #
# --------------------------------------------------------------------------- #
def test_draft_event_failsafe_ai_off(monkeypatch):
    monkeypatch.setattr(settings, "ai_enrich_enabled", False)
    out = pd.draft_event("Aimelo meetup in Almelo, elke woensdag")
    assert out["title"] == "Aimelo meetup in Almelo, elke woensdag"
    assert out["frequency"] == "eenmalig"  # veilige default
    assert out["category"] == "meetup"  # veilige default
    assert out["next_at"] == ""  # geen datum verzonnen
    assert out["url"] == ""


def test_draft_news_failsafe_keeps_url(monkeypatch):
    monkeypatch.setattr(settings, "ai_enrich_enabled", False)
    out = pd.draft_news("https://nrc.nl/artikel-over-ai")
    assert out["url"] == "https://nrc.nl/artikel-over-ai"
    assert out["role"] == "gedeeld"
    assert out["published_at"] == ""


# --------------------------------------------------------------------------- #
# Met AI (gemockt) — gegronde mapping                                         #
# --------------------------------------------------------------------------- #
def test_draft_event_maps_ai_fields(monkeypatch):
    monkeypatch.setattr(settings, "ai_enrich_enabled", True)
    monkeypatch.setattr(browser_render_service, "markdown", lambda u: "pagina-inhoud")
    client = FakeClient(name="record_event_draft", data={
        "title": "Aimelo — AI-community Almelo",
        "frequency": "wekelijks",
        "category": "coding",
        "date_iso": "2026-07-15T19:00",
        "location": "Almelo",
        "cadence_note": "elke woensdag",
        "description": "Wekelijkse AI-meetup.",
    })
    out = pd.draft_event("https://aimelo.nl", client=client)
    assert out["title"] == "Aimelo — AI-community Almelo"
    assert out["frequency"] == "wekelijks"
    assert out["category"] == "coding"
    assert out["next_at"] == "2026-07-15T19:00"
    assert out["location"] == "Almelo"
    assert out["url"] == "https://aimelo.nl"


def test_draft_event_invalid_category_falls_back(monkeypatch):
    monkeypatch.setattr(settings, "ai_enrich_enabled", True)
    monkeypatch.setattr(browser_render_service, "markdown", lambda u: None)
    client = FakeClient(name="record_event_draft", data={"title": "X", "category": "zomaar"})
    assert pd.draft_event("iets", client=client)["category"] == "meetup"


def test_draft_event_never_invents_date(monkeypatch):
    monkeypatch.setattr(settings, "ai_enrich_enabled", True)
    monkeypatch.setattr(browser_render_service, "markdown", lambda u: None)
    # Alleen een datum zonder tijd, of leeg → next_at blijft leeg (geen verzonnen tijd).
    for date_iso in ("", "2026-07-15"):
        client = FakeClient(name="record_event_draft", data={"title": "X", "date_iso": date_iso})
        assert pd.draft_event("iets", client=client)["next_at"] == ""


def test_draft_event_invalid_frequency_falls_back(monkeypatch):
    monkeypatch.setattr(settings, "ai_enrich_enabled", True)
    monkeypatch.setattr(browser_render_service, "markdown", lambda u: None)
    client = FakeClient(name="record_event_draft", data={"title": "X", "frequency": "zomaar"})
    assert pd.draft_event("iets", client=client)["frequency"] == "eenmalig"


def test_draft_news_maps_ai_fields(monkeypatch):
    monkeypatch.setattr(settings, "ai_enrich_enabled", True)
    monkeypatch.setattr(browser_render_service, "markdown", lambda u: "artikel")
    client = FakeClient(name="record_news_draft", data={
        "title": "Hoe deze bouwer AI-agents inzet",
        "source": "Emerce",
        "role": "geinterviewd",
        "date_iso": "2026-06-20",
        "description": "Interview.",
    })
    out = pd.draft_news("https://emerce.nl/x", client=client)
    assert out["title"].startswith("Hoe deze bouwer")
    assert out["source"] == "Emerce"
    assert out["role"] == "geinterviewd"
    assert out["published_at"] == "2026-06-20"
    assert out["url"] == "https://emerce.nl/x"
