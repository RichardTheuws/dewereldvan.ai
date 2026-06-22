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


def test_classify_gallery_returns_gallery(monkeypatch):
    monkeypatch.setattr(settings, "ai_enrich_enabled", True)
    client = FakeClient(classification={"category": "gallery"})
    out = pe.classify_work_item("# Portfolio\n![werk](https://x.nl/a.jpg)", client=client)
    assert out is not None
    assert out.kind is OfferingKind.gallery
    assert out.event_at is None and out.location is None


# --------------------------------------------------------------------------- #
# extract_gallery_images — beeld-URLs uit de markdown (zero-AI)               #
# --------------------------------------------------------------------------- #
def test_extract_gallery_images_filters_dedup_and_caps():
    md = (
        "# Portfolio\n"
        "![a](https://cdn.nl/1.jpg)\n"
        "![b](https://cdn.nl/2.PNG?w=800)\n"   # extensie case + query → ok
        "![a-again](https://cdn.nl/1.jpg)\n"    # dubbel → ontdubbeld
        "![logo](https://cdn.nl/logo.png)\n"    # ruis → geweerd
        "![rel](/lokaal/3.jpg)\n"               # relatief/niet-https → geweerd
        "![doc](https://cdn.nl/brochure.pdf)\n" # geen beeld-extensie → geweerd
        "![c](https://cdn.nl/3.webp)\n"
    )
    out = pe.extract_gallery_images(md)
    assert out == [
        "https://cdn.nl/1.jpg",
        "https://cdn.nl/2.PNG?w=800",
        "https://cdn.nl/3.webp",
    ]


def test_extract_gallery_images_caps_at_max():
    md = "\n".join(f"![n](https://cdn.nl/{i}.jpg)" for i in range(50))
    assert len(pe.extract_gallery_images(md)) == pe.GALLERY_MAX_IMAGES


def test_extract_gallery_images_empty():
    assert pe.extract_gallery_images(None) == []
    assert pe.extract_gallery_images("# Geen beelden hier") == []


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


def test_enrich_promotes_to_gallery_with_images(db, make_member, make_profile, monkeypatch):
    _mock_render(
        monkeypatch,
        "# Portfolio van Mara\n"
        "![werk 1](https://cdn.nl/a.jpg)\n"
        "![werk 2](https://cdn.nl/b.png)\n"
        "![werk 3](https://cdn.nl/c.webp)\n",
    )
    off = _offering(db, make_member, make_profile, email="d@x.nl", title="Portfolio")
    client = FakeClient(classification={"category": "gallery"}, summary="Het portfolio van Mara.")
    assert pe.enrich_offering(db, off, client=client) is True
    assert off.kind is OfferingKind.gallery
    assert off.gallery_urls == [
        "https://cdn.nl/a.jpg",
        "https://cdn.nl/b.png",
        "https://cdn.nl/c.webp",
    ]


def test_enrich_gallery_too_few_images_stays_project(db, make_member, make_profile, monkeypatch):
    # Geclassificeerd als galerij, maar slechts één beeld → geen lege galerij; blijft project.
    _mock_render(monkeypatch, "# Portfolio\n![enig werk](https://cdn.nl/a.jpg)\n")
    off = _offering(db, make_member, make_profile, email="e@x.nl", title="Portfolio")
    client = FakeClient(classification={"category": "gallery"}, summary="Portfolio.")
    pe.enrich_offering(db, off, client=client)
    assert off.kind is OfferingKind.project
    assert off.gallery_urls is None
