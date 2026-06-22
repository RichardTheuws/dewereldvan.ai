"""oEmbed-showcase (pivot Fase C) — video/audio-werk-items uit een link.

- ``detect_kind``: pure host-match (geen netwerk).
- ``resolve``: oEmbed gemockt; bouwt ZELF een sandboxed iframe uit een gevalideerde
  src; weigert een niet-allowlisted embed-host (XSS-poort) en faalt veilig naar None.
- Integratie: ``profile_service.update_offering`` zet kind + embed_html op een
  embed-link, en valt terug op ``project`` bij een gewone URL.
"""

from __future__ import annotations

import pytest
from app.models import OfferingKind
from app.services import embed_service


class _FakeResp:
    def __init__(self, payload: dict, raise_exc: bool = False) -> None:
        self._p = payload
        self._raise = raise_exc

    def raise_for_status(self) -> None:
        if self._raise:
            import httpx

            raise httpx.HTTPError("boom")

    def json(self) -> dict:
        return self._p


def _mock_oembed(monkeypatch, html: str, *, raise_exc: bool = False) -> None:
    monkeypatch.setattr(
        embed_service.httpx, "get",
        lambda *a, **k: _FakeResp({"html": html}, raise_exc=raise_exc),
    )


# --------------------------------------------------------------------------- #
# detect_kind — pure host-match                                               #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("url,kind", [
    ("https://www.youtube.com/watch?v=abc", OfferingKind.video),
    ("https://youtu.be/abc", OfferingKind.video),
    ("https://vimeo.com/12345", OfferingKind.video),
    ("https://soundcloud.com/artist/track", OfferingKind.audio),
    ("https://open.spotify.com/track/xyz", OfferingKind.audio),
    ("https://example.com/iets", None),
    ("", None),
    (None, None),
])
def test_detect_kind(url, kind):
    assert embed_service.detect_kind(url) == kind


# --------------------------------------------------------------------------- #
# resolve — bouwt veilige iframe / weigert onveilige src / fail-safe          #
# --------------------------------------------------------------------------- #
def test_resolve_youtube_builds_sandboxed_iframe(monkeypatch):
    _mock_oembed(monkeypatch, '<iframe src="https://www.youtube.com/embed/abc123" allowfullscreen></iframe>')
    out = embed_service.resolve("https://www.youtube.com/watch?v=abc123")
    assert out is not None
    kind, html = out
    assert kind is OfferingKind.video
    assert "https://www.youtube.com/embed/abc123" in html
    assert "sandbox=" in html
    assert "<iframe" in html and "embed-frame--video" in html
    assert "autoplay" not in html  # geen autoplay


def test_resolve_soundcloud_audio_shape(monkeypatch):
    _mock_oembed(monkeypatch, '<iframe src="https://w.soundcloud.com/player/?url=x"></iframe>')
    out = embed_service.resolve("https://soundcloud.com/a/b")
    assert out is not None
    kind, html = out
    assert kind is OfferingKind.audio
    assert "embed-frame--audio" in html


def test_resolve_rejects_non_allowlisted_embed_host(monkeypatch):
    # Provider matcht (youtube), maar de teruggegeven iframe-src wijst naar een
    # vreemde host → moet geweigerd worden (XSS-/clickjack-poort dicht).
    _mock_oembed(monkeypatch, '<iframe src="https://evil.example/embed/abc"></iframe>')
    assert embed_service.resolve("https://www.youtube.com/watch?v=abc") is None


def test_resolve_rejects_non_https_src(monkeypatch):
    _mock_oembed(monkeypatch, '<iframe src="http://www.youtube.com/embed/abc"></iframe>')
    assert embed_service.resolve("https://www.youtube.com/watch?v=abc") is None


def test_resolve_non_provider_url_returns_none():
    # Geen netwerk-call nodig: niet-matchende host → meteen None.
    assert embed_service.resolve("https://example.com/video") is None


def test_resolve_failsafe_on_http_error(monkeypatch):
    _mock_oembed(monkeypatch, "irrelevant", raise_exc=True)
    assert embed_service.resolve("https://vimeo.com/123") is None


def test_resolve_failsafe_on_missing_iframe(monkeypatch):
    _mock_oembed(monkeypatch, "<p>geen iframe</p>")
    assert embed_service.resolve("https://vimeo.com/123") is None


# --------------------------------------------------------------------------- #
# Integratie — update_offering zet kind + embed_html                          #
# --------------------------------------------------------------------------- #
def test_update_offering_sets_video_embed(db, make_member, make_profile, make_offering, monkeypatch):
    from app.services import profile_service

    monkeypatch.setattr(
        embed_service, "resolve",
        lambda url: (OfferingKind.video, "<div class='embed-frame--video'><iframe></iframe></div>"),
    )
    member = make_member()
    profile = make_profile(member)
    off = make_offering(profile, title="Mijn showreel")

    profile_service.update_offering(
        db, profile, off.id, url="https://www.youtube.com/watch?v=abc"
    )
    assert off.kind is OfferingKind.video
    assert off.embed_html and "iframe" in off.embed_html
    assert off.screenshot_url is None  # een speler, geen screenshot


def test_update_offering_plain_url_stays_project(db, make_member, make_profile, make_offering, monkeypatch):
    from app.services import profile_service

    monkeypatch.setattr(embed_service, "resolve", lambda url: None)
    member = make_member()
    profile = make_profile(member)
    off = make_offering(profile, title="Mijn site")

    profile_service.update_offering(
        db, profile, off.id, url="https://example.com/project"
    )
    assert off.kind is OfferingKind.project
    assert off.embed_html is None
