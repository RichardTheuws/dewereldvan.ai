"""Roadmap-inhoud verversen naar de echte, actuele staat (idempotent).

De roadmap stond nog op pre-pivot-inhoud (bv. "Events" onder Overwegen, terwijl de
agenda + curatie al live zijn). Dit script zet de canonieke, eerlijke roadmap neer:
wat er al gelanceerd is, wat in aanbouw is, wat gepland staat en wat we overwegen.

Veilig + herhaalbaar:
- Items die uit een lid-idee zijn gepromoot (``linked_idea_id`` gezet) blijven staan
  (die zijn door de community gevoed — niet door ons seed-script beheerd).
- Alle overige (door ons beheerde) items worden vervangen door de lijst hieronder.

Draai op de M4:

    docker compose exec -T web python -m scripts.seed_roadmap
"""

from __future__ import annotations

import logging

from sqlalchemy import delete, func, select

from app.db import SessionLocal
from app.models import RoadmapItem, RoadmapStatus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed_roadmap")

# (status, fase-tag, titel, omschrijving). Volgorde binnen een status = positie.
CANONICAL: list[tuple[RoadmapStatus, str, str, str]] = [
    # --- Gelanceerd (gedaan) — staat live op het platform ---
    (RoadmapStatus.gedaan, "Profiel", "AI-profiel uit één link",
     "Plak een link — de agent leest 'm en bouwt je profiel. Jij controleert en verfijnt, alles inline."),
    (RoadmapStatus.gedaan, "Profiel", "Online-ontdekking",
     "De agent zoekt je publieke werk op en stelt voor wat op je profiel kan; jij bevestigt per stuk."),
    (RoadmapStatus.gedaan, "Netwerk", "Levende ledengids",
     "Ontdek de makers, gefilterd op discipline, tools en waar ze voor openstaan."),
    (RoadmapStatus.gedaan, "Netwerk", "Matchmaking + intro's",
     "De agent matcht vraag en aanbod en stelt intro's voor — gegrond, consent-gepoort. Jij beslist."),
    (RoadmapStatus.gedaan, "Netwerk", "In je eigen tool (MCP)",
     "Praat met dewereldvan vanuit Claude Code of Cursor: profiel, zoeken, intro's — nul context-switch."),
    (RoadmapStatus.gedaan, "Agenda", "Agenda met categorieën & RSVP",
     "AI-meetups & events in NL/BE, filterbaar op soort; meld je aan (ga / organiseer / spreek)."),
    (RoadmapStatus.gedaan, "Agenda", "AI-agenda-curatie",
     "De agent vindt zelf echte events op het web en zet de zekere direct op de agenda."),
    (RoadmapStatus.gedaan, "Nieuws", "Wekelijkse nieuws-briefing",
     "Een AI-gecureerde shortlist van wat er voor déze groep toe doet — jij keurt 'm goed."),
    (RoadmapStatus.gedaan, "Tools", "Tool-catalogus & reviews",
     "Welke tools de groep gebruikt, met AI-dossiers en notities van leden."),
    (RoadmapStatus.gedaan, "Community", "Ideeënbus",
     "Opper wat het platform moet worden en stem mee — voedt deze roadmap."),
    (RoadmapStatus.gedaan, "Community", "Notificaties via je eigen kanaal",
     "Seintjes via Telegram in plaats van een mailbox vol — jij kiest het kanaal."),
    # --- In aanbouw (bezig) ---
    (RoadmapStatus.bezig, "Community", "Telegram rich-content bot",
     "Rijke updates en interactie vanuit het platform, rechtstreeks in Telegram."),
    # --- Gepland (gepland) ---
    (RoadmapStatus.gepland, "Netwerk", "Persoonlijk dashboard",
     "Eén overzicht van je matches, intro's en wat de agent voor je vond terwijl je weg was."),
    (RoadmapStatus.gepland, "Netwerk", "Direct contact tussen leden",
     "Praat direct met een match op het platform, na wederzijds akkoord."),
    # --- Overwegen (overwegen) ---
    (RoadmapStatus.overwegen, "Community", "Subgroepen per thema",
     "Plekken per domein (agents, beleid, RAG, …) voor diepere gesprekken."),
    (RoadmapStatus.overwegen, "Community", "Meer notificatiekanalen",
     "Naast Telegram ook andere kanalen, naar voorkeur van het lid."),
]


def main() -> int:
    with SessionLocal() as db:
        # Bewaar door-de-community-gevoede items; vervang alleen wat wij beheren.
        preserved = db.scalar(
            select(RoadmapItem).where(RoadmapItem.linked_idea_id.is_not(None)).limit(1)
        )
        db.execute(delete(RoadmapItem).where(RoadmapItem.linked_idea_id.is_(None)))

        pos_by_status: dict[RoadmapStatus, int] = {}
        for status, phase, title, desc in CANONICAL:
            pos = pos_by_status.get(status, 0)
            pos_by_status[status] = pos + 1
            db.add(
                RoadmapItem(
                    title=title, description=desc, status=status,
                    phase=phase, position=pos,
                )
            )
        db.commit()
        total = db.scalar(select(func.count()).select_from(RoadmapItem))
    logger.info("Roadmap geseed: %s items (community-items behouden: %s).",
                total, "ja" if preserved else "geen")
    return 0


if __name__ == "__main__":  # pragma: no cover
    main()
