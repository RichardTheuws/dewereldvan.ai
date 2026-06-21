# 01 — Noordster: wat 'De Wereld van AI' is

**Status**: TER GOEDKEURING · **Datum**: 2026-06-21 · **Subteam 1 van 4 (eigenaar noordster)**
**Kadert**: subteams 2 (nieuws), 3 (tool-review), 4 (bezoeker-ervaring).
**Leidend**: `CLAUDE.md` (ervaringsmandaat) + `docs/STYLEGUIDE.md` (kosmische diepte). Toetssteen overal:
**lage operationele last + stabiliteit** (solo-operator, mantelzorg-gebonden) en *"verrast dit iemand
die dagelijks met AI bouwt?"*.

> **TL;DR** — Dit is geen directory van mensen die "iets met AI doen". Het is een **levende kaart van het
> scherpste AI-netwerk van NL/BE waar een agent voor jou doorheen werkt**. De unieke asset is de **graaf**
> (de makers + hun werk + hun vraag/aanbod) en het unieke mechanisme is **agency over die graaf, bezorgd
> in de tool waar het lid al zit (MCP)**. Niemand anders heeft die combinatie. Noordster-metric =
> **gegronde verbindingen die anders niet waren ontstaan**.

---

## 1. Kernbelofte

### Eén zin
**De Wereld van AI laat de scherpste AI-makers van NL/BE elkaar vinden en versterken — een agent doet
het zoekwerk, jij beslist.** Het is een netwerk dat *voor je werkt*, niet een gids die je doorbladert.

### Wat hier te *halen* is dat nergens anders bestaat
1. **Toegang tot de juiste mensen, vóór-gefilterd door wie er al ín zit.** Niet "alle AI-mensen", maar
   precies déze besloten kring (begonnen als WhatsApp-groep van Bart Ensink / Hendrik van Zwol c.s.).
   De waarde is de samenstelling, niet de schaal.
2. **Een agent met agency over een graaf die niemand anders heeft.** Vraag/aanbod, domein-aangrenzendheid,
   en wie nieuw is — dat is gestructureerde data waar de concierge + Scout op redeneren. Een LinkedIn-zoek
   of een Notion-lijst kan dit niet: zij hebben de graaf niet en geen agent erbovenop.
3. **Het komt naar je toe in jouw eigen tool.** Via de MCP-server praat je met dewereldvan vanuit Claude
   Code / Cursor: profiel bouwen, makers zoeken, intro's voorstellen — nul context-switch. Het netwerk
   leeft waar de aandacht van een AI-bouwer al de hele dag is.

### (a) Eerste bezoeker — niet-lid, komt via WhatsApp, mobiel
> **"Dit is waar de scherpste AI-makers van NL/BE zitten — en je ziet binnen 20 seconden waarom je erbij wil."**

Belofte: in één scroll begrijpt de bezoeker (1) wíé hier zit (concrete makers + hun werk, niet abstracte
claims), (2) dát het slim is (de demo bouwt vóór je ogen een profiel uit een link — `/demo`, Nova
Belmonte), en (3) wat de volgende stap is (word lid → je eigen profiel staat in minuten). Geen formulier,
geen uitleg-lap. *Bewijs door te tonen, niet door te beweren.*

### (b) Lid
> **"Onderhoud één profiel; het netwerk werkt voor je terwijl je weg bent."**

