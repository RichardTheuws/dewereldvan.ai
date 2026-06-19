"""Seed — agenda-events (gegrond) + roadmap-cachet.

Prod-only data-migratie (tests bouwen via ``create_all``, niet via Alembic, dus
deze seed raakt de testsuite niet). **Idempotent + niet-destructief**: events
worden alleen geplaatst als ``post`` nog leeg is; roadmap-items alleen als
``roadmap_item`` nog leeg is — zo overschrijven we nooit door-leden/admin
toegevoegde of bewerkte data bij een latere stamp/herhaling.

Gegronde seed (geen verzinsels):
- **Aimelo** — opgehaald van https://aimelo.nl: AI-community in Almelo, elke
  woensdag 18:00–20:00, eerstvolgend wo 24 juni 2026.
- **Meetup Meppel/Zwolle** — door de eigenaar als 'wekelijks?' aangedragen,
  expliciet als TE BEVESTIGEN gemarkeerd (de frequentie-badge maakt een fout
  meteen zichtbaar zodat de organisator 'm corrigeert).

Revision ID: 0011_seed_agenda_roadmap
Revises: 0010_post
Create Date: 2026-06-19

"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011_seed_agenda_roadmap"
down_revision: str | None = "0010_post"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_post = sa.table(
    "post",
    sa.column("added_by_id", sa.Integer),
    sa.column("kind", sa.String),
    sa.column("title", sa.String),
    sa.column("description", sa.Text),
    sa.column("url", sa.String),
    sa.column("hidden", sa.Boolean),
    sa.column("frequency", sa.String),
    sa.column("next_at", sa.DateTime),
    sa.column("cadence_note", sa.String),
    sa.column("location", sa.String),
)

_roadmap = sa.table(
    "roadmap_item",
    sa.column("title", sa.String),
    sa.column("description", sa.Text),
    sa.column("status", sa.String),
    sa.column("phase", sa.String),
    sa.column("position", sa.Integer),
)


_EVENTS = [
    {
        "added_by_id": None,
        "kind": "event",
        "title": "Aimelo — de AI-community van Almelo",
        "description": (
            "Elke woensdag samen met AI experimenteren, kennis delen en elkaar "
            "helpen. Ondernemers, studenten en makers. Gratis, geen "
            "verplichtingen. Locatie: Moving-In, Twentepoort Oost 26, Almelo."
        ),
        "url": "https://aimelo.nl",
        "hidden": False,
        "frequency": "wekelijks",
        # 18:00 lokale tijd; cadence_note draagt de exacte tijd.
        "next_at": datetime(2026, 6, 24, 18, 0),
        "cadence_note": "elke woensdag 18:00–20:00",
        "location": "Almelo",
    },
    {
        "added_by_id": None,
        "kind": "event",
        "title": "AI-meetup Meppel/Zwolle",
        "description": (
            "Regionale AI-meetup in de omgeving Meppel/Zwolle. Frequentie en "
            "exacte locatie nog te bevestigen — ken jij de organisator? Vul de "
            "details aan of corrigeer ze."
        ),
        "url": None,
        "hidden": False,
        "frequency": "wekelijks",
        "next_at": None,
        "cadence_note": "wekelijks — nog te bevestigen",
        "location": "Meppel/Zwolle",
    },
]


# (title, description, status, phase, position)
_ROADMAP = [
    ("Ledengids & profielen", "Wie we zijn, wat we maken, waar we naar zoeken — doorzoekbaar.", "gedaan", "Nu live", 0),
    ("AI-profielbouw", "Deel een link; de AI bouwt je profiel in de canvas op.", "gedaan", "Nu live", 1),
    ("Agent-canvas", "De agent ís de interface — interfaces materialiseren in-stroom.", "gedaan", "Nu live", 2),
    ("Agenda & meetups", "Een levende agenda van AI-meetups die iedereen mag aanvullen.", "bezig", "In aanbouw", 0),
    ("Nieuws & uitgelicht werk", "Artikelen, interviews en werk van leden — direct gedeeld.", "bezig", "In aanbouw", 1),
    ("Matchmaking vraag ↔ aanbod", "Koppel wat je maakt aan wie het zoekt; slimme suggesties.", "gepland", "Volgende", 0),
    ("Community & updates", "Korte updates en reacties binnen de besloten community.", "overwegen", "Later", 0),
    ("Publieke showcase", "Een etalage naar buiten: uitgelicht werk van leden, SEO.", "overwegen", "Later", 1),
    ("Contact & intro's", "Warme introducties tussen leden, met instemming.", "overwegen", "Later", 2),
]


def upgrade() -> None:
    bind = op.get_bind()

    have_posts = bind.execute(sa.text("SELECT COUNT(*) FROM post")).scalar() or 0
    if not have_posts:
        op.bulk_insert(_post, _EVENTS)

    have_roadmap = (
        bind.execute(sa.text("SELECT COUNT(*) FROM roadmap_item")).scalar() or 0
    )
    if not have_roadmap:
        op.bulk_insert(
            _roadmap,
            [
                {
                    "title": t,
                    "description": d,
                    "status": s,
                    "phase": ph,
                    "position": pos,
                }
                for (t, d, s, ph, pos) in _ROADMAP
            ],
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM post WHERE added_by_id IS NULL AND kind = 'event'")
    )
    bind.execute(
        sa.text("DELETE FROM roadmap_item WHERE phase IN ('Nu live', 'In aanbouw')")
    )
