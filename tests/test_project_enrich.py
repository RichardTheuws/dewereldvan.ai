"""Tests voor project-verrijking — screenshot-hero + AI-samenvatting.

Geen netwerk: Cloudflare Browser Rendering wordt gemonkeypatcht, de Claude-call
is een in-memory fake. Dekt: opslag (landscape WEBP), samenvatting (gating +
grounding-pad), enrich-orchestratie, idempotente batch, en het nullen van de
verrijking bij een URL-wijziging.
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image

from app.models import Offering
from app.services import (
    photo_service,
    profile_service,
    project_enrich_service as pe,
)


def _png(w: int = 1280, h: int = 800) -> bytes:
    img = Image.new("RGB", (w, h), (12, 12, 30))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class _TextBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class _Msg:
    def __init__(self, text):
        self.content = [_TextBlock(text)]


class _FakeCreate:
    def __init__(self, reply):
        self.reply = reply
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _Msg(self.reply)


class FakeClient:
    def __init__(self, reply="Een tool die SEO-rapporten genereert met AI."):
        self.messages = _FakeCreate(reply)


def _offering_with_url(db, make_member, make_profile, url="https://gyurka.nl"):
    member = make_member(email="p@x.nl", name="P")
    profile = make_profile(member, display_name="P")
    db.flush()
    offering = profile_service.add_offering(db, profile, title="Gyurka", description=None)
    offering.url = url
    db.flush()
    return offering


# --------------------------------------------------------------------------- #
# Opslag — landscape WEBP, geen vierkante crop                                  #
# --------------------------------------------------------------------------- #


def test_save_screenshot_writes_webp(tmp_path, monkeypatch):
    monkeypatch.setattr(photo_service, "UPLOAD_DIR", tmp_path)
    import app.storage.photos as photos

    monkeypatch.setattr(photos, "UPLOAD_DIR", tmp_path)
    url = photos.save_screenshot(_png(1280, 800), 42)
    assert url and url.endswith(".webp")
    name = url.rsplit("/", 1)[-1]
    assert (tmp_path / name).exists()


def test_save_screenshot_bad_bytes_returns_none():
    assert photo_service.save_screenshot(b"not an image", 1) is None


# --------------------------------------------------------------------------- #
# Samenvatting — gating + grounding-pad                                         #
# --------------------------------------------------------------------------- #


def test_summarize_gated_off(monkeypatch):
    monkeypatch.setattr(
        "app.services.project_enrich_service.settings.ai_enrich_enabled", False
    )
    assert pe.summarize("https://x.nl", client=FakeClient()) is None


def test_summarize_uses_markdown_and_returns_text(monkeypatch):
    monkeypatch.setattr(
        "app.services.project_enrich_service.settings.ai_enrich_enabled", True
    )
    monkeypatch.setattr(
        "app.services.browser_render_service.markdown",
        lambda u: "# Gyurka\nEen AI-SEO-tool.",
    )
    client = FakeClient()
    out = pe.summarize("https://gyurka.nl", client=client)
    assert out and "SEO" in out
    # De markdown is daadwerkelijk aan het model gevoerd (grounding-pad).
    assert "Gyurka" in client.messages.calls[0]["messages"][0]["content"]


def test_summarize_no_markdown_returns_none(monkeypatch):
    monkeypatch.setattr(
        "app.services.project_enrich_service.settings.ai_enrich_enabled", True
    )
    monkeypatch.setattr(
        "app.services.browser_render_service.markdown", lambda u: None
    )
    assert pe.summarize("https://x.nl", client=FakeClient()) is None


# --------------------------------------------------------------------------- #
# enrich_offering — screenshot + samenvatting                                   #
# --------------------------------------------------------------------------- #


def test_enrich_offering_sets_both(db, make_member, make_profile, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.services.project_enrich_service.settings.ai_enrich_enabled", True
    )
    monkeypatch.setattr("app.storage.photos.UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(photo_service, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(
        "app.services.browser_render_service.screenshot", lambda u: _png()
    )
    monkeypatch.setattr(
        "app.services.browser_render_service.markdown", lambda u: "Een SEO-tool."
    )
    offering = _offering_with_url(db, make_member, make_profile)

    assert pe.enrich_offering(db, offering, client=FakeClient()) is True
    assert offering.screenshot_url and offering.screenshot_url.endswith(".webp")
    assert offering.summary


def test_enrich_offering_no_url_is_noop(db, make_member, make_profile):
    member = make_member(email="n@x.nl", name="N")
    profile = make_profile(member, display_name="N")
    db.flush()
    offering = profile_service.add_offering(db, profile, title="Geen link", description=None)
    db.flush()
    assert pe.enrich_offering(db, offering, client=FakeClient()) is False


def test_enrich_offering_screenshot_only_when_ai_off(
    db, make_member, make_profile, monkeypatch, tmp_path
):
    """AI uit → geen samenvatting, maar de screenshot-hero wordt wél gezet."""
    monkeypatch.setattr(
        "app.services.project_enrich_service.settings.ai_enrich_enabled", False
    )
    monkeypatch.setattr("app.storage.photos.UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(photo_service, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(
        "app.services.browser_render_service.screenshot", lambda u: _png()
    )
    offering = _offering_with_url(db, make_member, make_profile)
    assert pe.enrich_offering(db, offering, client=FakeClient()) is True
    assert offering.screenshot_url
    assert offering.summary is None


# --------------------------------------------------------------------------- #
# refresh_all — idempotente batch                                              #
# --------------------------------------------------------------------------- #


def test_refresh_all_skips_already_enriched(
    db, make_member, make_profile, monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "app.services.project_enrich_service.settings.ai_enrich_enabled", True
    )
    monkeypatch.setattr("app.storage.photos.UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(photo_service, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(
        "app.services.browser_render_service.screenshot", lambda u: _png()
    )
    monkeypatch.setattr(
        "app.services.browser_render_service.markdown", lambda u: "Tekst."
    )
    offering = _offering_with_url(db, make_member, make_profile)
    db.commit()

    assert pe.refresh_all(db, client=FakeClient()) == 1
    db.commit()
    # Tweede run: al verrijkt (beide gezet) → overgeslagen.
    assert pe.refresh_all(db, client=FakeClient()) == 0


# --------------------------------------------------------------------------- #
# URL-wijziging nult de verrijking (her-genereren)                             #
# --------------------------------------------------------------------------- #


def test_url_change_clears_enrichment(db, make_member, make_profile):
    offering = _offering_with_url(db, make_member, make_profile)
    offering.screenshot_url = "/uploads/proj-1-abc.webp"
    offering.summary = "Oude samenvatting."
    db.flush()
    profile = offering.profile

    profile_service.update_offering(
        db, profile, offering.id, url="https://nieuw.nl"
    )
    assert offering.url == "https://nieuw.nl"
    assert offering.screenshot_url is None
    assert offering.summary is None


def test_same_url_keeps_enrichment(db, make_member, make_profile):
    offering = _offering_with_url(db, make_member, make_profile, url="https://gyurka.nl")
    offering.screenshot_url = "/uploads/proj-1-abc.webp"
    offering.summary = "Blijft staan."
    db.flush()
    profile = offering.profile

    # Zelfde URL opnieuw opslaan → verrijking blijft behouden.
    profile_service.update_offering(
        db, profile, offering.id, url="https://gyurka.nl", title="Gyurka 2"
    )
    assert offering.screenshot_url == "/uploads/proj-1-abc.webp"
    assert offering.summary == "Blijft staan."


# --------------------------------------------------------------------------- #
# Browser Rendering zonder creds = no-op (dev/test draait door)                #
# --------------------------------------------------------------------------- #


def test_browser_render_noop_without_creds(monkeypatch):
    from app.services import browser_render_service as br

    monkeypatch.setattr(br.settings, "cloudflare_account_id", None)
    monkeypatch.setattr(br.settings, "cloudflare_api_token", None)
    assert br.screenshot("https://x.nl") is None
    assert br.markdown("https://x.nl") is None
