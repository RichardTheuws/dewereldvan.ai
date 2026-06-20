"""Tool-service — beheer de AI-toolset op een profiel + de gedeelde catalogus.

Spiegelt het tag-deel van ``profile_service`` (normalisatie/dedup op slug,
globaal gedeelde rij via ``get_or_create``, replace-semantiek in ``set_tools``),
met twee verschillen:

- een tool draagt een optionele ``url``; de logo-verrijking (``logo_url``) loopt
  uitsluitend via de nachtelijke job ``app.jobs.enrich_tool_logos``
  (``logo_service.refresh_all``) — nooit synchroon bij opslaan, zodat de bewerk-
  UX niet vertraagt en er geen pre-commit-race is. ``logo_url`` mag None blijven;
- naast ``set_tools`` (replace) bestaan ``add_tool``/``remove_tool`` voor losse
  toevoeg/verwijder-acties (de tag-laag heeft die niet, maar de SPEC vraagt ze).

De ledengids-filter op tool zit in ``members_service.list_public_profiles(tool=...)``
(één AVG-poort, exact zoals tags).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Profile, Tool
from app.security import slugify


def _parse_tool_names(raw) -> list[str]:
    """Splits een komma-gescheiden tool-string of lijst in genormaliseerde namen.

    Dedup op de canonieke slug (eerste casing wint), exact ``_parse_tags``.
    """
    if not raw:
        return []
    if isinstance(raw, str):
        parts = raw.split(",")
    else:
        parts = list(raw)
    seen: dict[str, str] = {}
    for part in parts:
        name = (part or "").strip()
        if not name:
            continue
        seen.setdefault(slugify(name), name)
    return list(seen.values())


def get_or_create(db: Session, name: str, url: str | None = None) -> Tool:
    """Vind of maak de gedeelde ``Tool`` voor ``name`` (dedup op canonieke slug).

    Bestaat de tool al en heeft die nog geen URL terwijl er nu één meekomt, dan
    vullen we die aan (verrijkt de catalogus zonder iets te overschrijven). Het
    logo wordt NIET hier opgehaald — dat doet de nachtelijke job
    (``logo_service.refresh_all``) los, om een pre-commit-race te vermijden.
    """
    slug = slugify(name)
    tool = db.scalar(select(Tool).where(Tool.slug == slug))
    clean_url = (url or "").strip() or None
    if tool is None:
        tool = Tool(name=name, slug=slug, url=clean_url)
        db.add(tool)
        db.flush()
        return tool
    # Bestaande rij: vul alleen een ontbrekende URL aan (niet overschrijven).
    if clean_url and not tool.url:
        tool.url = clean_url
        db.flush()
    return tool


def set_tools(db: Session, profile: Profile, names) -> None:
    """Vervang de toolset van het profiel (replace-semantiek, zoals ``set_tags``).

    ``names`` mag een komma-gescheiden string of een lijst van namen zijn.
    """
    parsed = _parse_tool_names(names)
    profile.tools = [get_or_create(db, name) for name in parsed]
    db.flush()


def add_tool(
    db: Session, profile: Profile, name: str, url: str | None = None
) -> Tool | None:
    """Voeg één tool toe aan het profiel (idempotent op de koppeling).

    Vrij toevoegen van een tool buiten de catalogus werkt (``get_or_create``).
    Retourneert de ``Tool`` (of None bij een lege naam).
    """
    if not (name or "").strip():
        return None
    tool = get_or_create(db, name.strip(), url)
    if tool not in profile.tools:
        profile.tools.append(tool)
        db.flush()
    return tool


def remove_tool(db: Session, profile: Profile, tool_id: int) -> bool:
    """Ontkoppel één tool van het profiel. Returnt True bij verwijderen.

    Verwijdert ALLEEN de koppeling, niet de gedeelde ``Tool``-rij (die hoort bij
    andere leden — zelfde semantiek als tags).
    """
    tool = db.get(Tool, tool_id)
    if tool is None or tool not in profile.tools:
        return False
    profile.tools.remove(tool)
    db.flush()
    return True
