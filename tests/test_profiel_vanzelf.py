"""PRD-profiel-vanzelf: snelle presence-ronde, concept-profiel, auto-koppelen op de
server en de publiceerkaart. Geen netwerk: de fake Anthropic uit de footprint-tests.
"""

from __future__ import annotations

import json

from app.models import Member, Offering, Post, PostKind, ProfileLinkKind, Visibility
from app.services import (
    discovery_job_service,
    footprint_service,
    profile_concept_service,
    profile_service,
)

from tests import test_footprint_discovery as _fd

# Gedeelde helpers + fixtures van de footprint-tests (zelfde test-DB-opzet).
FakeAnthropic = _fd.FakeAnthropic
_Block = _fd._Block
_csrf = _fd._csrf
_findings_block = _fd._findings_block
route_engine = _fd.route_engine
SessionTest = _fd.SessionTest
approved_id = _fd.approved_id
make_client = _fd.make_client


def _presence_block(findings, profile):
    return _Block(
        type="tool_use", name="record_presence", id="p1",
        input={"findings": findings, "profile": profile},
    )


_CONCEPT = {
    "headline": "CTO bij HeleCloud",
    "bio": "Ik bouw cloudplatforms en help teams met AI in productie.",
    "roles": [{"label": "CTO · HeleCloud", "url": "https://helecloud.example"}],
    "is_organisation": False,
    "confidence": 92,
}


def _concept(**over):
    raw = {**_CONCEPT, **over}
    return footprint_service._sanitize_concept(raw)


# --------------------------------------------------------------------------- #
# Domein-hint                                                                 #
# --------------------------------------------------------------------------- #


def test_email_domain_hint_skips_generic_providers():
    assert footprint_service.email_domain_hint("walter@helecloud.com") == "helecloud.com"
    assert footprint_service.email_domain_hint("Jan@GMAIL.com") is None
    assert footprint_service.email_domain_hint("x@outlook.nl") is None
    assert footprint_service.email_domain_hint("geen-adres") is None
    assert footprint_service.email_domain_hint(None) is None


def test_presence_prompt_carries_domain_and_caps_tools(db, make_member, make_profile, monkeypatch):
    monkeypatch.setattr(footprint_service.settings, "ai_enrich_enabled", True)
    member = make_member(name="Walter Heck", email="walter@helecloud.com")
    profile = make_profile(member, display_name="Walter Heck")
    fake = FakeAnthropic([{"stop_reason": "end_turn",
                           "content": [_presence_block([], _CONCEPT)]}])

    findings, concept = footprint_service.discover_presence(profile, lambda e, d: None, client=fake)

    kwargs = fake.stream_kwargs[0]
    prompt = kwargs["messages"][0]["content"]
    assert "helecloud.com" in prompt
    assert "Geen ankers bekend" not in prompt
    tools = {t["name"]: t for t in kwargs["tools"]}
    assert tools["web_search"]["max_uses"] == 3
    assert tools["web_search"]["type"] == "web_search_20250305"  # snel, gemeten
    assert kwargs["extra_body"] == {"output_config": {"effort": "low"}}
    assert "record_presence" in tools
    assert concept is not None and concept.headline == "CTO bij HeleCloud"


def test_presence_gmail_gives_no_domain_hint(db, make_member, make_profile, monkeypatch):
    monkeypatch.setattr(footprint_service.settings, "ai_enrich_enabled", True)
    member = make_member(name="Jessica", email="jessica@gmail.com")
    profile = make_profile(member, display_name="Jessica")
    fake = FakeAnthropic([{"stop_reason": "end_turn",
                           "content": [_presence_block([], _CONCEPT)]}])
    footprint_service.discover_presence(profile, lambda e, d: None, client=fake)
    assert "gmail.com" not in fake.stream_kwargs[0]["messages"][0]["content"]


def test_presence_failure_returns_nothing(db, make_member, make_profile, monkeypatch):
    monkeypatch.setattr(footprint_service.settings, "ai_enrich_enabled", True)
    member = make_member(name="Fout")
    profile = make_profile(member, display_name="Fout")

    class Boom:
        class messages:  # noqa: N801
            @staticmethod
            def stream(**kw):
                raise RuntimeError("api down")

    result = footprint_service.discover_presence(profile, lambda e, d: None, client=Boom)
    assert result == ([], None)


def test_presence_off_when_ai_disabled(db, make_member, make_profile, monkeypatch):
    monkeypatch.setattr(footprint_service.settings, "ai_enrich_enabled", False)
    member = make_member(name="Uit")
    profile = make_profile(member, display_name="Uit")
    assert footprint_service.discover_presence(profile, lambda e, d: None) == ([], None)


# --------------------------------------------------------------------------- #
# Concept: alleen lege velden, alleen bij genoeg zekerheid                    #
# --------------------------------------------------------------------------- #


