"""Backend-tests voor de Concierge (Fase 1).

Dekt: de tool-loop (happy + tool_use→result), grounding (verzonnen slug → geen
kaart), lege resultaten, refusal, AVG-poort (besloten lekt niet), nudge-selectie
+ dismiss-persist, founder-naam-match, en de SDK-contract-guards (geen
temperature/top_p/budget_tokens; thinking=adaptive).

Geen netwerk, geen API-key: ``anthropic.Anthropic`` wordt vervangen door een
in-memory fake die een gescript tool-use→end_turn-scenario afspeelt.
"""

from __future__ import annotations

import json

import anthropic
import pytest
from app.models import MemberStatus, Visibility
from app.services import (
    concierge_service,
    nudge_service,
    profile_service,
    registration,
)

# --------------------------------------------------------------------------- #
# Fake Anthropic met een echte tool_use-loop                                  #
# --------------------------------------------------------------------------- #


class _Block:
    """Minimaal content-blok met dict-achtige .type/.name/.input/.id velden."""

    def __init__(self, **kw):
        self.__dict__.update(kw)

    def model_dump(self):
        return dict(self.__dict__)


class _FakeMsg:
    def __init__(self, stop_reason, content):
        self.stop_reason = stop_reason
        self.content = content


class _FakeStream:
    def __init__(self, owner):
        self._owner = owner

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    @property
    def text_stream(self):
        step = self._owner.script[self._owner.call_idx]
        return iter(step.get("deltas", []))

    def get_final_message(self):
        owner = self._owner
        step = owner.script[owner.call_idx]
        owner.call_idx += 1
        return _FakeMsg(step["stop_reason"], step["content"])


class _FakeMessages:
    def __init__(self, owner):
        self._owner = owner

    def stream(self, **kwargs):
        self._owner.stream_kwargs.append(kwargs)
        return _FakeStream(self._owner)


class FakeAnthropicLoop:
    """Speelt een lijst van ronde-stappen af.

    Elke stap: ``{"deltas": [...], "stop_reason": "tool_use"|"end_turn"|"refusal",
    "content": [...blocks...]}``. Eén stap per ``stream(...)``-call.
    """

    def __init__(self, script):
        self.script = script
        self.call_idx = 0
        self.stream_kwargs: list[dict] = []
        self.messages = _FakeMessages(self)


@pytest.fixture
def install_loop(monkeypatch):
    def _install(script):
        fake = FakeAnthropicLoop(script)
        monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **k: fake)
        return fake

    return _install


def _drain(db, messages, *, viewer=None):
    """Draai de loop, verzamel deltas + card-slugs + tool-events."""
    deltas: list[str] = []
    cards: list[str] = []
    events: list[dict] = []
    final = concierge_service.stream_concierge(
        messages,
        deltas.append,
        db=db,
        viewer=viewer,
        on_card=cards.append,
        on_tool_event=events.append,
    )
    return final, deltas, cards, events


def _drain_nav(db, messages, *, viewer=None):
    """Draai de loop en vang de navigate-signalen (on_navigate)."""
    navs: list[str] = []
    cards: list = []
    final = concierge_service.stream_concierge(
        messages,
        lambda _t: None,
        db=db,
        viewer=viewer,
        on_card=cards.append,
        on_navigate=navs.append,
    )
    return final, navs, cards


# --------------------------------------------------------------------------- #
# Tool-loop: happy path met search_members → kaart + tool_result              #
# --------------------------------------------------------------------------- #


def _public_member_with_tag(db, make_member, make_profile, *, name, tag, email):
    member = make_member(email=email, name=name)
    profile = make_profile(member, display_name=name, visibility=Visibility.public)
    profile_service.set_tags(db, profile, tag)
    db.flush()
    return member, profile


def test_tool_loop_search_then_text(db, make_member, make_profile, install_loop):
    _public_member_with_tag(
        db, make_member, make_profile,
        name="Sanne", tag="voice-agents", email="sanne@x.nl",
    )
    tool_use = _Block(
        type="tool_use", id="t1", name="search_members",
        input={"tag": "voice-agents"},
    )
    fake = install_loop([
        {"deltas": [], "stop_reason": "tool_use", "content": [tool_use]},
        {"deltas": ["Eén ", "maker."], "stop_reason": "end_turn",
         "content": [{"type": "text", "text": "Eén maker."}]},
    ])

    final, deltas, cards, events = _drain(db, [{"role": "user", "content": "wie"}])

    assert getattr(final, "stop_reason", None) == "end_turn"
    assert "".join(deltas) == "Eén maker."
    # Grounding: de echte slug komt als kaart-signaal terug.
    assert cards == ["sanne"]
    assert any(e.get("count") == 1 for e in events)
    # Twee stream-calls (tool-ronde + tekst-ronde).
    assert fake.call_idx == 2
    # SDK-contract: thinking=adaptive, geen verboden params.
    for kw in fake.stream_kwargs:
        assert kw["thinking"] == {"type": "adaptive"}
        assert "temperature" not in kw
        assert "top_p" not in kw
        assert "top_k" not in kw
        assert "budget_tokens" not in kw


