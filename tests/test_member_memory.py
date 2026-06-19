"""Tests voor het sessie-overstijgend concierge-geheugen (Fase 2).

Dekt: distill (write + hoogwatermerk + idempotentie), de prompt-injectie in de
stream-system, de AVG-reset (clear_turns wist het geheugen mee), en de gating.
Geen netwerk: een in-memory fake voor ``messages.create``.
"""

from __future__ import annotations

import anthropic
import pytest

from app.models import Member
from app.services import (
    concierge_service,
    concierge_state,
    member_memory_service as mm,
)


# --------------------------------------------------------------------------- #
# Fake Anthropic met messages.create (de distill-call)                        #
# --------------------------------------------------------------------------- #


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
    def __init__(self, reply="- bouwt voice-agents\n- zoekt een designer"):
        self.messages = _FakeCreate(reply)


def _seed_turns(db, member_id, *pairs):
    for role, content in pairs:
        concierge_state.append_turn(db, member_id, role, content)
    db.flush()


# --------------------------------------------------------------------------- #
# build_memory_block — de prompt-aanvulling                                    #
# --------------------------------------------------------------------------- #


def test_memory_block_empty_is_blank():
    assert mm.build_memory_block(None) == ""
    assert mm.build_memory_block("   ") == ""


def test_memory_block_includes_memory_as_background():
    block = mm.build_memory_block("- bouwt voice-agents")
    assert "voice-agents" in block
    # Expliciet als achtergrond, niet als instructie (injectie-discipline).
    assert "achtergrond" in block.lower()
    assert "instructie" in block.lower()


# --------------------------------------------------------------------------- #
# distill_member — write + hoogwatermerk + idempotentie                        #
# --------------------------------------------------------------------------- #


def test_distill_writes_memory_and_watermark(db, make_member):
    member = make_member(email="a@x.nl", name="A")
    db.flush()
    _seed_turns(
        db, member.id,
        ("user", "Ik bouw voice-agents en zoek een designer."),
        ("assistant", "Helder, ik kijk mee."),
    )
    client = FakeClient()

    assert mm.distill_member(db, member, client=client) is True
    assert member.member_memory and "voice-agents" in member.member_memory
    assert member.memory_synced_turn_id is not None
    # De distill-call kreeg het huidige geheugen + de turns mee.
    sent = client.messages.calls[0]["messages"][0]["content"]
    assert "voice-agents" in sent


def test_distill_is_idempotent_without_new_turns(db, make_member):
    member = make_member(email="b@x.nl", name="B")
    db.flush()
    _seed_turns(db, member.id, ("user", "Ik maak RAG-pipelines."))
    client = FakeClient(reply="- maakt RAG-pipelines")

    assert mm.distill_member(db, member, client=client) is True
    # Tweede keer zonder nieuwe turns → geen call meer, geen update.
    assert mm.distill_member(db, member, client=client) is False
    assert len(client.messages.calls) == 1


def test_distill_runs_again_after_new_turn(db, make_member):
    member = make_member(email="c@x.nl", name="C")
    db.flush()
    _seed_turns(db, member.id, ("user", "Ik maak agents."))
    client = FakeClient()
    assert mm.distill_member(db, member, client=client) is True

    _seed_turns(db, member.id, ("user", "Ik zoek nu ook een co-founder."))
    assert mm.distill_member(db, member, client=client) is True
    assert len(client.messages.calls) == 2


def test_distill_no_turns_is_noop(db, make_member):
    member = make_member(email="d@x.nl", name="D")
    db.flush()
    client = FakeClient()
    assert mm.distill_member(db, member, client=client) is False
    assert member.member_memory is None
    assert client.messages.calls == []


# --------------------------------------------------------------------------- #
# refresh_all — gating + batch                                                 #
# --------------------------------------------------------------------------- #


def test_refresh_all_gated_off(db, make_member, monkeypatch):
    member = make_member(email="e@x.nl", name="E")
    db.flush()
    _seed_turns(db, member.id, ("user", "Ik bouw chatbots."))
    monkeypatch.setattr(
        "app.services.member_memory_service.settings.ai_enrich_enabled", False
    )
    assert mm.refresh_all(db, client=FakeClient()) == 0


def test_refresh_all_distills_members_with_turns(db, make_member, monkeypatch):
    monkeypatch.setattr(
        "app.services.member_memory_service.settings.ai_enrich_enabled", True
    )
    m1 = make_member(email="f@x.nl", name="F")
    m2 = make_member(email="g@x.nl", name="G")
    db.flush()
    _seed_turns(db, m1.id, ("user", "Ik maak X."))
    _seed_turns(db, m2.id, ("user", "Ik maak Y."))
    assert mm.refresh_all(db, client=FakeClient()) == 2


# --------------------------------------------------------------------------- #
# Prompt-injectie in de stream-system                                          #
# --------------------------------------------------------------------------- #


def test_stream_injects_memory_into_system(db, make_member, monkeypatch):
    from tests.test_concierge import FakeAnthropicLoop

    fake = FakeAnthropicLoop(
        [{"deltas": ["Hoi."], "stop_reason": "end_turn",
          "content": [{"type": "text", "text": "Hoi."}]}]
    )
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **k: fake)

    concierge_service.stream_concierge(
        [{"role": "user", "content": "hallo"}],
        lambda _t: None,
        db=db,
        member_memory="- bouwt voice-agents",
    )
    system = fake.stream_kwargs[0]["system"]
    assert "voice-agents" in system


def test_stream_without_memory_is_base_prompt(db, monkeypatch):
    from tests.test_concierge import FakeAnthropicLoop

    fake = FakeAnthropicLoop(
        [{"deltas": ["Hoi."], "stop_reason": "end_turn",
          "content": [{"type": "text", "text": "Hoi."}]}]
    )
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **k: fake)

    concierge_service.stream_concierge(
        [{"role": "user", "content": "hallo"}], lambda _t: None, db=db
    )
    assert fake.stream_kwargs[0]["system"] == concierge_service.SYSTEM_PROMPT


# --------------------------------------------------------------------------- #
# AVG: clear_turns wist het geheugen mee                                       #
# --------------------------------------------------------------------------- #


def test_clear_turns_wipes_memory(db, make_member):
    member = make_member(email="h@x.nl", name="H")
    db.flush()
    _seed_turns(db, member.id, ("user", "Ik bouw agents."))
    mm.distill_member(db, member, client=FakeClient())
    assert member.member_memory is not None

    concierge_state.clear_turns(db, member.id)
    db.flush()
    refreshed = db.get(Member, member.id)
    assert refreshed.member_memory is None
    assert refreshed.memory_synced_turn_id is None


def test_clear_resets_memory(db, make_member):
    member = make_member(email="i@x.nl", name="I")
    db.flush()
    _seed_turns(db, member.id, ("user", "Ik maak iets."))
    mm.distill_member(db, member, client=FakeClient())
    mm.clear(db, member.id)
    assert member.member_memory is None
    assert member.memory_synced_turn_id is None
