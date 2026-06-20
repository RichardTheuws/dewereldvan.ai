"""Tests voor de cover-art-director (gegronde fal.ai-prompt per profiel)."""

from __future__ import annotations

from app.services import cover_art_service as ca
from app.services import profile_service


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
    def __init__(self, reply="soundwaves dissolving into a constellation"):
        self.messages = _FakeCreate(reply)


def _profile(db, make_member, make_profile, **kw):
    member = make_member(email="c@x.nl", name="C")
    profile = make_profile(member, display_name="C", **kw)
    db.flush()
    return profile


def test_build_prompt_gated_off_uses_fallback(db, make_member, make_profile, monkeypatch):
    monkeypatch.setattr(
        "app.services.cover_art_service.settings.ai_enrich_enabled", False
    )
    profile = _profile(db, make_member, make_profile, headline="Voice-agents bouwer")
    prompt = ca.build_prompt(profile, client=FakeClient())
    # Fallback = deterministische cover_prompt (kosmische stijl), geen "Evoking:".
    assert "cosmic nebula" in prompt
    assert "Evoking:" not in prompt


def test_build_prompt_grounded_metaphor(db, make_member, make_profile, monkeypatch):
    monkeypatch.setattr(
        "app.services.cover_art_service.settings.ai_enrich_enabled", True
    )
    profile = _profile(
        db, make_member, make_profile,
        headline="Ik bouw voice-agents", makes_summary="spraak-AI",
    )
    profile_service.set_tags(db, profile, "voice-agents")
    db.flush()
    client = FakeClient()
    prompt = ca.build_prompt(profile, client=client)
    # Kosmisch anker + de gegronde metafoor.
    assert "cosmic nebula" in prompt
    assert "Evoking: soundwaves dissolving into a constellation" in prompt
    # De brief is daadwerkelijk aan het model gevoerd (grounding).
    sent = client.messages.calls[0]["messages"][0]["content"]
    assert "voice-agents" in sent


def test_build_prompt_empty_profile_falls_back(db, make_member, make_profile, monkeypatch):
    monkeypatch.setattr(
        "app.services.cover_art_service.settings.ai_enrich_enabled", True
    )
    # Geen headline/bio/makes/tags → lege brief → fallback (puur stijl-anker).
    profile = _profile(db, make_member, make_profile)
    prompt = ca.build_prompt(profile, client=FakeClient())
    assert "cosmic nebula" in prompt
    assert "Evoking:" not in prompt


def test_build_prompt_falls_back_on_error(db, make_member, make_profile, monkeypatch):
    monkeypatch.setattr(
        "app.services.cover_art_service.settings.ai_enrich_enabled", True
    )
    profile = _profile(db, make_member, make_profile, headline="Iets")

    class _Boom:
        class messages:
            @staticmethod
            def create(**kwargs):
                raise RuntimeError("api down")

    prompt = ca.build_prompt(profile, client=_Boom())
    assert "cosmic nebula" in prompt
    assert "Evoking:" not in prompt