def test_tool_result_is_fed_back(db, make_member, make_profile, install_loop):
    """De tweede stream-call ziet het assistant tool_use + user tool_result."""
    _public_member_with_tag(
        db, make_member, make_profile,
        name="Mark", tag="beleid", email="mark@x.nl",
    )
    tool_use = _Block(
        type="tool_use", id="tt", name="search_members", input={"tag": "beleid"}
    )
    fake = install_loop([
        {"deltas": [], "stop_reason": "tool_use", "content": [tool_use]},
        {"deltas": ["ok"], "stop_reason": "end_turn",
         "content": [{"type": "text", "text": "ok"}]},
    ])
    _drain(db, [{"role": "user", "content": "wie"}])

    second = fake.stream_kwargs[1]["messages"]
    # laatste twee berichten: assistant(tool_use) + user(tool_result)
    assert second[-2]["role"] == "assistant"
    assert second[-1]["role"] == "user"
    tr = second[-1]["content"][0]
    assert tr["type"] == "tool_result"
    assert tr["tool_use_id"] == "tt"
    payload = json.loads(tr["content"])
    assert payload["count"] == 1
    assert payload["members"][0]["slug"] == "mark"


# --------------------------------------------------------------------------- #
# Grounding: verzonnen slug → geen kaart                                       #
# --------------------------------------------------------------------------- #


def test_grounding_invented_slug_no_card(db):
    """connect op een niet-bestaande slug levert een error en geen kaart-slug."""
    result, slugs = concierge_service.run_tool(
        db, "connect", {"slug": "verzonnen-persoon"}, viewer=None
    )
    assert "error" in result
    assert slugs == []


def test_render_card_by_slug_gate(db, make_member, make_profile):
    """_public_profile_by_slug geeft None voor een onbekende slug (render-poort)."""
    assert concierge_service._public_profile_by_slug(db, "bestaat-niet") is None


# --------------------------------------------------------------------------- #
# Lege resultaten                                                              #
# --------------------------------------------------------------------------- #


def test_search_empty_results(db):
    result, slugs = concierge_service.run_tool(
        db, "search_members", {"tag": "niets-matcht-dit"}, viewer=None
    )
    assert result["count"] == 0
    assert result["members"] == []
    assert slugs == []


def test_search_requires_filter(db):
    result, slugs = concierge_service.run_tool(
        db, "search_members", {}, viewer=None
    )
    assert "error" in result
    assert slugs == []


# --------------------------------------------------------------------------- #
# Refusal                                                                      #
# --------------------------------------------------------------------------- #


def test_refusal_returns_without_reading_content(db, install_loop):
    install_loop([
        {"deltas": [], "stop_reason": "refusal", "content": []},
    ])
    final, deltas, cards, events = _drain(db, [{"role": "user", "content": "x"}])
    assert concierge_service._refused(final)
    assert deltas == []
    assert cards == []


# --------------------------------------------------------------------------- #
# AVG-poort: besloten/geschorst lekt niet                                     #
# --------------------------------------------------------------------------- #


def test_avg_gate_members_only_not_surfaced(db, make_member, make_profile):
    member = make_member(email="besloten@x.nl", name="Besloten")
    profile = make_profile(
        member, display_name="Besloten", visibility=Visibility.members
    )
    profile_service.set_tags(db, profile, "geheim")
    db.flush()
    result, slugs = concierge_service.run_tool(
        db, "search_members", {"tag": "geheim"}, viewer=None
    )
    assert result["count"] == 0
    # connect mag 'm ook niet oppervlakken.
    cresult, cslugs = concierge_service.run_tool(
        db, "connect", {"slug": profile.slug}, viewer=None
    )
    assert "error" in cresult
    assert cslugs == []


