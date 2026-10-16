"""search_service — één zoekveld over makers, events en nieuws (PRD voordeur §3.1).

Nul AI (een bezoeker triggert nooit betaalde AI). Makers komen uit
``directory_service.public_makers`` (alleen openbare profielen; alleen publieke
blokken doorzocht), events en nieuws uit de bestaande kijker-bewuste lijsten van
``post_service`` (``live``, niet verborgen, nieuws van besloten leden valt weg).
Zoekopdrachten worden niet opgeslagen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Post, Profile
from app.security import naive_utc, utcnow
from app.services import directory_service, post_service
from app.services.visibility import public_section_visible

__all__ = [
    "MIN_QUERY", "MAX_QUERY", "PER_GROUP", "Results", "search", "normalize_query", "is_searchable",
]

MIN_QUERY = 2
MAX_QUERY = 100
PER_GROUP = 6


@dataclass
class Results:
    query: str
    makers: list[Profile] = field(default_factory=list)
    events: list[Post] = field(default_factory=list)
    news: list[Post] = field(default_factory=list)
    totals: dict[str, int] = field(default_factory=dict)

    @property
    def empty(self) -> bool:
        return not (self.makers or self.events or self.news)


def normalize_query(raw: str | None) -> str:
    return " ".join((raw or "").split())[:MAX_QUERY]


def _terms(query: str) -> list[str]:
    return [t for t in query.lower().split() if len(t) >= MIN_QUERY]


def is_searchable(query: str) -> bool:
    """Bevat de (genormaliseerde) zoekterm minstens één woord van ≥ ``MIN_QUERY`` tekens?"""
    return bool(_terms(query))


def _matches(haystack: str, terms: list[str]) -> bool:
    text = haystack.lower()
    return all(t in text for t in terms)


def _maker_text(p: Profile) -> str:
    parts = [p.display_name or "", p.headline or ""]
    parts += [t.name for t in p.tags] + [t.name for t in getattr(p, "tools", [])]
    if public_section_visible(p, "makes", None):
        parts.append(p.makes_summary or "")
        parts += [o.title or "" for o in p.offerings]
        parts += [o.description or "" for o in p.offerings]
    if public_section_visible(p, "bio", None):
        parts.append(p.bio or "")
    return " ".join(parts)


def _upcoming(events: list[Post], now: datetime) -> list[Post]:
    return [e for e in events if e.next_at is None or e.next_at >= now]


def search(db: Session, raw: str | None, *, now: datetime | None = None) -> Results:
    """Zoek op alle woorden (AND, hoofdletterongevoelig). Een te korte zoekterm
    geeft een leeg resultaat zonder te zoeken."""
    query = normalize_query(raw)
    res = Results(query=query)
    terms = _terms(query)
    if not terms:
        return res
    now = naive_utc(now or utcnow())

    makers = [p for p in directory_service.public_makers(db) if _matches(_maker_text(p), terms)]
    events = [
        e for e in _upcoming(post_service.list_events(db, now=now), now)
        if _matches(" ".join([e.title or "", e.location or "", e.description or "",
                              e.cadence_note or ""]), terms)
    ]
    news = [
        n for n in post_service.list_news(db, viewer=None)
        if _matches(" ".join([n.title or "", n.ai_take or "", n.description or ""]), terms)
    ]
    res.totals = {"makers": len(makers), "events": len(events), "news": len(news)}
    res.makers, res.events, res.news = makers[:PER_GROUP], events[:PER_GROUP], news[:PER_GROUP]
    return res
