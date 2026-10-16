"""stats_service — vindbaarheid meten zonder iemand te volgen (PRD hub §4.4).

Telt per profiel per dag: mensen die het profiel bekeken (``view``), AI-assistenten
die het ophaalden (``ai_fetch``, herkend aan hun user-agent) en anonieme MCP-
zoekresultaten waarin het stond (``mcp_hit``). Alleen getallen: geen IP, geen
user-agent, geen cookie. Andere bots (crawlers, scripts) tellen niet mee.

Tellen is best-effort: een fout mag het tonen van een profiel nooit breken.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Inquiry, ProfileStatDay
from app.security import utcnow

logger = logging.getLogger(__name__)

__all__ = [
    "VIEW",
    "AI_FETCH",
    "MCP_HIT",
    "classify_agent",
    "record",
    "record_view",
    "Summary",
    "summary",
]

VIEW, AI_FETCH, MCP_HIT = "view", "ai_fetch", "mcp_hit"
WINDOW_DAYS = 30

# AI-assistenten die een pagina ophalen voor een antwoord of hun zoekindex.
_AI_AGENTS = re.compile(
    r"GPTBot|ChatGPT-User|OAI-SearchBot|ClaudeBot|Claude-User|Claude-SearchBot|anthropic-ai|"
    r"PerplexityBot|Perplexity-User|Google-Extended|Applebot-Extended|Meta-ExternalAgent|"
    r"cohere-ai|MistralAI-User|DuckAssistBot|YouBot",
    re.I,
)
# Overige automaten: tellen niet als mens en niet als AI.
_OTHER_BOTS = re.compile(
    r"bot|crawl|spider|slurp|curl|wget|python|httpx|requests|go-http|headless|"
    r"lighthouse|preview|facebookexternalhit|monitor|uptime",
    re.I,
)


def classify_agent(user_agent: str | None) -> str | None:
    """``ai_fetch`` | ``view`` | ``None`` (niet tellen)."""
    ua = user_agent or ""
    if _AI_AGENTS.search(ua):
        return AI_FETCH
    if not ua.strip() or _OTHER_BOTS.search(ua):
        return None
    return VIEW


def _today() -> date:
    return utcnow().date()


def record(db: Session, profile_id: int, kind: str, day: date | None = None, n: int = 1) -> None:
    """Hoog de teller op (atomair UPDATE; ontbreekt de rij, dan een insert in een
    savepoint — een race op de unique-constraint valt terug op de UPDATE)."""
    day = day or _today()
    where = (
        ProfileStatDay.profile_id == profile_id,
        ProfileStatDay.day == day,
        ProfileStatDay.kind == kind,
    )
    done = db.execute(
        update(ProfileStatDay).where(*where).values(count=ProfileStatDay.count + n)
    ).rowcount
    if done:
        return
    try:
        with db.begin_nested():
            db.add(ProfileStatDay(profile_id=profile_id, day=day, kind=kind, count=n))
            db.flush()
    except IntegrityError:
        db.execute(update(ProfileStatDay).where(*where).values(count=ProfileStatDay.count + n))


def record_view(db: Session, profile_id: int, user_agent: str | None) -> None:
    """Tel een profielbezoek (mens of AI). Best-effort, commit zelf."""
    kind = classify_agent(user_agent)
    if kind is None:
        return
    try:
        record(db, profile_id, kind)
        db.commit()
    except Exception:  # noqa: BLE001 — tellen mag het profiel nooit breken
        db.rollback()
        logger.exception("stat-teller faalde voor profiel %s", profile_id)


@dataclass(frozen=True)
class Summary:
    days: list[tuple[date, int]]  # (dag, mensen) voor de laatste WINDOW_DAYS dagen
    views: int
    ai_fetches: int
    mcp_hits: int
    inquiries: int
    peak: int


def summary(db: Session, profile_id: int, member_id: int, today: date | None = None) -> Summary:
    today = today or _today()
    start = today - timedelta(days=WINDOW_DAYS - 1)
    rows = db.execute(
        select(ProfileStatDay.day, ProfileStatDay.kind, ProfileStatDay.count).where(
            ProfileStatDay.profile_id == profile_id, ProfileStatDay.day >= start
        )
    ).all()
    per_day = {start + timedelta(days=i): 0 for i in range(WINDOW_DAYS)}
    totals = {VIEW: 0, AI_FETCH: 0, MCP_HIT: 0}
    for day, kind, count in rows:
        totals[kind] = totals.get(kind, 0) + count
        if kind == VIEW and day in per_day:
            per_day[day] += count
    since = utcnow().replace(tzinfo=None) - timedelta(days=WINDOW_DAYS)
    inquiries = db.scalar(
        select(func.count(Inquiry.id)).where(
            Inquiry.member_id == member_id, Inquiry.created_at >= since
        )
    ) or 0
    days = sorted(per_day.items())
    return Summary(
        days=days,
        views=totals[VIEW],
        ai_fetches=totals[AI_FETCH],
        mcp_hits=totals[MCP_HIT],
        inquiries=inquiries,
        peak=max((c for _d, c in days), default=0),
    )
