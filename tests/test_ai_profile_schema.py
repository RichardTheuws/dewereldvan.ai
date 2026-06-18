"""Structured-output schema + hallucinatie-guard for AI-native profielbouw (F1).

Everything here is pure mapping or a fully-mocked ``messages.parse`` call: no
Anthropic client is ever constructed, so no API key and no network is needed.

Covers (bouwcontract §3b/§3d):
- ``PROFILE_SCHEMA`` is a valid, strict JSON-schema (every object has
  ``additionalProperties: false`` and lists all its props in ``required``).
- ``_to_draft`` maps the Pydantic output to a ``DraftProfile`` and applies the
  hallucinatie-guard: empty strings -> ``None``, roles without ``label`` /
  projects without ``name`` are dropped.
- ``finalize_draft`` over a mocked ``messages.parse`` yields a correct draft.
- The refusal path raises ``EnrichmentRefused`` (no blind ``content`` read).
"""

from __future__ import annotations

import pytest
from app.schemas.ai_profile import DraftProfileOut, DraftProject, DraftRole
from app.services.ai_profile import (
    MAX_PAUSE_TURNS,
    PROFILE_SCHEMA,
    DraftProfile,
    EnrichmentRefused,
    _to_draft,
    finalize_draft,
    stream_turn,
)

from tests._ai_helpers import FakeAnthropic, install_fake_anthropic


# --- PROFILE_SCHEMA shape ------------------------------------------------------
def _assert_strict_object(node: dict) -> None:
    """Recursively assert every object node is strict + required-complete."""
    if node.get("type") == "object":
        assert node.get("additionalProperties") is False, node
        props = set(node.get("properties", {}))
        required = set(node.get("required", []))
        # Anthropic strict mode: every defined property must be required.
        assert props == required, (props, required)
        for child in node.get("properties", {}).values():
            _assert_strict_object(child)
    elif node.get("type") == "array":
        _assert_strict_object(node["items"])


def test_profile_schema_is_strict_and_required_complete():
    assert PROFILE_SCHEMA["type"] == "object"
    _assert_strict_object(PROFILE_SCHEMA)
    # Top-level fields the service/route depend on.
    assert set(PROFILE_SCHEMA["required"]) == {
        "headline",
        "bio",
        "roles",
        "projects",
        "seeking",
        "tags",
    }


def test_profile_schema_role_and_project_items_strict():
    role = PROFILE_SCHEMA["properties"]["roles"]["items"]
    assert set(role["required"]) == {"label", "url", "description", "image_url"}
    project = PROFILE_SCHEMA["properties"]["projects"]["items"]
    assert set(project["required"]) == {"name", "url", "description", "image_url"}


# --- _to_draft hallucinatie-guard ----------------------------------------------
def test_to_draft_blank_strings_become_none():
    parsed = DraftProfileOut(
        headline="Maker & onderzoeker",
        bio="Ik bouw dingen.",
        roles=[DraftRole(label="Oprichter", url="", description="", image_url="")],
        projects=[DraftProject(name="dewereldvan.ai", url="", description="x", image_url="")],
        seeking="",
        tags=["AI", "  ", "zorg"],
    )
    draft = _to_draft(parsed)
    assert isinstance(draft, DraftProfile)
    assert draft.headline == "Maker & onderzoeker"
    assert draft.seeking is None  # "" -> None
    # Empty url/description/image_url collapsed to None.
    assert draft.roles[0].url is None
    assert draft.roles[0].image_url is None
    assert draft.projects[0].url is None
    assert draft.projects[0].description == "x"
    # Whitespace-only tag dropped.
    assert draft.tags == ["AI", "zorg"]


def test_to_draft_drops_roles_without_label_and_projects_without_name():
    parsed = DraftProfileOut(
        headline="H",
        bio="B",
        roles=[
            DraftRole(label="", url="https://x", description="", image_url=""),
            DraftRole(label="  ", url="", description="", image_url=""),
            DraftRole(label="Echt", url="", description="", image_url=""),
        ],
        projects=[
            DraftProject(name="", url="https://y", description="", image_url=""),
            DraftProject(name="Echt project", url="", description="", image_url=""),
        ],
        seeking="mensen",
        tags=[],
    )
    draft = _to_draft(parsed)
    assert [r.label for r in draft.roles] == ["Echt"]
    assert [p.name for p in draft.projects] == ["Echt project"]