def test_avg_gate_suspended_owner_not_surfaced(db, make_member, make_profile):
    member = make_member(
        email="geschorst@x.nl", name="Geschorst", status=MemberStatus.suspended
    )
    profile = make_profile(
        member, display_name="Geschorst", visibility=Visibility.public
    )
    profile_service.set_tags(db, profile, "agents")
    db.flush()
    result, _ = concierge_service.run_tool(
        db, "search_members", {"tag": "agents"}, viewer=None
    )
    assert result["count"] == 0


# --------------------------------------------------------------------------- #
# explain + navigate + my_status                                              #
# --------------------------------------------------------------------------- #


def test_explain_uses_curated_text(db):
    result, _ = concierge_service.run_tool(
        db, "explain", {"topic": "zichtbaarheid"}, viewer=None
    )
    assert "besloten" in result["text"].lower()
    bad, _ = concierge_service.run_tool(
        db, "explain", {"topic": "onbekend"}, viewer=None
    )
    assert "error" in bad


def test_navigate_route_table_and_member(db, make_member, make_profile):
    res, _ = concierge_service.run_tool(
        db, "navigate", {"target": "roadmap"}, viewer=None
    )
    assert res["url"] == "/roadmap"

    member = make_member(email="nav@x.nl", name="Nav")
    profile = make_profile(member, display_name="Nav", visibility=Visibility.public)
    db.flush()
    res2, _ = concierge_service.run_tool(
        db, "navigate", {"target": f"member:{profile.slug}"}, viewer=None
    )
    assert res2["url"] == f"/leden/{profile.slug}"

    bad, _ = concierge_service.run_tool(
        db, "navigate", {"target": "member:nope"}, viewer=None
    )
    assert "error" in bad


# --------------------------------------------------------------------------- #
# M2: navigate-intent produceert een navigate-signaal (anders navigeert het    #
#     lid NOOIT — de tool gaf de url enkel terug aan Claude).                   #
# --------------------------------------------------------------------------- #


def test_navigate_intent_emits_on_navigate(db, install_loop):
    """Een navigate-tool-call roept on_navigate aan met de interne url."""
    nav_use = _Block(
        type="tool_use", id="n1", name="navigate", input={"target": "roadmap"}
    )
    install_loop([
        {"deltas": [], "stop_reason": "tool_use", "content": [nav_use]},
        {"deltas": ["Daar."], "stop_reason": "end_turn",
         "content": [{"type": "text", "text": "Daar."}]},
    ])
    final, navs, _cards = _drain_nav(db, [{"role": "user", "content": "ga"}])
    assert getattr(final, "stop_reason", None) == "end_turn"
    assert navs == ["/roadmap"]


def test_navigate_error_does_not_emit(db, install_loop):
    """Een onbekende bestemming (error-tak) levert GEEN navigate-signaal."""
    nav_use = _Block(
        type="tool_use", id="n2", name="navigate", input={"target": "member:nope"}
    )
    install_loop([
        {"deltas": [], "stop_reason": "tool_use", "content": [nav_use]},
        {"deltas": ["ok"], "stop_reason": "end_turn",
         "content": [{"type": "text", "text": "ok"}]},
    ])
    _final, navs, _cards = _drain_nav(db, [{"role": "user", "content": "ga"}])
    assert navs == []


# --------------------------------------------------------------------------- #
# Agent-Shell Fase 1: de surface-tool emit + registratie                       #
# --------------------------------------------------------------------------- #


def test_surface_tool_emits_on_surface(db, install_loop):
    """Een surface-tool-call roept on_surface aan met {view, params} (geen render
    in de engine — grounding-poort blijft in de router)."""
    surf_use = _Block(
        type="tool_use", id="s1", name="surface",
        input={"view": "members_grid", "params": {"tag": "agents"}},
    )
    install_loop([
        {"deltas": [], "stop_reason": "tool_use", "content": [surf_use]},
        {"deltas": ["ok"], "stop_reason": "end_turn",
         "content": [{"type": "text", "text": "ok"}]},
    ])
    signals: list[dict] = []
    concierge_service.stream_concierge(
        [{"role": "user", "content": "laat de makers zien"}],
        lambda _t: None,
        db=db,
        on_surface=signals.append,
    )
    assert signals == [{"view": "members_grid", "params": {"tag": "agents"}}]


