"""Offering-slug-service (L3/L4) — uniek + collision-suffix + rename→301-redirect.

Bewijst: ``ensure_slug`` is idempotent en uniek (botsing → ``-2``), een rename
legt de oude slug vast in ``OfferingSlugHistory`` zodat ``redirect_target`` de
huidige slug teruggeeft (basis voor de 301 in de route).
"""

from __future__ import annotations

from app.models import OfferingSlugHistory
from app.security import slugify
from app.services import offering_slug


def test_ensure_slug_from_title(db, make_member, make_profile, make_offering):
    member = make_member(email="o1@example.com")
    profile = make_profile(member)
    off = make_offering(profile, title="Mijn Zorg Platform")
    slug = offering_slug.ensure_slug(db, off)
    assert slug == slugify("Mijn Zorg Platform") == "mijn-zorg-platform"
    assert off.slug == slug


def test_ensure_slug_is_idempotent(db, make_member, make_profile, make_offering):
    member = make_member(email="o2@example.com")
    profile = make_profile(member)
    off = make_offering(profile, title="Stabiel Project")
    first = offering_slug.ensure_slug(db, off)
    # Tweede aanroep raakt de bestaande slug niet aan (stabiliteit/linkwaarde).
    second = offering_slug.ensure_slug(db, off)
    assert first == second


def test_colliding_titles_get_numeric_suffix(
    db, make_member, make_profile, make_offering
):
    member = make_member(email="o3@example.com")
    profile = make_profile(member)
    a = make_offering(profile, title="Tweeling")
    b = make_offering(profile, title="Tweeling")
    slug_a = offering_slug.ensure_slug(db, a)
    slug_b = offering_slug.ensure_slug(db, b)
    assert slug_a == "tweeling"
    assert slug_b == "tweeling-2"
    assert slug_a != slug_b


def test_rename_records_old_slug_for_redirect(
    db, make_member, make_profile, make_offering
):
    member = make_member(email="o4@example.com")
    profile = make_profile(member)
    off = make_offering(profile, title="Oude Naam")
    old = offering_slug.ensure_slug(db, off)
    assert old == "oude-naam"

    new = offering_slug.rename_to(db, off, "Gloednieuwe Naam")
    assert new == "gloednieuwe-naam"
    assert off.slug == new

    # De oude slug staat nu in de history-tabel.
    hist = db.scalar(
        OfferingSlugHistory.__table__.select().where(
            OfferingSlugHistory.old_slug == old
        )
    )
    assert hist is not None


def test_redirect_target_resolves_old_to_current(
    db, make_member, make_profile, make_offering
):
    member = make_member(email="o5@example.com")
    profile = make_profile(member)
    off = make_offering(profile, title="Eerste Titel")
    old = offering_slug.ensure_slug(db, off)
    new = offering_slug.rename_to(db, off, "Tweede Titel")

    # Lookup op de oude slug → huidige slug (basis voor 301).
    assert offering_slug.redirect_target(db, old) == new
    # Een onbekende slug → None (echte 404).
    assert offering_slug.redirect_target(db, "bestaat-niet") is None


def test_find_by_slug(db, make_member, make_profile, make_offering):
    member = make_member(email="o6@example.com")
    profile = make_profile(member)
    off = make_offering(profile, title="Vindbaar")
    offering_slug.ensure_slug(db, off)
    found = offering_slug.find_by_slug(db, "vindbaar")
    assert found is not None and found.id == off.id
    assert offering_slug.find_by_slug(db, "niets") is None