def test_concept_fills_empty_fields(db, make_member, make_profile):
    member = make_member(name="Walter")
    profile = make_profile(member, display_name="Walter")
    profile.visibility = Visibility.members
    db.flush()

    filled = profile_concept_service.apply_concept(db, profile, _concept())

    assert filled == ["headline", "bio", "roles"]
    assert profile.headline == "CTO bij HeleCloud"
    assert profile.bio.startswith("Ik bouw")
    roles = [link for link in profile.profile_links if link.kind is ProfileLinkKind.affiliation]
    assert [(r.label, r.url) for r in roles] == [("CTO · HeleCloud", "https://helecloud.example")]
    assert profile.ai_enriched is True
    assert profile.visibility == Visibility.members  # nooit vanzelf openbaar
    assert profile_concept_service.has_content(profile)


def test_concept_never_overwrites(db, make_member, make_profile):
    member = make_member(name="Robin")
    profile = make_profile(member, display_name="Robin")
    profile.headline = "Mijn eigen kopregel"
    profile.bio = "Mijn eigen bio."
    db.flush()

    filled = profile_concept_service.apply_concept(db, profile, _concept())

    assert filled == ["roles"]
    assert profile.headline == "Mijn eigen kopregel"
    assert profile.bio == "Mijn eigen bio."


def test_concept_below_threshold_fills_nothing(db, make_member, make_profile):
    member = make_member(name="Naamgenoot")
    profile = make_profile(member, display_name="Naamgenoot")

    assert profile_concept_service.apply_concept(db, profile, _concept(confidence=84)) == []
    assert profile.headline is None and profile.bio is None
    assert profile_concept_service.apply_concept(db, profile, None) == []


def test_concept_sanitizer_drops_unsafe_role_urls():
    c = _concept(roles=[{"label": "A", "url": "javascript:alert(1)"}, {"label": ""},
                        {"label": "B"}, {"label": "C"}, {"label": "D"}])
    assert c.roles == (("A", None), ("B", None), ("C", None))
    empty = {"headline": "", "bio": "", "confidence": 99}
    assert footprint_service._sanitize_concept(empty) is None


# --------------------------------------------------------------------------- #
# Run: presence → concept + auto-koppelen op de server, ook zonder browser     #
# --------------------------------------------------------------------------- #


def _seed_running(SessionTest, member_id):
    from app.models import DiscoveryRun

    with SessionTest() as s:
        s.add(DiscoveryRun(member_id=member_id, status="running"))
        s.commit()


def test_chain_fills_concept_and_crystallizes_without_browser(
    SessionTest, approved_id, monkeypatch
):
    monkeypatch.setattr(footprint_service.settings, "ai_enrich_enabled", True)
    _seed_running(SessionTest, approved_id)
    fake = FakeAnthropic([
        # 1. presence-ronde: LinkedIn (presence) + concept
        {"stop_reason": "end_turn", "content": [_presence_block(
            [{"title": "LinkedIn", "url": "https://linkedin.example/in/o",
              "type": "presence", "confidence": 97, "why": "eigen profiel"}],
            _CONCEPT,
        )]},
        # 2. brede ronde: zeker project + zekere talk + twijfel-media
        {"stop_reason": "end_turn", "content": [_findings_block([
            {"title": "Eigen tool", "url": "https://tool.example", "type": "project",
             "confidence": 95, "why": "x"},
            {"title": "Keynote", "url": "https://talk.example", "type": "talk",
             "confidence": 91, "why": "y"},
            {"title": "Misschien", "url": "https://maybe.example", "type": "media",
             "confidence": 70, "why": "z"},
        ])]},
    ])

    discovery_job_service.run_chain(approved_id, session_factory=SessionTest, client=fake)

    with SessionTest() as s:
        run = discovery_job_service.get_run(s, approved_id)
        assert run.status == "done"
        assert discovery_job_service.passes_of(run) == {"presence", "broad"}
        assert len(discovery_job_service.findings_of(run)) == 4
        member = s.get(Member, approved_id)
        profile = member.profile
        assert profile.headline == "CTO bij HeleCloud"
        assert profile.visibility == Visibility.members
        assert [o.url for o in profile.offerings] == ["https://tool.example"]
        news = s.query(Post).filter(Post.kind == PostKind.nieuws).all()
        assert [p.url for p in news] == ["https://talk.example"]  # presence + twijfel niet


def test_presence_pass_keeps_run_running(SessionTest, approved_id, monkeypatch):
    """Na de snelle ronde blijft de run lopen (de tail toont al wel het concept)."""
    monkeypatch.setattr(footprint_service.settings, "ai_enrich_enabled", True)
    _seed_running(SessionTest, approved_id)
    fake = FakeAnthropic([{"stop_reason": "end_turn",
                           "content": [_presence_block([], _CONCEPT)]}])
    discovery_job_service.run_job(
        approved_id, session_factory=SessionTest, client=fake,
        focus="presence", final=False,
    )
    with SessionTest() as s:
        run = discovery_job_service.get_run(s, approved_id)
        assert run.status == "running"
        assert "presence" in discovery_job_service.passes_of(run)
        assert s.get(Member, approved_id).profile.bio