# --- finalize_draft over a mocked messages.parse -------------------------------
def test_finalize_draft_maps_mocked_structured_output(monkeypatch):
    parsed = DraftProfileOut(
        headline="Bouwer",
        bio="Korte bio.",
        roles=[DraftRole(label="CTO", url="https://co", description="", image_url="")],
        projects=[],
        seeking="samenwerking",
        tags=["python"],
    )
    fake = FakeAnthropic(parsed_output=parsed, parse_stop_reason="end_turn")
    with install_fake_anthropic(monkeypatch, fake):
        draft = finalize_draft([{"role": "user", "content": "ik ben CTO"}])

    assert draft.headline == "Bouwer"
    assert draft.roles[0].label == "CTO"
    assert draft.roles[0].url == "https://co"
    assert draft.seeking == "samenwerking"
    assert draft.tags == ["python"]

    # The forbidden sampling params are never sent; adaptive thinking always is.
    (kw,) = fake.parse_kwargs
    assert kw["thinking"] == {"type": "adaptive"}
    assert "temperature" not in kw
    assert "top_p" not in kw
    assert "top_k" not in kw
    assert "budget_tokens" not in kw
    # The finalize call carries no web tools (deterministic JSON step).
    assert "tools" not in kw


def test_finalize_draft_refusal_raises(monkeypatch):
    """A safety refusal on the finalize step raises, never reads content[0]."""
    fake = FakeAnthropic(parsed_output=None, parse_stop_reason="refusal")
    with install_fake_anthropic(monkeypatch, fake):  # noqa: SIM117
        with pytest.raises(EnrichmentRefused):
            finalize_draft([{"role": "user", "content": "hoi"}])


def test_finalize_draft_missing_parsed_output_raises(monkeypatch):
    """No parsed_output (e.g. max_tokens truncation) fails explicitly, no half draft."""
    fake = FakeAnthropic(parsed_output=None, parse_stop_reason="max_tokens")
    with install_fake_anthropic(monkeypatch, fake):  # noqa: SIM117
        with pytest.raises(EnrichmentRefused):
            finalize_draft([{"role": "user", "content": "hoi"}])


# --- stream_turn guards (pure service, mocked stream) --------------------------
def test_stream_turn_streams_deltas_and_returns_end_turn(monkeypatch):
    fake = FakeAnthropic(deltas=["Hoi ", "lid."], stream_stop_reasons=["end_turn"])
    sent: list[str] = []
    final = stream_turn(
        [{"role": "user", "content": "hoi"}], sent.append, client=fake
    )
    assert sent == ["Hoi ", "lid."]
    assert final.stop_reason == "end_turn"
    # No forbidden sampling params; adaptive thinking + web tools always present.
    (kw,) = fake.stream_kwargs
    assert kw["thinking"] == {"type": "adaptive"}
    assert "temperature" not in kw and "budget_tokens" not in kw
    assert [t["type"] for t in kw["tools"]] == [
        "web_search_20260209",
        "web_fetch_20260209",
    ]


def test_stream_turn_refusal_returns_without_reading_content(monkeypatch):
    """A refusal is surfaced via stop_reason; caller must not read content[0]."""
    fake = FakeAnthropic(deltas=[], stream_stop_reasons=["refusal"], assistant_content=[])
    final = stream_turn([{"role": "user", "content": "x"}], lambda _t: None, client=fake)
    assert final.stop_reason == "refusal"
    # Exactly one stream call: a refusal does not loop.
    assert fake.stream_calls == 1


def test_stream_turn_pause_turn_loops_then_ends(monkeypatch):
    """pause_turn re-sends assistant content (no extra user msg) until end_turn."""
    fake = FakeAnthropic(
        deltas=["deel"],
        stream_stop_reasons=["pause_turn", "pause_turn", "end_turn"],
    )
    final = stream_turn([{"role": "user", "content": "zoek dit op"}], lambda _t: None, client=fake)
    assert final.stop_reason == "end_turn"
    # 2 pauses + 1 final = 3 stream invocations.
    assert fake.stream_calls == 3


def test_stream_turn_pause_turn_cap_is_enforced(monkeypatch):
    """Endless pause_turn is capped at MAX_PAUSE_TURNS (cost/abuse guard)."""
    fake = FakeAnthropic(
        deltas=[],
        stream_stop_reasons=["pause_turn"],  # always pause -> hits the cap
    )
    final = stream_turn([{"role": "user", "content": "loop"}], lambda _t: None, client=fake)
    assert final.stop_reason == "pause_turn"
    # The first call + MAX_PAUSE_TURNS retries, then the cap stops the loop.
    assert fake.stream_calls == MAX_PAUSE_TURNS + 1


def test_stream_turn_does_not_mutate_input_messages(monkeypatch):
    fake = FakeAnthropic(stream_stop_reasons=["pause_turn", "end_turn"])
    messages = [{"role": "user", "content": "hoi"}]
    stream_turn(messages, lambda _t: None, client=fake)
    assert messages == [{"role": "user", "content": "hoi"}]

