"""Scene-gids (PRD maker-podium, fase 1).

Dekt: (1) de publieke gids-pagina rendert met kopieerbare prompt-kaarten,
(2) de ``scene_gids``-nudge verschijnt voor een lid mét werk-item en zónder
hero-video — en verdwijnt bij een video of na dismiss, (3) de hero-studio
linkt naar de gids.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.models import Visibility
from app.services import nudge_service


# --------------------------------------------------------------------------- #
# Gids-pagina                                                                  #
# --------------------------------------------------------------------------- #


def _client() -> TestClient:
    from app.main import app

    return TestClient(app, base_url="https://testserver")


def test_scene_gids_publiek_leesbaar_met_promptkaarten():
    resp = _client().get("/gids/scene")
    assert resp.status_code == 200
    body = resp.text
    assert "Maak je eigen scene" in body
    # De twee kern-prompts + kopieer-affordance staan erin.
    assert 'id="prompt-beeld"' in body
    assert 'id="prompt-video"' in body
    assert body.count("data-copy=") >= 3
    assert "data-reveal-scroll" in body


def test_scene_gids_toont_registerlink_voor_anoniem():
    body = _client().get("/gids/scene").text
    assert "/register" in body


# --------------------------------------------------------------------------- #
# Nudge-selectie                                                               #
# --------------------------------------------------------------------------- #


@pytest.fixture
def lid_met_werk(db, make_member, make_profile, make_offering):
    """Approved lid met een profiel + één werk-item, zonder tags/cover-video.

    ``members``-zichtbaarheid zodat er geen tag-overlap/nieuwe-makers-ruis is.
    """
    member = make_member(email="scene@example.com", name="Scene Maker")
    profile = make_profile(member, visibility=Visibility.members)
    make_offering(profile, title="Mijn project")
    return member


def test_scene_gids_nudge_voor_lid_met_werk_zonder_video(db, lid_met_werk):
    nudge = nudge_service.select_nudge(db, lid_met_werk)
    assert nudge is not None
    assert nudge.kind == "scene_gids"
    assert nudge.action == "navigate:/gids/scene"


def test_scene_gids_nudge_verdwijnt_met_cover_video(db, lid_met_werk):
    lid_met_werk.profile.cover_video_url = "/uploads/cover-1-abc.mp4"
    db.flush()
    nudge = nudge_service.select_nudge(db, lid_met_werk)
    assert nudge is None or nudge.kind != "scene_gids"


def test_scene_gids_nudge_respecteert_dismiss(db, lid_met_werk):
    nudge_service.dismiss(db, lid_met_werk, "scene_gids")
    nudge = nudge_service.select_nudge(db, lid_met_werk)
    assert nudge is None or nudge.kind != "scene_gids"


def test_scene_gids_nudge_niet_zonder_werk(db, make_member, make_profile):
    member = make_member(email="leeg@example.com", name="Leeg Lid")
    make_profile(member, visibility=Visibility.members)
    nudge = nudge_service.select_nudge(db, member)
    assert nudge is None or nudge.kind != "scene_gids"


# --------------------------------------------------------------------------- #
# Hero-studio verwijst naar de gids                                            #
# --------------------------------------------------------------------------- #


def test_cover_studio_template_linkt_naar_gids():
    from pathlib import Path

    tpl = Path("app/templates/ai/_cover_studio.html").read_text(encoding="utf-8")
    assert "/gids/scene" in tpl