Belofte: je bouwt je profiel in een gesprek (links plakken → de agent vult 'm), en daarna **brengt de
agent jou kansen** — een match (iemand zoekt wat jij maakt), een nieuwe maker in jouw domein, een
intro-voorstel — gegrond, klein, op het juiste moment, pull in je eigen tool of in de canvas. Je houdt
de regie (elke verbinding is consent-gepoort; één klik wist alles). De op-last voor het lid is bijna nul;
de intelligentie zit aan onze kant.

---

## 2. Bezoekersreis + wow-momenten

Wow ≠ alleen motion. De stijl (`cosmic.css`) is de *drager*; de **verrassing zit in de intelligentie en
de gegrondheid** — het systeem doet onverwacht slim werk en het klopt altijd (anti-hallucinatie). Vijf
momenten, in volgorde van de reis:

| # | Moment | Wow-mechanisme (niet "het beweegt mooi") | Hergebruikt wat er staat |
|---|--------|------------------------------------------|--------------------------|
| **W1** | **Landing (publiek, mobiel)** | Levende constellatie van *échte* makers — elke ster is een echt lid; de bezoeker voelt de samenstelling, niet een marketingclaim. "X van jullie staan er al" als sociale bewijskracht. | teaser-canvas + `_cosmic_*`; OG-tags bestaan |
| **W2** | **De demo bouwt een profiel vóór je ogen** (`/demo`) | Je geeft (of de replay toont) een link → "site scannen ✓" → headline/bio/projecten **materialiseren één voor één** uit "een website". De bezoeker snapt het mechanisme zonder uitleg. Gescript = nul AI-kosten, altijd-aan, indexeerbaar. | `/demo` live (Nova Belmonte, v0.20.0) |
| **W3** | **Eerste login → profielbouw in een gesprek** | Geen leeg formulier: "Heb je een website? Dan scan ik die vast." Eén link → compleet, kloppend profiel met echte beelden + cover. De wow is dat het *klopt en compleet is*, niet dat het glanst. | `profile_builder`-surface + AI-profielbouw (live) |
| **W4** | **Discovery: "ik zoek je even op"** | De agent speurt het lid online op, lost naamgenoten op (disambiguatie = de moat), en crystalliseert echt werk/vermeldingen op het profiel — live-tail, terugkeer-view, ≥90 auto met undo. Verbazing = *het systeem deed werk voor je terwijl je toekeek*. | `footprint_service` + `DiscoveryRun` (live) |
| **W5** | **De agent brengt een kans (Scout/match)** | "Terwijl je weg was vond ik 2 dingen." Eén gegronde match of intro-voorstel — in je eigen AI-tool (MCP) of in de canvas. Verbazing = *initiatief + het klopt*, niet ruis. Eerlijk "deze week niets" als er niets is. | `match_service` + MCP + Scout-PRD |

**Hoe verbazen we keer op keer (niet eenmalig)?** Drie ingebouwde herhaalmechanismen, allemaal al
deels aanwezig:
- **Per-bezoek variatie** in motion/constellatie (reveal-mood + constellatie-mood, v0.49.0) → het voelt
  nooit twee keer identiek, zonder dat we per scherm nieuw werk doen.
- **Progress-bewuste affordances** (`DiscoveryRun.passes`) → de interface *begrijpt wat je al deed* en
  biedt de volgende, verse stap aan in plaats van een dode knop. Dat is "superslim" als gedrag.
- **De graaf groeit** → elke nieuwe maker maakt de volgende Scout-/match-uitkomst rijker. De wow schaalt
  mee met de community in plaats van te slijten.

---

## 3. Positionering — de scherpe hoek

**Verschil met een generieke AI-startup-showcase / directory:**

| Zij | Wij |
|-----|-----|
| Een **lijst** die je doorbladert; jij doet het zoekwerk. | Een **agent** doet het zoekwerk; jij beslist. |
| Open/iedereen → ruis, lage signaalwaarde. | Besloten, gecureerd door wie er al zit → hoge signaalwaarde. |
| Statische profielen die verouderen. | Profielen die de agent **zelf vult/verrijkt** (profielbouw + Discovery). |
| "Kom naar onze site." | "Het komt naar jou — in je eigen AI-tool (MCP)." |
| Connectie = e-mailadres kopiëren. | Connectie = **gegrond intro-voorstel**, consent-gepoort, één klik. |

**De moat, in één regel:** *agency over een graaf die niemand anders heeft, bezorgd waar het lid al zit.*
De graaf (scherpste AI-makers + werk + vraag/aanbod) is niet te kopiëren zonder dezelfde mensen; de
disambiguatie-engine (Discovery) en de gegronde, anti-hallucinatie-tooling zijn het uitvoerende verschil.

**Bewust géén** algemene AI-nieuwssite, géén tool-marktplaats, géén open community-forum. Dat zijn
commodities met hoge op-last. Onze nieuws- en tool-elementen bestaan *in dienst van de graaf en de
makers* (zie §5), niet als zelfstandige producten.

---

## 4. Noordster-metric

**Hoofdmetric: aantal gegronde verbindingen dat anders niet was ontstaan.**
Operationeel = **geaccepteerde intro's** (`Connection` met wederzijds akkoord, consent-poort gepasseerd)
per maand. Dit meet precies de kernbelofte ("elkaar vinden en versterken"), is gegrond in bestaande
data (geen nieuwe instrumentatie), en is robuust tegen ijdelheid: een like of pageview telt niet — alleen
een echte, beiderzijds gewilde verbinding. **Past bij lage op-last**: het getal valt af te lezen uit de
`connection`-tabel; geen analytics-stack nodig.

**Support-metric 1 — Activatie: % goedgekeurde leden met een compleet, gepubliceerd profiel.**
Zonder gevulde profielen heeft de graaf geen substraat; dit is de voorwaarde voor de hoofdmetric en
sluit aan op de lopende activatie-koers ("eerst zoveel mogelijk leden een profiel"). Afleesbaar uit
`profile.completeness` + zichtbaarheid.

**Support-metric 2 — Agent-precisie: acceptatie-ratio van wat de agent aanreikt** (matches/Scout-items/
Discovery-findings die een lid *laat staan / accepteert* vs. afwijst). Dit is de KILL-bewaker: zakt de
precisie, dan wordt de agent ruis voor experts (netto negatief) en valt 'm terug op confirm-everything.
Eén cijfer, periodiek met de hand af te lezen — geen dashboard-onderhoud.

> Waarom niet "actieve leden" of "pageviews" als noordster? Afgewezen: meet aanwezigheid, niet waarde —
> een gezond besloten netwerk kan rustig zijn en tóch waardevol (zie de Scout-math: vroeg rustige weken
> zijn correct gedrag, niet falen). De verbinding is de waarde-eenheid.

---

## 5. Wat dit betekent voor de andere streams

De noordster ("agent + graaf, gegrond, lage op-last") is de toetssteen voor subteam 2–4. Concreet kader:

### Subteam 2 — Nieuws
- **Rol**: nieuws bestaat *in dienst van de makers en de graaf*, niet als algemene AI-nieuwsfeed (dat is
  commodity + hoge op-last). De sterkste vorm is **nieuws óver/ván leden** (interviews, artikelen die ze
  schreven) — dat verrijkt profielen en voedt de Discovery-media-pass. Bouw op de bestaande `Post`-entiteit
  (kind=nieuws, rol-badge), niet op een tweede systeem.
- **Toets**: voegt een nieuwsitem signaal toe over een *lid/de graaf*, of is het generieke ruis? Bij ruis →
  niet doen. Lage op-last = geen redactie-verplichting; leden + Discovery vullen het, admin verbergt alleen.

### Subteam 3 — Tool-review
- **Rol**: tools zijn een **lens op makers** ("wie werkt waarmee"), niet een onafhankelijke marktplaats/
  reviewsite. De bestaande tool-catalogus (`tool` + `profile_tool` M2M, filter op tool/toolset) is het
  substraat: een tool-review hoort te leiden naar *de leden die ermee bouwen* en naar matchmaking-signaal,
  niet naar een sterrenrating-product met onderhoudslast.
- **Toets**: versterkt dit het vinden-van-de-juiste-maker, of bouwen we een tweede product met eigen
  op-last? Bij het laatste → herkaderen naar graaf-signaal.

### Subteam 4 — Bezoeker-ervaring
- **Rol**: eigenaar van W1→W3 (landing → demo → eerste login) met het scherpe onderscheid **publiek vs.
  lid** (anon = crawlbare showcase/SEO + ontdekken; lid = agent-shell). De publieke kant moet in 20s de
  kernbelofte bewijzen *door te tonen* (W1/W2), niet door tekst. PREVIEW-banner eraf bij publieke launch;
  evt. apex-cutover teaser→app.
- **Toets**: bewijst elk publiek scherm de belofte via de ervaring/intelligentie (constellatie van echte
  makers, demo die bouwt), of is het "een mooie pagina"? Eén identiteit, geen tweede look.

---

## 6. Aanbeveling

**Vast te leggen als noordster:** *De Wereld van AI is een levende kaart van het scherpste AI-netwerk van
NL/BE waar een agent met agency over de graaf voor het lid doorheen werkt — gegrond, in de tool waar het
lid al zit, met de gegronde verbinding als waarde-eenheid.* Meet succes aan **geaccepteerde intro's/mnd**
(hoofd), met **profiel-activatie** en **agent-precisie** als support. Dit cementeert wat al gebouwd is
(concierge, Discovery, matchmaking, MCP, Scout-PRD) tot één coherent verhaal en geeft subteam 2–4 een
harde toets: *versterkt dit de graaf + de agent, tegen lage op-last?*

**Ik leg dit zo vast en geef het door als kader aan subteam 2–4, tenzij je vetoert.**

### Verworpen alternatieven (1 regel elk)
- **"Publieke AI-showcase/directory voor heel NL/BE"** — verworpen: open = ruis + hoge curatie-last + geen
  moat; de besloten samenstelling ís de waarde.
- **"AI-nieuws- en tool-platform"** — verworpen: commodity-producten met redactie-/onderhoudslast, botsen
  met lage-op-last en met de graaf-moat; nieuws/tools horen ondergeschikt aan de makers.
- **"Community-forum / sociaal netwerk"** — verworpen: WhatsApp blijft het chatkanaal (bewust buiten scope);
  moderatie-last + retentie-druk passen niet bij een solo-operator.
- **"Vanity-metric (actieve leden / pageviews) als noordster"** — verworpen: meet aanwezigheid, niet de
  waarde-eenheid (de verbinding); een gezond besloten netwerk mag rustig zijn.

### Risico's
- **Netwerk-dichtheid (grootste).** De agent-waarde schaalt met de graaf; bij een dunne community vindt de
  Scout/match vaak weinig. *Mitigatie*: activatie-koers eerst (support-metric 1), eerlijk "deze week niets"
  i.p.v. geforceerde items, niet rijk-rekenen op vroege weken.
- **Agent-precisie / ruis voor experts.** Een verkeerde match of false-positive-finding is bij dit publiek
  duurder dan bij een doorsnee-doelgroep. *Mitigatie*: hoge drempels + confirm-poorten + grounding +
  support-metric 2 als KILL-bewaker.
- **"Mooi maar niet slim"-regressie** (de herhaalde kern-feedback). *Mitigatie*: elke nieuwe pagina toetst
  aan W1–W5-mechanismen (intelligentie + gegrondheid), niet alleen aan motion.
- **Op-last-creep via nieuws/tools** (subteam 2/3). *Mitigatie*: §5-toets — geen zelfstandig product met
  eigen redactie-/moderatielast; alles ondergeschikt aan de graaf, leden vullen, admin verbergt alleen.
- **Privacy/AVG bij een publieke showcase.** *Mitigatie*: default besloten, per-profiel zichtbaarheid,
  `noindex` op besloten, één-klik-volledig-wissen (al live).
```
