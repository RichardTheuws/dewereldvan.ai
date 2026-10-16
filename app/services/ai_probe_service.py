"""ai_probe_service — de maandelijkse AI-steekproef (PRD hub §4.4, deel 2).

Beantwoordt per openbaar profiel twee realistische vragen zoals een opdrachtgever
ze aan een AI-assistent stelt ("Welke AI-trainers in Nederland of België kun je
aanraden voor zorg?"). Claude beantwoordt ze met web-search; wij stellen daarna
DETERMINISTISCH vast of het lid genoemd werd en of dewereldvan.ai tussen de bronnen
stond. Eerlijk benoemd als steekproef met Claude, geen ChatGPT-ranking.

- De vragen komen uit de publieke vermelding (``directory_service.maker_record``):
  nul AI om ze te maken, en nooit iets uit een besloten blok.
- Leden-AI (geen bezoeker) → valt buiten de bezoekers-cap; eigen begrenzing:
  ``MAX_PROBES_PER_RUN`` en ``max_uses`` op web_search, alleen openbare profielen,
  idempotent per maand (de job slaat al-gemeten vragen over).
- Gegated op ``settings.ai_enrich_enabled``; best-effort (een fout = geen rij).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import anthropic
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AiProbe, Profile
from app.security import utcnow
from app.services import directory_service

logger = logging.getLogger(__name__)

__all__ = [
    "ProbeAnswer",
    "questions_for",
    "ask",
    "evaluate",
    "run_month",
    "latest_for",
    "current_month",
]

MODEL: str = settings.anthropic_model
MAX_TOKENS = 2500
MAX_SEARCHES = 3
# Bewust de eenvoudige zoekversie: 20260209 filtert via code-execution, wat de
# max_uses opslokt en kan time-outen (gemeten 2026-10-16). Gewoon zoeken lijkt ook
# meer op hoe een doorsnee assistent antwoordt.
WEB_SEARCH_TOOL = "web_search_20250305"
MAX_PROBES_PER_RUN = 60
MAX_PAUSES = 3
_TOOL_RESULT_INPUT_KEYS = ("type", "tool_use_id", "content", "is_error")
HUB_HOST = "dewereldvan.ai"

SYSTEM_PROMPT = (
    "Je bent een behulpzame AI-assistent. Beantwoord de vraag van de gebruiker zoals je dat "
    "normaal zou doen: zoek op het web, noem concrete mensen of bureaus met hun naam, en "
    "verwijs naar je bronnen. Antwoord kort, in het Nederlands."
)

_PHRASE = {
    "Bouwer": "AI-developers of AI-bureaus",
    "Trainer": "AI-trainers",
    "Video-AI": "makers van AI-video",
    "Audio-AI": "makers van AI-audio of -muziek",
    "Publicatie": "schrijvers of onderzoekers over AI",
    "Design": "ontwerpers die met AI werken",
}


@dataclass(frozen=True)
class ProbeAnswer:
    text: str
    sources: list[str] = field(default_factory=list)


def current_month() -> str:
    return utcnow().strftime("%Y-%m")


def questions_for(profile: Profile) -> list[str]:
    """Hooguit twee vragen, uit de PUBLIEKE vermelding. Zonder kopregel en zonder
    discipline valt er niets realistisch te vragen → lege lijst."""
    rec = directory_service.maker_record(profile)
    out: list[str] = []
    if rec["disciplines"]:
        phrase = _PHRASE.get(rec["disciplines"][0], "AI-specialisten")
        topic = f" voor {rec['tags'][0]}" if rec["tags"] else ""
        out.append(f"Welke {phrase} in Nederland of België kun je aanraden{topic}?")
    if rec["kopregel"]:
        out.append(
            f"Ik zoek iemand in Nederland of België voor dit: {rec['kopregel']}. Wie raad je aan?"
        )
    return [q[:300] for q in out]


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


def _field(block: object, key: str):
    return block.get(key) if isinstance(block, dict) else getattr(block, key, None)


def _input_blocks(blocks: list) -> list[dict]:
    """Maak ontvangen blokken geschikt als invoer (output-only velden eruit; zie
    [[dewereldvan-ai-engine-constraints]])."""
    cleaned: list[dict] = []
    for b in blocks:
        d = b.model_dump() if hasattr(b, "model_dump") else dict(b)
        if str(d.get("type", "")).endswith("_tool_result"):
            d = {k: d[k] for k in _TOOL_RESULT_INPUT_KEYS if k in d}
        cleaned.append(d)
    return cleaned


def ask(question: str, *, client: anthropic.Anthropic | None = None) -> ProbeAnswer:
    """Eén vraag aan Claude met web-search. Geeft de antwoordtekst + geciteerde URLs."""
    client = client or _client()
    convo: list[dict] = [{"role": "user", "content": question}]
    blocks: list = []
    for _ in range(MAX_PAUSES + 1):
        message = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=[{"type": WEB_SEARCH_TOOL, "name": "web_search", "max_uses": MAX_SEARCHES}],
            messages=convo,
        )
        content = list(_field(message, "content") or [])
        blocks.extend(content)
        if _field(message, "stop_reason") != "pause_turn":
            break
        # Server-tool pauzeerde de beurt: binnen dezelfde beurt hervatten (blokken vers).
        convo = convo + [{"role": "assistant", "content": _input_blocks(content)}]
    texts: list[str] = []
    sources: list[str] = []
    for block in blocks:
        if _field(block, "type") != "text":
            continue
        texts.append(_field(block, "text") or "")
        for cite in _field(block, "citations") or []:
            url = _field(cite, "url")
            if url and url not in sources:
                sources.append(url)
    return ProbeAnswer(text="".join(texts).strip(), sources=sources[:10])


def evaluate(profile: Profile, answer: ProbeAnswer) -> tuple[bool, bool]:
    """(genoemd, dewereldvan.ai als bron) — deterministisch, geen tweede AI-call."""
    text = answer.text.lower()
    name = (profile.display_name or "").strip().lower()
    mentioned = bool(name) and name in text
    hub = any(HUB_HOST in u for u in answer.sources) or HUB_HOST in text
    return mentioned, hub


def _done(db: Session, profile_id: int, month: str) -> set[str]:
    return set(
        db.scalars(
            select(AiProbe.question).where(AiProbe.profile_id == profile_id, AiProbe.month == month)
        )
    )


def run_month(
    db: Session,
    *,
    month: str | None = None,
    client: anthropic.Anthropic | None = None,
    limit: int = MAX_PROBES_PER_RUN,
) -> int:
    """Meet alle openbare profielen voor deze maand (idempotent). Geeft het aantal
    nieuwe metingen terug. Commit per meting (een latere fout kost eerdere niet)."""
    if not settings.ai_enrich_enabled:
        logger.info("ai_probe: AI staat uit (ai_enrich_enabled=False).")
        return 0
    month = month or current_month()
    made = 0
    for profile in directory_service.public_makers(db):
        done = _done(db, profile.id, month)
        for q in questions_for(profile):
            if q in done:
                continue
            if made >= limit:
                logger.warning("ai_probe: limiet van %d metingen bereikt.", limit)
                return made
            try:
                answer = ask(q, client=client)
            except Exception:  # noqa: BLE001 — best-effort
                logger.exception("ai_probe: vraag faalde voor profiel %s", profile.id)
                continue
            mentioned, hub = evaluate(profile, answer)
            try:
                with db.begin_nested():
                    db.add(AiProbe(
                        profile_id=profile.id, month=month, question=q, mentioned=mentioned,
                        hub_cited=hub, answer_excerpt=answer.text[:1200], sources=answer.sources,
                    ))
                    db.flush()
                db.commit()
                made += 1
            except IntegrityError:
                db.rollback()
    return made


def latest_for(db: Session, profile_id: int) -> list[AiProbe]:
    """De metingen van de meest recente gemeten maand (leeg = nog nooit gemeten)."""
    month = db.scalar(
        select(AiProbe.month).where(AiProbe.profile_id == profile_id)
        .order_by(AiProbe.month.desc()).limit(1)
    )
    if month is None:
        return []
    return list(
        db.scalars(
            select(AiProbe).where(AiProbe.profile_id == profile_id, AiProbe.month == month)
            .order_by(AiProbe.id)
        )
    )
