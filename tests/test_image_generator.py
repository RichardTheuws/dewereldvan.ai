"""ImageGenerator backends + factory (F2). No network: httpx.post is patched.

Covers (bouwcontract §6 / §7):
- ``FalImageGenerator.generate`` parses ``result["images"][0]["url"]`` on success.
- Every failure mode (network error, non-2xx, empty/invalid payload) degrades
  gracefully to ``GeneratedImage(url=None)`` — never raises at the caller.
- ``get_image_generator()`` factory: Noop when FAL_KEY is empty, Fal when set +
  backend="fal".
- ``NoopImageGenerator`` always returns ``url=None``.
- ``cover_prompt`` is grounded + never fails on empty input.
"""

from __future__ import annotations

import httpx
from app.ai import (
    FalImageGenerator,
    GeneratedImage,
    NoopImageGenerator,
    cover_prompt,
    get_image_generator,
)
from app.config import settings


class _FakeResponse:
    def __init__(self, status_code: int, payload, *, raises_json: bool = False) -> None:
        self.status_code = status_code
        self._payload = payload
        self._raises_json = raises_json

    def json(self):
        if self._raises_json:
            raise ValueError("not json")
        return self._payload


# --- FalImageGenerator success -------------------------------------------------
def test_fal_generate_success_returns_url(monkeypatch):
    captured = {}

    def _fake_post(url, *, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _FakeResponse(200, {"images": [{"url": "https://cdn.fal/abc.png"}]})

    monkeypatch.setattr(httpx, "post", _fake_post)
    gen = FalImageGenerator("fal_key_123")
    result = gen.generate("een kosmische cover")

    assert result == GeneratedImage(url="https://cdn.fal/abc.png")
    assert captured["headers"]["Authorization"] == "Key fal_key_123"
    assert captured["json"]["prompt"] == "een kosmische cover"
    assert captured["json"]["image_size"] == "landscape_16_9"


# --- FalImageGenerator graceful failure ----------------------------------------
def test_fal_network_error_is_graceful(monkeypatch):
    def _boom(*a, **k):
        raise httpx.ConnectError("geen verbinding")

    monkeypatch.setattr(httpx, "post", _boom)
    assert FalImageGenerator("k").generate("x") == GeneratedImage(url=None)


def test_fal_non_2xx_is_graceful(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResponse(500, None))
    assert FalImageGenerator("k").generate("x") == GeneratedImage(url=None)


def test_fal_empty_images_is_graceful(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResponse(200, {"images": []}))
    assert FalImageGenerator("k").generate("x") == GeneratedImage(url=None)


def test_fal_invalid_json_is_graceful(monkeypatch):
    monkeypatch.setattr(
        httpx, "post", lambda *a, **k: _FakeResponse(200, None, raises_json=True)
    )
    assert FalImageGenerator("k").generate("x") == GeneratedImage(url=None)


def test_fal_non_string_url_is_graceful(monkeypatch):
    monkeypatch.setattr(
        httpx, "post", lambda *a, **k: _FakeResponse(200, {"images": [{"url": None}]})
    )
    assert FalImageGenerator("k").generate("x") == GeneratedImage(url=None)


# --- generate_many (hero-studio) ----------------------------------------------
def test_fal_generate_many_returns_all_urls(monkeypatch):
    captured = {}

    def _fake_post(url, *, json, headers, timeout):
        captured["json"] = json
        return _FakeResponse(
            200,
            {"images": [{"url": "https://cdn.fal/a.png"}, {"url": "https://cdn.fal/b.png"}]},
        )

    monkeypatch.setattr(httpx, "post", _fake_post)
    out = FalImageGenerator("k").generate_many("kosmos", 2)
    assert out == [
        GeneratedImage(url="https://cdn.fal/a.png"),
        GeneratedImage(url="https://cdn.fal/b.png"),
    ]
    assert captured["json"]["num_images"] == 2


def test_fal_generate_many_clamps_count(monkeypatch):
    captured = {}

    def _fake_post(url, *, json, headers, timeout):
        captured["json"] = json
        return _FakeResponse(200, {"images": []})

    monkeypatch.setattr(httpx, "post", _fake_post)
    FalImageGenerator("k").generate_many("x", 99)
    assert captured["json"]["num_images"] == 4  # geklemd op _MAX_VARIANTS


def test_fal_generate_many_skips_bad_items(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *a, **k: _FakeResponse(
            200, {"images": [{"url": "https://ok/1.png"}, {"url": None}, {"nope": 1}]}
        ),
    )
    out = FalImageGenerator("k").generate_many("x", 3)
    assert out == [GeneratedImage(url="https://ok/1.png")]


def test_fal_generate_many_network_error_is_empty(monkeypatch):
    def _boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "post", _boom)
    assert FalImageGenerator("k").generate_many("x", 4) == []


def test_fal_generate_many_non_2xx_is_empty(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResponse(429, None))
    assert FalImageGenerator("k").generate_many("x", 4) == []


def test_noop_generate_many_is_empty():
    assert NoopImageGenerator().generate_many("x", 4) == []


# --- Noop backend --------------------------------------------------------------
def test_noop_generate_always_none():
    assert NoopImageGenerator().generate("anything") == GeneratedImage(url=None)


# --- Factory selection ---------------------------------------------------------
def test_factory_returns_noop_when_fal_key_missing(monkeypatch):
    monkeypatch.setattr(settings, "ai_image_backend", "fal")
    monkeypatch.setattr(settings, "fal_key", None)
    assert isinstance(get_image_generator(), NoopImageGenerator)


def test_factory_returns_fal_when_key_and_backend_set(monkeypatch):
    monkeypatch.setattr(settings, "ai_image_backend", "fal")
    monkeypatch.setattr(settings, "fal_key", "fal_secret")
    gen = get_image_generator()
    assert isinstance(gen, FalImageGenerator)  # type only — no network call


def test_factory_returns_noop_when_backend_noop(monkeypatch):
    monkeypatch.setattr(settings, "ai_image_backend", "noop")
    monkeypatch.setattr(settings, "fal_key", "fal_secret")
    assert isinstance(get_image_generator(), NoopImageGenerator)


# --- cover_prompt grounding ----------------------------------------------------
def test_cover_prompt_on_empty_input_is_pure_style():
    prompt = cover_prompt(None, None)
    assert "cosmic nebula" in prompt
    assert "themes of" not in prompt  # nothing to ground on


def test_cover_prompt_includes_bio_and_tags():
    prompt = cover_prompt("Ik bouw zorgtech.", ["AI", "zorg"])
    assert "Ik bouw zorgtech." in prompt
    assert "AI" in prompt and "zorg" in prompt