def test_draft_tool_emits_on_surface_without_writing(db, install_loop):
    """Een draft-tool SCHRIJFT NIET; hij emit een {draft, fields}-signaal via het
    surface-kanaal (de router rendert straks het voorgevulde formulier)."""
    draft_use = _Block(
        type="tool_use", id="d1", name="draft_offering",
        input={"title": "AI-tool", "description": "voor de zorg"},
    )
    install_loop([
        {"deltas": [], "stop_reason": "tool_use", "content": [draft_use]},
        {"deltas": ["ok"], "stop_reason": "end_turn",
         "content": [{"type": "text", "text": "ok"}]},
    ])
    signals: list[dict] = []
    concierge_service.stream_concierge(
        [{"role": "user", "content": "voeg een project toe"}],
        lambda _t: None,
        db=db,
        on_surface=signals.append,
    )
    assert signals == [
        {"draft": "offering", "fields": {"title": "AI-tool", "description": "voor de zorg"}}
    ]


def test_surface_tool_registered_with_contract():
    """De surface-tool is geregistreerd; het Opus-contract blijft ongewijzigd
    (geen sampling/budget-params worden door de tool-def geïntroduceerd)."""
    names = [t["name"] for t in concierge_service.TOOLS]
    assert "surface" in names
    assert concierge_service.THINKING == {"type": "adaptive"}


# --------------------------------------------------------------------------- #
# m1: connect-kaart draagt de shared_tags-"waarom" mee als kaart-signaal.       #
# --------------------------------------------------------------------------- #


def test_connect_card_signal_carries_shared_tags(db, make_member, make_profile, install_loop):
    """on_card krijgt voor connect een {slug, shared_tags}-payload (de waarom-regel)."""
    viewer = make_member(email="cv@x.nl", name="CViewer")
    vp = make_profile(viewer, display_name="CViewer", visibility=Visibility.members)
    profile_service.set_tags(db, vp, "agents, zorg")
    viewer.profile = vp
    other = make_member(email="co@x.nl", name="COther")
    op = make_profile(other, display_name="COther", visibility=Visibility.public)
    profile_service.set_tags(db, op, "agents, beleid")
    db.flush()

    conn_use = _Block(
        type="tool_use", id="c1", name="connect", input={"slug": op.slug}
    )
    install_loop([
        {"deltas": [], "stop_reason": "tool_use", "content": [conn_use]},
        {"deltas": ["ok"], "stop_reason": "end_turn",
         "content": [{"type": "text", "text": "ok"}]},
    ])
    cards: list = []
    concierge_service.stream_concierge(
        [{"role": "user", "content": "stel voor"}],
        lambda _t: None,
        db=db,
        viewer=viewer,
        on_card=cards.append,
    )
    assert len(cards) == 1
    signal = cards[0]
    assert isinstance(signal, dict)
    assert signal["slug"] == op.slug
    assert "agents" in signal["shared_tags"]
    assert "beleid" not in signal["shared_tags"]


def test_my_status_requires_member(db):
    res, _ = concierge_service.run_tool(db, "my_status", {}, viewer=None)
    assert "error" in res


def test_my_status_for_member(db, make_member, make_profile):
    member = make_member(email="status@x.nl", name="Status")
    profile = make_profile(
        member, display_name="Status", visibility=Visibility.members, bio="hoi"
    )
    member.profile = profile
    db.flush()
    res, _ = concierge_service.run_tool(db, "my_status", {}, viewer=member)
    assert "completeness_pct" in res
    assert res["visibility"] == "members"
    assert "wat je zoekt" in res["missing_fields"]


def test_connect_shared_tags(db, make_member, make_profile):
    viewer = make_member(email="viewer@x.nl", name="Viewer")
    vp = make_profile(viewer, display_name="Viewer", visibility=Visibility.members)
    profile_service.set_tags(db, vp, "agents, zorg")
    viewer.profile = vp

    other = make_member(email="other@x.nl", name="Other")
    op = make_profile(other, display_name="Other", visibility=Visibility.public)
    profile_service.set_tags(db, op, "agents, beleid")
    db.flush()

    res, slugs = concierge_service.run_tool(
        db, "connect", {"slug": op.slug}, viewer=viewer
    )
    assert res["slug"] == op.slug
    assert "agents" in res["shared_tags"]
    assert "beleid" not in res["shared_tags"]
    assert slugs == [op.slug]


