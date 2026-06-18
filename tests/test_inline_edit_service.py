"""Service-laag tests voor de per-veld inline-edit van de levende profielbouw.

Backend-team (SPEC §A.2/§A.4 + §E). De HTTP-route-handlers leven in
``ai_profile.py`` (kern-team-eigendom, nog te bouwen); deze suite borgt de
service-bouwstenen waarop die handlers leunen — exact het gedrag dat het
route-contract voorschrijft:

- ``update_offering`` : happy-path, titelwijziging → ``rename_to`` + 301-historie,
  ``safe_url``-guard (``javascript:`` geweigerd), eigendoms-check (vreemd id → None).
- ``persist_draft``   : verhuisde draft-persist (één bron) — mapt velden, zet nooit
  visibility, reconcilieert offerings op positie met slug-behoud.

SQLite in-memory via de gedeelde ``db``-fixture; geen Postgres, geen API-key.
"""

from __future__ import annotations

from app.models import OfferingSlugHistory
from app.services import offering_slug, profile_service


# --------------------------------------------------------------------------- #
# update_offering                                                             #
# --------------------------------------------------------------------------- #
def test_update_offering_happy_path(db, make_member, make_profile, make_offering):
    member = make_member()
    profile = make_profile(member)
    off = make_offering(profile, title="Oud project")
    offering_slug.ensure_slug(db, off)

    result = profile_service.update_offering(
        db,
        profile,
        off.id,
        description="Nieuwe omschrijving",
        url="https://voorbeeld.nl",
        image_url="https://voorbeeld.nl/og.png",
    )
    assert result is not None
    assert result.description == "Nieuwe omschrijving"
    assert result.url == "https://voorbeeld.nl"
    assert result.image_url == "https://voorbeeld.nl/og.png"


def test_update_offering_title_change_records_301_history(
    db, make_member, make_profile, make_offering
):
    member = make_member()
    profile = make_profile(member)
    off = make_offering(profile, title="Oude titel")
    offering_slug.ensure_slug(db, off)
    old_slug = off.slug
    assert old_slug == "oude-titel"

    profile_service.update_offering(db, profile, off.id, title="Nieuwe titel")
    db.flush()

    assert off.title == "Nieuwe titel"
    assert off.slug == "nieuwe-titel"
    # De oude slug is in de history-tabel vastgelegd voor de 301.
    hist = db.query(OfferingSlugHistory).filter_by(old_slug=old_slug).one_or_none()
    assert hist is not None
    assert hist.offering_id == off.id


def test_update_offering_rejects_javascript_url(
    db, make_member, make_profile, make_offering
):
    member = make_member()
    profile = make_profile(member)
    off = make_offering(profile, title="Project", url="https://ok.nl")
    offering_slug.ensure_slug(db, off)

    result = profile_service.update_offering(
        db, profile, off.id, url="javascript:alert(1)", image_url="data:text/html,x"
    )
    assert result is not None
    # Gevaarlijke schemes worden geweigerd (None), nooit opgeslagen.
    assert result.url is None
    assert result.image_url is None


def test_update_offering_empty_title_is_ignored(
    db, make_member, make_profile, make_offering
):
    member = make_member()
    profile = make_profile(member)
    off = make_offering(profile, title="Behoud mij")
    offering_slug.ensure_slug(db, off)

    result = profile_service.update_offering(db, profile, off.id, title="   ")
    assert result is not None
    assert result.title == "Behoud mij"  # NOT NULL → lege titel genegeerd


def test_update_offering_foreign_id_returns_none(
    db, make_member, make_profile, make_offering
):
    owner = make_member(email="owner@example.com")
    owner_profile = make_profile(owner, display_name="Owner")
    intruder = make_member(email="intruder@example.com")
    intruder_profile = make_profile(intruder, display_name="Intruder")
    off = make_offering(owner_profile, title="Van owner")
    offering_slug.ensure_slug(db, off)

    # Intruder probeert de offering van owner te patchen → eigendoms-check faalt.
    result = profile_service.update_offering(
        db, intruder_profile, off.id, description="hack"
    )
    assert result is None
    assert off.description != "hack"


def test_update_offering_missing_id_returns_none(db, make_member, make_profile):
    member = make_member()
    profile = make_profile(member)
    assert profile_service.update_offering(db, profile, 999999, title="x") is None


# --------------------------------------------------------------------------- #
# persist_draft (verhuisde één-bron draft-persist)                            #
# --------------------------------------------------------------------------- #
def _draft(**over):
    from app.services.ai_profile import DraftProfile, DraftProject, DraftRole

    base = dict(
        headline="CTO & maker",
        bio="Ik bouw platforms.",
        roles=[DraftRole(label="CTO", url="https://acme", description=None, image_url=None)],
        projects=[
            DraftProject(
                name="dewereldvan.ai",
                url="https://dwv",
                description="Platform",
                image_url=None,
            )
        ],
        seeking="medebouwers",
        tags=["python", "ai"],
    )
    base.update(over)
    return DraftProfile(**base)


def test_persist_draft_maps_fields_without_changing_visibility(
    db, make_member, make_profile
):
    from app.models import Visibility

    member = make_member()
    profile = make_profile(member, visibility=Visibility.members)
    messages = [{"role": "user", "content": "Ik ben CTO bij Acme."}]

    profile_service.persist_draft(db, profile, _draft(), source_messages=messages)

    assert profile.ai_enriched is True
    assert profile.headline == "CTO & maker"
    assert profile.bio == "Ik bouw platforms."
    assert profile.ai_source_text and "CTO bij Acme" in profile.ai_source_text
    assert any(link.label == "CTO" for link in profile.profile_links)
    assert any(off.title == "dewereldvan.ai" for off in profile.offerings)
    assert {t.name for t in profile.tags} == {"python", "ai"}
    assert any(n.title == "medebouwers" for n in profile.needs)
    # CRITICAL: nooit auto-publiceren.
    assert profile.visibility is Visibility.members
    assert profile.consented_public_at is None


def test_persist_draft_renamed_project_keeps_slug_history(
    db, make_member, make_profile
):
    member = make_member()
    profile = make_profile(member)
    messages = [{"role": "user", "content": "Ik bouw dingen."}]

    from app.services.ai_profile import DraftProject

    profile_service.persist_draft(
        db,
        profile,
        _draft(
            roles=[],
            projects=[
                DraftProject(
                    name="Oude Projectnaam",
                    url="https://p",
                    description="d",
                    image_url=None,
                )
            ],
            tags=[],
        ),
        source_messages=messages,
    )
    assert len(profile.offerings) == 1
    old_id = profile.offerings[0].id
    old_slug = profile.offerings[0].slug
    assert old_slug == "oude-projectnaam"

    # Regenerate met gewijzigde titel → zelfde rij + 301-historie.
    profile_service.persist_draft(
        db,
        profile,
        _draft(
            roles=[],
            projects=[
                DraftProject(
                    name="Nieuwe Projectnaam",
                    url="https://p",
                    description="d",
                    image_url=None,
                )
            ],
            tags=[],
        ),
        source_messages=messages,
    )
    assert len(profile.offerings) == 1
    assert profile.offerings[0].id == old_id
    assert profile.offerings[0].slug == "nieuwe-projectnaam"
    hist = db.query(OfferingSlugHistory).filter_by(old_slug=old_slug).one_or_none()
    assert hist is not None
