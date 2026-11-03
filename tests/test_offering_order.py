"""Projecten verschijnen in de volgorde die het lid koos (``position``), niet in
de willekeurige rijvolgorde van de database."""

from __future__ import annotations

from app.models import Offering, Profile


def test_offerings_follow_position_not_insert_order(db, make_member, make_profile):
    profile = make_profile(make_member())
    for title, pos in [("Derde", 2), ("Eerste", 0), ("Tweede", 1), ("Ook tweede", 1)]:
        db.add(Offering(profile_id=profile.id, title=title, position=pos))
    db.commit()
    db.expire_all()

    titles = [o.title for o in db.get(Profile, profile.id).offerings]
    assert titles == ["Eerste", "Tweede", "Ook tweede", "Derde"]
