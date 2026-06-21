"""graph_service — gegronde relaties tussen makers, strict uit de DB.

De graaf is de unieke asset (noordster). Relaties komen UITSLUITEND uit gedeelde
tags/tools: geen LLM, geen externe call → nul hallucinatie, nul kosten, unattended
draaibaar. Voedt de "Verbonden in de wereld"-sectie op het publieke profiel en
(later) de echte ledengids-graaf — één bron, geen tweede implementatie.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Profile
from app.services import members_service


@dataclass(frozen=True)
class RelatedMaker:
    """Eén gegronde buur op de graaf + de concrete grond van de verbinding."""

    profile: Profile
    shared_label: str  # bv. "deelt tool: cursor" of "beiden in voice-agents"
    score: int


def _idents(items) -> set[str]:
    """Genormaliseerde identifiers (slug, anders naam) van tags/tools."""
    out: set[str] = set()
    for it in items or []:
        key = getattr(it, "slug", None) or getattr(it, "name", None)
        if key:
            out.add(str(key).strip().lower())
    return out


def _label(shared_tools: set[str], shared_tags: set[str]) -> str:
    """Concreet, eerlijk label van de sterkste gedeelde grond."""
    if shared_tools:
        sample = sorted(shared_tools)[0]
        n = len(shared_tools)
        return f"deelt {n} tools · {sample}" if n > 1 else f"deelt tool: {sample}"
    sample = sorted(shared_tags)[0]
    n = len(shared_tags)
    return f"{n} gedeelde thema's · {sample}" if n > 1 else f"beiden in {sample}"


def related_members(
    db: Session, profile: Profile, *, limit: int = 4
) -> list[RelatedMaker]:
    """Tot ``limit`` publieke makers die ≥1 tag of tool met ``profile`` delen.

    Tools wegen zwaarder dan tags (specifieker signaal). In-memory over de
    publieke-profielen-poort (``list_public_profiles`` eager-load't tags/tools),
    zodat besloten/geschorst nooit lekt en er geen extra query per kandidaat is.
    Lege lijst als het profiel zelf geen tags/tools heeft (niets om op te gronden).
    """
    self_tags = _idents(getattr(profile, "tags", None))
    self_tools = _idents(getattr(profile, "tools", None))
    if not self_tags and not self_tools:
        return []

    out: list[RelatedMaker] = []
    for cand in members_service.list_public_profiles(db):
        if cand.id == profile.id:
            continue
        shared_tools = self_tools & _idents(getattr(cand, "tools", None))
        shared_tags = self_tags & _idents(getattr(cand, "tags", None))
        score = len(shared_tools) * 2 + len(shared_tags)
        if score == 0:
            continue
        out.append(
            RelatedMaker(
                profile=cand,
                shared_label=_label(shared_tools, shared_tags),
                score=score,
            )
        )
    out.sort(key=lambda r: (-r.score, (r.profile.display_name or "").lower()))
    return out[:limit]