def test_server_and_browser_crystallize_stay_idempotent(
    make_client, SessionTest, approved_id, monkeypatch
):
    """De kaart in de browser POST't nog steeds; dat geeft geen dubbel werk-item."""
    monkeypatch.setattr(footprint_service.settings, "ai_enrich_enabled", True)
    _seed_running(SessionTest, approved_id)
    fake = FakeAnthropic([{"stop_reason": "end_turn", "content": [_findings_block([
        {"title": "Eigen tool", "url": "https://tool.example", "type": "project",
         "confidence": 95, "why": "x"},
    ])]}])
    discovery_job_service.run_job(approved_id, session_factory=SessionTest, client=fake)

    client = make_client(approved_id)
    token = _csrf(client)
    resp = client.post(
        "/profiel/ai/ontdek/crystalliseer",
        data={"title": "Eigen tool", "url": "https://tool.example", "type": "project",
              "confidence": "95"},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    with SessionTest() as s:
        assert s.query(Offering).filter(Offering.url == "https://tool.example").count() == 1


def test_start_fresh_broad_runs_chain(SessionTest, approved_id, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(discovery_job_service, "run_chain", lambda mid, **k: calls.append("chain"))
    monkeypatch.setattr(discovery_job_service, "run_job", lambda mid, **k: calls.append(k["focus"]))

    class _SyncThread:
        def __init__(self, target, args, kwargs, **_):
            self._t, self._a, self._k = target, args, kwargs

        def start(self):
            self._t(*self._a, **self._k)

    monkeypatch.setattr(discovery_job_service.threading, "Thread", _SyncThread)
    with SessionTest() as s:
        member = s.get(Member, approved_id)
        discovery_job_service.start(s, member)
        discovery_job_service.start(s, member, focus="media", append=True)
    assert calls == ["chain", "media"]
    assert approved_id not in discovery_job_service._inflight


# --------------------------------------------------------------------------- #
# Bouwpagina: hoofdknop, publiceerkaart, autostart                            #
# --------------------------------------------------------------------------- #


def test_build_page_leads_with_search_button(make_client, approved_id):
    resp = make_client(approved_id).get("/profiel/ai/bouwen")
    assert resp.status_code == 200
    text = resp.text
    assert "Zoek mij op en bouw mijn profiel" in text
    assert text.index("Zoek mij op en bouw mijn profiel") < text.index("Of vertel het zelf")
    assert "Je profiel staat klaar" not in text  # leeg profiel → geen kaart


def test_ready_card_only_with_content_and_not_public(make_client, SessionTest, approved_id):
    client = make_client(approved_id)
    assert "Je profiel staat klaar" not in client.get("/profiel/ai/klaar").text

    with SessionTest() as s:
        member = s.get(Member, approved_id)
        profile = profile_service.get_or_create_profile(s, member)
        profile.headline = "Bouwt met AI"
        s.commit()
    assert "Openbaar zetten" in client.get("/profiel/ai/klaar").text
    assert "Je profiel staat klaar" in client.get("/profiel/ai/bouwen").text


def test_ready_card_button_publishes_with_consent(make_client, SessionTest, approved_id):
    with SessionTest() as s:
        profile = profile_service.get_or_create_profile(s, s.get(Member, approved_id))
        profile.bio = "Ik maak dingen."
        s.commit()
    client = make_client(approved_id)
    token = _csrf(client)
    resp = client.post(
        "/profiel/ai/publiceren",
        data={"visibility": "public", "consent": "on"},
        headers={"X-CSRF-Token": token, "HX-Request": "true"},
    )
    assert resp.status_code == 204 and resp.headers["HX-Redirect"].startswith("/leden/")
    with SessionTest() as s:
        profile = s.get(Member, approved_id).profile
        assert profile.visibility == Visibility.public
        assert profile.consented_public_at is not None
    assert "Je profiel staat klaar" not in client.get("/profiel/ai/klaar").text


def test_autostart_only_from_welcome_and_without_run(
    make_client, SessionTest, approved_id, monkeypatch
):
    monkeypatch.setattr(footprint_service.settings, "ai_enrich_enabled", True)
    client = make_client(approved_id)
    assert 'hx-trigger="submit, load"' in client.get("/profiel/ai/bouwen?zoek=1").text
    assert 'hx-trigger="submit"' in client.get("/profiel/ai/bouwen").text

    from app.models import DiscoveryRun

    with SessionTest() as s:
        s.add(DiscoveryRun(member_id=approved_id, status="done", findings_json=json.dumps([])))
        s.commit()
    assert "submit, load" not in client.get("/profiel/ai/bouwen?zoek=1").text


def test_live_form_fragment_renders(make_client, approved_id):
    resp = make_client(approved_id).get("/profiel/ai/vorm")
    assert resp.status_code == 200
    assert 'id="profielvorm"' in resp.text


def test_new_fragments_require_login(make_client):
    client = make_client(None)
    for path in ("/profiel/ai/vorm", "/profiel/ai/klaar"):
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code in (302, 303), path


def test_welcome_offers_search_start(make_client, approved_id):
    resp = make_client(approved_id).get("/welkom")
    assert resp.status_code == 200
    assert "/profiel/ai/bouwen?zoek=1" in resp.text
