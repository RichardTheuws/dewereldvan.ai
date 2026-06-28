"""Gecureerde kennisbank voor de Concierge (Concierge-intelligentie Fase 1).

De ``explain``-tool was een vaste 6-topic-dict: elke vraag daarbuiten gaf
"onbekend onderwerp". Hier vervangen we dat door een **gecureerde corpus** +
deterministische **keyword-retrieval** — de grounding-poort blijft (de agent
synthetiseert ALLEEN uit teruggegeven snippets; we genereren geen platformfeiten
vrij). Geen LLM, geen embeddings, geen dependency: een token-overlap-score over
een vaste lijst entries. pgvector is een latere schaal-stap (zelfde keuze als
matchmaking) — lage op-last weegt zwaarder dan de recall-marge bij ~15 entries.

Eén bron: zowel de concierge (``tool_explain``) als de MCP-tool
``hoe_werkt_dewereldvan`` lezen hieruit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class KnowledgeEntry:
    """Eén gecureerd kennis-fragment. ``keywords`` sturen de retrieval-score."""

    id: str
    title: str
    text: str
    keywords: tuple[str, ...] = field(default_factory=tuple)


# Nederlandse stopwoorden + losse vraagwoorden die niets onderscheiden. Klein
# genoeg om hardcoded te houden; voorkomt dat "hoe/wat/de/het" de score sturen.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "de", "het", "een", "en", "of", "ik", "je", "jij", "mijn", "me", "we",
        "wij", "is", "zijn", "ben", "wordt", "word", "kan", "kun", "kunnen",
        "moet", "mag", "wil", "hoe", "wat", "wie", "waar", "wanneer", "waarom",
        "welke", "dit", "dat", "deze", "die", "er", "te", "op", "in", "aan",
        "voor", "met", "naar", "van", "om", "als", "dan", "ook", "nog", "wel",
        "niet", "geen", "maar", "bij", "uit", "over", "naar", "doen", "gaat",
        "gaan", "heb", "hebben", "heeft", "krijg", "krijgen", "even",
    }
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    """Lowercase tokens van len ≥ 3 zonder stopwoorden (deterministisch)."""
    return [
        t
        for t in _TOKEN_RE.findall((text or "").lower())
        if len(t) >= 3 and t not in _STOPWORDS
    ]


# --------------------------------------------------------------------------- #
# De gecureerde corpus — echte platformfeiten (geen marketing, geen verzinsels) #
# --------------------------------------------------------------------------- #

KNOWLEDGE: tuple[KnowledgeEntry, ...] = (
    KnowledgeEntry(
        id="platform",
        title="Wat is dewereldvan.ai",
        text=(
            "dewereldvan.ai is een open community voor iedereen in NL/BE die met "
            "AI bouwt, traint, ontwerpt, onderzoekt of er beleid over maakt — van "
            "wie net begint tot wie er dagelijks mee werkt. Je maakt een "
            "profiel (wie je bent, wat je maakt, waar je naar zoekt), vindt "
            "elkaar via de ledengids en brengt vraag en aanbod bij elkaar."
        ),
        keywords=("platform", "dewereldvan", "community", "wereld", "groep", "overzicht"),
    ),
    KnowledgeEntry(
        id="profiel",
        title="Je profiel maken",
        text=(
            "Je profiel bouw je samen met de AI: deel een link (je site, GitHub "
            "of LinkedIn) of vertel kort wie je bent, en het profiel vormt zich "
            "live. Daarna pas je elk veld inline aan. Publiceren doe je zelf — "
            "niets wordt automatisch openbaar."
        ),
        keywords=(
            "profiel", "aanmaken", "maken", "bouwen", "kopregel", "bio",
            "headline", "invullen", "link", "website", "github", "linkedin",
        ),
    ),
    KnowledgeEntry(
        id="zichtbaarheid",
        title="Zichtbaarheid van je profiel",
        text=(
            "Per profiel kies je de zichtbaarheid. De standaard is besloten: "
            "alleen leden zien je profiel. Openbaar maken kan, maar alleen met "
            "jouw expliciete toestemming. Besloten profielen verschijnen nooit "
            "in een openbare zoekopdracht."
        ),
        keywords=(
            "zichtbaarheid", "besloten", "openbaar", "prive", "privacy", "zien",
            "publiek", "afgeschermd", "instelling",
        ),
    ),
    KnowledgeEntry(
        id="login",
        title="Inloggen zonder wachtwoord",
        text=(
            "Je logt in zonder wachtwoord. Vul je e-mailadres in en je krijgt "
            "een magic-link toegestuurd; die link logt je veilig in. Er is dus "
            "geen wachtwoord om te onthouden of te verliezen."
        ),
        keywords=(
            "inloggen", "login", "aanmelden", "wachtwoord", "magic", "magisch",
            "link", "toegang", "email", "e-mailadres",
        ),
    ),
    KnowledgeEntry(
        id="registratie",
        title="Toegang en goedkeuring",
        text=(
            "Je registreert je met je e-mailadres. Een nieuwe aanmelding wordt "
            "kort door een beheerder goedgekeurd voordat je toegang krijgt; kom "
            "je via een uitnodigingslink binnen, dan ben je meteen goedgekeurd. "
            "De site is nu nog voor genodigden (preview)."
        ),
        keywords=(
            "registreren", "registratie", "aanmelden", "toegang", "goedkeuring",
            "goedkeuren", "uitnodiging", "invite", "lid", "worden", "wachtrij",
            "preview", "genodigden",
        ),
    ),
    KnowledgeEntry(
        id="kosten",
        title="Kosten en lidmaatschap",
        text=(
            "dewereldvan.ai is gratis en open voor iedereen die met AI bezig is. "
            "Er is geen openbare verkoop of abonnement: je meldt je aan (of komt "
            "via een uitnodiging) en na een korte check om spam te weren ben je "
            "welkom."
        ),
        keywords=(
            "kosten", "prijs", "betalen", "gratis", "geld", "abonnement",
            "lidmaatschap", "kost",
        ),
    ),
    KnowledgeEntry(
        id="avg",
        title="Je data en het recht om alles te wissen",
        text=(
            "Jij houdt de regie over je gegevens. Met één knop wis je je "
            "VOLLEDIGE profiel: profieltekst, projecten, zoekvragen, onderwerpen, "
            "je gesprek met de concierge, je foto en je account — alles wordt "
            "echt verwijderd en je wordt uitgelogd."
        ),
        keywords=(
            "data", "gegevens", "avg", "gdpr", "privacy", "wissen", "verwijderen",
            "verwijder", "vergeten", "account", "regie", "weg",
        ),
    ),
    KnowledgeEntry(
        id="matchmaking",
        title="Matches: vraag en aanbod",
        text=(
            "Het platform brengt vraag en aanbod bij elkaar. De AI vergelijkt "
            "wat jij zoekt met wat anderen maken (en omgekeerd) op "
            "complementariteit en stelt gegronde matches voor, met een korte "
            "uitleg waarom. Je ziet ze in je matches-overzicht."
        ),
        keywords=(
            "match", "matches", "matchmaking", "vraag", "aanbod", "koppelen",
            "complementair", "verbinden", "passend", "zoekt", "biedt",
        ),
    ),
    KnowledgeEntry(
        id="intro",
        title="Jezelf voorstellen (intro)",
        text=(
            "Vanuit een match of een profiel kun je 'stel me voor' kiezen: je "
            "schrijft (of de AI stelt voor) een kort gegrond bericht. De ander "
            "krijgt het en kan akkoord gaan. Contactgegevens worden pas gedeeld "
            "ná wederzijds akkoord — een bewuste consent-poort."
        ),
        keywords=(
            "intro", "introductie", "voorstellen", "kennismaken", "connect",
            "verbinden", "contact", "bericht", "benaderen",
        ),
    ),
    KnowledgeEntry(
        id="agenda",
        title="Agenda en meetups",
        text=(
            "In de agenda staan de meetups en events van de community. Iedereen "
            "mag er direct een toevoegen (eenmalig of terugkerend). De agenda "
            "kijkt vooruit: je ziet wat eraan komt."
        ),
        keywords=(
            "agenda", "meetup", "meetups", "event", "events", "bijeenkomst",
            "afspraak", "wanneer", "kalender",
        ),
    ),
    KnowledgeEntry(
        id="nieuws",
        title="Nieuws van de leden",
        text=(
            "Het nieuws verzamelt artikelen, interviews en uitgelicht werk van "
            "de leden. Iedereen plaatst direct, met een rol-badge: zelf "
            "geschreven, geïnterviewd, vermeld of gedeeld."
        ),
        keywords=(
            "nieuws", "artikel", "artikelen", "interview", "geinterviewd",
            "publicatie", "verschenen", "geschreven", "uitgelicht", "pers",
        ),
    ),
    KnowledgeEntry(
        id="verbind",
        title="Je AI-tool koppelen (MCP)",
        text=(
            "Je kunt dewereldvan.ai koppelen aan je eigen AI-tool (Claude Code, "
            "Cursor of een eigen agent) via een MCP-server. Dan bouw je je "
            "profiel, doorzoek je de makers, haal je je matches op en stel je je "
            "voor — rechtstreeks vanuit je editor. Ga naar 'Verbind tool' "
            "(/profiel/verbind), genereer een token en plak het getoonde "
            "`claude mcp add`-commando in je tool."
        ),
        keywords=(
            "verbind", "verbinden", "koppelen", "koppeling", "mcp", "server",
            "tool", "claude", "code", "cursor", "agent", "editor", "token",
            "integratie", "api",
        ),
    ),
    KnowledgeEntry(
        id="ideeen",
        title="De ideeënbus",
        text=(
            "In de ideeënbus deel je ideeën voor het platform en stem je op die "
            "van anderen. De beste ideeën belanden op de roadmap."
        ),
        keywords=("ideeen", "idee", "ideeenbus", "voorstel", "stemmen", "stem", "feedback"),
    ),
    KnowledgeEntry(
        id="roadmap",
        title="De roadmap",
        text=(
            "De roadmap toont waar we mee bezig zijn en wat er gepland staat. "
            "Hij wordt gevoed door de ideeën van de leden."
        ),
        keywords=("roadmap", "planning", "gepland", "toekomst", "bezig", "komt"),
    ),
    KnowledgeEntry(
        id="demo",
        title="De publieke demo",
        text=(
            "Op /demo staat een publieke demonstratie: een fictief profiel dat "
            "door de AI live wordt opgebouwd, met dezelfde kosmische stijl als "
            "het echte platform. Zo zie je zonder account hoe profielbouw werkt."
        ),
        keywords=("demo", "voorbeeld", "proberen", "showcase", "fictief"),
    ),
)

_BY_ID: dict[str, KnowledgeEntry] = {e.id: e for e in KNOWLEDGE}


def overview() -> KnowledgeEntry:
    """De val-terug-entry voor een lege query (het platform-overzicht)."""
    return _BY_ID["platform"]


def search(query: str, *, limit: int = 3) -> list[KnowledgeEntry]:
    """Top-``limit`` entries voor ``query`` op token-overlap (deterministisch).

    Score per entry: keyword-hit telt zwaar (×3), token in titel (×2), token in
    body (×1). Entries met score 0 vallen af. Lege query → het overzicht.
    Stabiele volgorde bij gelijke score (corpus-volgorde) zodat tests vast staan.
    """
    qtokens = _tokens(query)
    if not qtokens:
        return [overview()]

    scored: list[tuple[int, int, KnowledgeEntry]] = []
    for idx, entry in enumerate(KNOWLEDGE):
        kw = {k.lower() for k in entry.keywords}
        title_tokens = set(_tokens(entry.title))
        body_tokens = set(_tokens(entry.text))
        score = 0
        for t in qtokens:
            if t in kw:
                score += 3
            if t in title_tokens:
                score += 2
            if t in body_tokens:
                score += 1
        if score > 0:
            scored.append((score, -idx, entry))  # -idx: stabiel, corpus-volgorde

    scored.sort(key=lambda s: (s[0], s[1]), reverse=True)
    return [e for _score, _idx, e in scored[:limit]]
