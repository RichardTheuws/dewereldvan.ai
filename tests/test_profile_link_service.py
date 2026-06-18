"""Tests voor ``profile_link_service`` — volledige CRUD voor rollen/affiliaties.

Backend-team (SPEC §A.3 + §E). De rol-kaarten (ProfileLink kind=affiliation) op de
levende profielvorm krijgen voor het eerst een eigen add/update/remove-service.
Geborgd gedrag:

- ``add``    : zet kind=affiliation, position oplopend, ``safe_url``-guard op urls.
- ``update`` : patcht alleen meegegeven velden, eigendoms-check (vreemd id → None),
  weigert ``javascript:``-urls, negeert leeg label (NOT NULL).
- ``remove`` : verwijdert iff eigenaar, eigendoms-check (vreemd id → False).

SQLite in-memory via de gedeelde ``db``-fixture; geen Postgres, geen API-key.
"""

from __future__ import annotations

from app.models import ProfileLinkKind
from app.services import profile_link_service


def test_add_creates_affiliation_with_position(db, make_member, make_profile):
    member = make_member()
    profile = make_profile(member)

    first = profile_link_service.add(
        db, profile, label="CTO bij Acme", url="https://acme.nl"
    )
    second = profile_link_service.add(db, profile, label="Adviseur")

    assert first.kind is ProfileLinkKind.affiliation
    assert first.position == 0
    assert second.position == 1
    assert first.url == "https://acme.nl"
    assert {link.label for link in profile.profile_links} == {"CTO bij Acme", "Adviseur"}


def test_add_rejects_dangerous_url(db, make_member, make_profile):
    member = make_member()
    profile = make_profile(member)
    link = profile_link_service.add(
        db, profile, label="Rol", url="javascript:alert(1)", image_url="data:x"
    )
    assert link.url is None
    assert link.image_url is None


def test_update_patches_only_given_fields(db, make_member, make_profile):
    member = make_member()
    profile = make_profile(member)
    link = profile_link_service.add(
        db, profile, label="Oud", url="https://oud.nl", description="oude desc"
    )

    result = profile_link_service.update(
        db, profile, link.id, label="Nieuw", url="https://nieuw.nl"
    )
    assert result is not None
    assert result.label == "Nieuw"
    assert result.url == "https://nieuw.nl"
    # description niet meegegeven → ongewijzigd.
    assert result.description == "oude desc"


def test_update_rejects_dangerous_url(db, make_member, make_profile):
    member = make_member()
    profile = make_profile(member)
    link = profile_link_service.add(db, profile, label="Rol", url="https://ok.nl")
    result = profile_link_service.update(db, profile, link.id, url="javascript:evil()")
    assert result is not None
    assert result.url is None


def test_update_empty_label_is_ignored(db, make_member, make_profile):
    member = make_member()
    profile = make_profile(member)
    link = profile_link_service.add(db, profile, label="Behoud mij")
    result = profile_link_service.update(db, profile, link.id, label="   ")
    assert result is not None
    assert result.label == "Behoud mij"  # NOT NULL → leeg label genegeerd


def test_update_foreign_id_returns_none(db, make_member, make_profile):
    owner = make_member(email="owner@example.com")
    owner_profile = make_profile(owner, display_name="Owner")
    intruder = make_member(email="intruder@example.com")
    intruder_profile = make_profile(intruder, display_name="Intruder")
    link = profile_link_service.add(db, owner_profile, label="Van owner")

    assert profile_link_service.update(
        db, intruder_profile, link.id, label="hack"
    ) is None
    assert link.label == "Van owner"


def test_update_missing_id_returns_none(db, make_member, make_profile):
    member = make_member()
    profile = make_profile(member)
    assert profile_link_service.update(db, profile, 999999, label="x") is None


def test_remove_deletes_own_link(db, make_member, make_profile):
    member = make_member()
    profile = make_profile(member)
    link = profile_link_service.add(db, profile, label="Weg ermee")
    assert profile_link_service.remove(db, profile, link.id) is True
    assert profile.profile_links == []


def test_remove_foreign_id_returns_false(db, make_member, make_profile):
    owner = make_member(email="owner@example.com")
    owner_profile = make_profile(owner, display_name="Owner")
    intruder = make_member(email="intruder@example.com")
    intruder_profile = make_profile(intruder, display_name="Intruder")
    link = profile_link_service.add(db, owner_profile, label="Van owner")

    assert profile_link_service.remove(db, intruder_profile, link.id) is False
    assert len(owner_profile.profile_links) == 1


def test_remove_missing_id_returns_false(db, make_member, make_profile):
    member = make_member()
    profile = make_profile(member)
    assert profile_link_service.remove(db, profile, 424242) is False