# --------------------------------------------------------------------------- #
# Founder-naam-match (genormaliseerd)                                          #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Bart Ensink", True),
        ("bart ensink", True),
        ("Hendrik van Zwol", True),
        ("hendrik  van  zwol", True),
        ("Zwol Hendrik van", True),  # woordvolgorde-tolerant
        ("Iemand Anders", False),
        ("Bart", False),
    ],
)
def test_founder_name_match(name, expected):
    assert registration.is_founder_name(name) is expected


def test_register_sets_is_founder(db):
    res = registration.register_member(
        db, name="Hendrik van Zwol", email="hendrik@x.nl"
    )
    assert res.member.is_founder is True
    res2 = registration.register_member(db, name="Gewoon Lid", email="lid@x.nl")
    assert res2.member.is_founder is False


# --------------------------------------------------------------------------- #
# Nudge-selectie + dismiss-persist                                            #
# --------------------------------------------------------------------------- #


def test_nudge_tag_overlap_selected(db, make_member, make_profile):
    viewer = make_member(email="v@x.nl", name="V")
    vp = make_profile(viewer, display_name="V", visibility=Visibility.members)
    profile_service.set_tags(db, vp, "voice-agents")
    viewer.profile = vp

    other = make_member(email="o@x.nl", name="Mark")
    op = make_profile(other, display_name="Mark", visibility=Visibility.public)
    profile_service.set_tags(db, op, "voice-agents")
    db.flush()

    nudge = nudge_service.select_nudge(db, viewer)
    assert nudge is not None
    assert nudge.kind == f"tag_overlap:{op.slug}"
    assert "Mark" in nudge.message
    assert nudge.slug == op.slug


def test_nudge_dismiss_persist_silences(db, make_member, make_profile):
    viewer = make_member(email="v2@x.nl", name="V2")
    vp = make_profile(viewer, display_name="V2", visibility=Visibility.members)
    profile_service.set_tags(db, vp, "agents")
    viewer.profile = vp
    other = make_member(email="o2@x.nl", name="Other2")
    op = make_profile(other, display_name="Other2", visibility=Visibility.public)
    profile_service.set_tags(db, op, "agents")
    db.flush()

    nudge = nudge_service.select_nudge(db, viewer)
    assert nudge is not None
    nudge_service.dismiss(db, viewer, nudge.kind)
    db.flush()
    # Dezelfde sterke trigger komt nu niet meer als deze nudge terug.
    again = nudge_service.select_nudge(db, viewer)
    assert again is None or again.kind != nudge.kind


def test_nudge_dismiss_is_idempotent_single_row(db, make_member):
    from app.models import ConciergeNudgeDismissal
    from sqlalchemy import func, select

    member = make_member(email="d@x.nl", name="D")
    db.flush()
    nudge_service.dismiss(db, member, "nieuwe_makers")
    nudge_service.dismiss(db, member, "nieuwe_makers")
    db.flush()
    count = db.scalar(
        select(func.count())
        .select_from(ConciergeNudgeDismissal)
        .where(ConciergeNudgeDismissal.member_id == member.id)
    )
    assert count == 1


def test_nudge_anon_only_new_makers(db, make_member, make_profile):
    member = make_member(email="pub@x.nl", name="Pub")
    make_profile(member, display_name="Pub", visibility=Visibility.public)
    db.flush()
    nudge = nudge_service.select_nudge(db, None)
    assert nudge is not None
    assert nudge.kind == "nieuwe_makers"


def test_nudge_anon_cookie_dismiss(db, make_member, make_profile):
    member = make_member(email="pub2@x.nl", name="Pub2")
    make_profile(member, display_name="Pub2", visibility=Visibility.public)
    db.flush()
    nudge = nudge_service.select_nudge(
        db, None, dismissed_cookie_kinds={"nieuwe_makers"}
    )
    assert nudge is None


def test_nudge_profiel_bijna_af(db, make_member, make_profile):
    member = make_member(email="bijna@x.nl", name="Bijna")
    profile = make_profile(
        member, display_name="Bijna", visibility=Visibility.members,
        bio="een bio", makes_summary="ik maak agents",
    )
    profile_service.set_tags(db, profile, "agents")
    profile_service.add_offering(db, profile, title="Project", description=None)
    member.profile = profile
    profile_service.recompute_completeness(profile)
    db.flush()
    # 25+15+25+15 = 80 (geen need) → ≥70, <100, "wat je zoekt" ontbreekt.
    assert 70 <= profile.completeness < 100
    nudge = nudge_service.select_nudge(db, member)
    assert nudge is not None
    assert nudge.kind == "profiel_bijna_af"
    assert "zoekt" in nudge.message
