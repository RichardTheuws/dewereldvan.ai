# PRD — De Pivot: Open, Multidisciplinair Maker-platform met Showcase

**Versie**: 0.1.0
**Datum**: 2026-06-22
**Status**: 🟡 APPROVAL PENDING (geen implementatie vóór akkoord — Gouden Regel 2)
**Vervangt**: de visie-/doelgroep-/toegang-delen van `docs/PRD.md` (v0.1.0, WhatsApp-groep-MVP).

---

## 1. De pivot in één zin

dewereldvan.ai is ontstaan uit één WhatsApp-groep, maar wordt **een open plek voor iedereen
met AI-affiniteit — uit álle disciplines — om hun eigen werk te tonen en onderling te
verbinden.** De toegangspoort blijft bestaan, maar **filtert spam, niet mensen**: niemand
wordt ooit als "niet geschikt" gekwalificeerd.

Drie lagen, één geheel:
1. **Toegang zonder oordeel** — open registratie, AI-spam-triage, auto-welkom voor echte makers.
2. **De multidisciplinaire showcase** — je profiel is een agent-gebouwde etalage van echt werk,
   in de vorm die bij jouw discipline past (project, workshop, showreel, audio, galerij…).
3. **Verbinding** — de showcase voedt matchmaking/discovery: makers vinden en bereiken elkaar.

De showcase is de spil: hij maakt de open, multidisciplinaire visie wáár én is tegelijk het
anti-spam-signaal (een echt portfolio bouwen is precies wat een spammer niet doet).

---

## 2. Doelgroep

**Iedereen met AI-affiniteit**, breed maar thematisch coherent: bouwers/coders, trainers en
educatoren, audio- en video-AI-makers, designers/artists, onderzoekers, beleidsmakers, én
oprecht nieuwsgierigen. Het thema (AI) is de enige grens; er is **geen prestige-lat**. De poort
filtert spam/bots + duidelijk off-topic — verder is iedereen welkom.

> Dit vervangt de oude framing "de scherpste AI-makers van NL/BE" als *toegangscriterium*. Die
> blijft wél de *toon/ambitie* van de ervaring (het mandaat "verbaas iedereen"), maar is geen
> drempel meer om binnen te komen.

---

## 3. Laag 1 — Toegang zonder oordeel

**Principe**: lidmaatschap is losgekoppeld van oordeel. De enige afwijzing die bestaat is
"dit is spam", neutraal geframed als een systeem-grens — nooit als een waardeoordeel over een mens.

### 3.1 De flow
1. **Open registratie** (naam + e-mail), thematisch geframed ("voor iedereen die met AI bouwt,
   leert, of er beleid over maakt"). Geen prestige-vraag.
2. **De agent-onboarding ís de poort.** De agent verwelkomt en helpt direct het profiel bouwen
   ("vertel kort wat je met AI doet, of plak een link"). Een echt profiel maken = de toelating.
   Spam komt zo ver niet; een echt mens zeilt erdoorheen. Poort en warme eerste indruk = hetzelfde moment.
3. **AI-spam-triage (geen prestige-oordeel).** Bij een nieuw profiel scoort een AI-call alleen op
   **spam-/bot-waarschijnlijkheid** (gibberish, link-spam, incoherentie, bekende bot-patronen) en
   levert een advies + reden: `welkom` · `even kijken` · `lijkt spam`. De AI oordeelt **nooit** over
   "past bij de community".
4. **Auto-welkom + flag-review** (de gekozen vertrouwen-default): een echt (niet-spam) profiel =
   direct binnen. Alleen `even kijken`/`lijkt spam` belandt in jouw lichtgewicht review-queue
   (één-klik). De "approval" blijft dus bestaan — maar alleen waar nodig.

### 3.2 Genadige toestanden (nooit een hard "rejected = ongeschikt")
- **welkom** → binnen; de welkomst-/login-mail (bestaat al, v0.69.0) wordt pure verwelkoming.
- **even kijken** → neutrale, tijd-gebonden "we kijken even mee"-staat; het lid kan ondertussen
  al z'n profiel bouwen. Geen negatief signaal.
- **lijkt spam** → stil niet-geactiveerd, mét een neutrale ontsnapping ("klopt dit niet? mail ons")
  zodat een vals-positief mens zich kan herstellen. **Nooit** de woorden "niet geschikt".

### 3.3 Gelaagde zichtbaarheid i.p.v. binair in/uit
Iedereen die geen spam is, is "in" — maar nieuwkomers zijn zichtbaar **"nieuw"** (de tijd-bewuste
gloed, v0.70.0) en standing groeit door deelname, niet door een poortwachter. Niemand wordt
buitengesloten; aanzien wordt verdiend, niet vergund.

### 3.4 Microcopy
Overal simpel, warm, eerlijk (Styleguide §microcopy). De poort wordt uitgelegd als anti-spam,
nooit als kwaliteitslat. Geen zweverige taal; wel heldere, gewone woorden.

---

## 4. Laag 2 — De multidisciplinaire showcase

**Principe**: elke discipline toont werk in zijn eigen native vorm. Niet één tekstprofiel-mal, maar
een flexibele etalage. Niet per discipline hardcoden — één **typed werk-item-model** dat de agent
intelligent vult uit een link.

### 4.1 Werk-item-model (AUGMENT van `Offering`, geen herbouw)
`Offering` is vandaag al een werk-item ("wat ik maak": `url` + `screenshot_url` + `summary`). We
**generaliseren** het met een `kind`:

| kind | discipline (voorbeeld) | native rendering |
|------|------------------------|------------------|
| `project` (default) | coders | screenshot-hero + AI-samenvatting (bestaat) |
| `workshop` / `event` | trainers/educatoren | titel + datum + locatie/online + aanmeld-/terugkijk-link |
| `video` | video-AI | embedded speler (oEmbed: YouTube/Vimeo) — de showreel |
| `audio` | audio-AI | embedded speler (oEmbed/`<audio>`) — de showreel |
| `gallery` | design/artists | beeld-galerij |
| `writing` | onderzoek/beleid | publicatie/post-kaart |
| `link` | overig | nette unfurl-kaart |

Bestaande rijen = `project` (additieve migratie, niets breekt). Matchmaking (offering↔need) blijft
intact: een werk-item is nog steeds "wat ik maak/bied".

### 4.2 De agent als invuller ("verbaas door intelligentie")
Je plakt een link; de **agent herkent het type** (YouTube-showreel / workshop-pagina / GitHub-repo /
SoundCloud-set) en rendert het **native** via oEmbed/unfurl — geen upload-formulier per vakgebied.
Hergebruikt de bestaande patronen: `browser_render_service` (screenshot/markdown), `visitor_url_card`
(unfurl), de SSRF-guard, en de levende AI-profielbouw. Embeds via oEmbed-endpoints; faalt een embed,
dan een nette link-fallback (nooit een gebroken speler).

### 4.3 Discipline-facet (voor discovery, niet als poort)
Een **zelf-gekozen, meervoudige** discipline-facet op het profiel (coder · trainer · audio · video ·
design · research · policy · overig). Niet gegated, niet beoordeeld — puur om de gids/matchmaking te
voeden ("vind een video-AI'er", "trainers in de buurt"). Implementatie: lichte uitbreiding op het
bestaande tag-mechanisme of een dedicated veld (beslissen in de bouwfase).

---

## 5. Laag 3 — Verbinding (grotendeels gebouwd, wordt rijker)

De rijkere showcase voedt wat er al ligt: matchmaking (`match_service`), intro's
(`connection_service`), de levende graaf/constellatie, en discovery (`footprint_service`). Nieuwe
discovery-kansen: matchen op discipline + werk-type ("wie maakt video?", "ik zoek een workshop over
RAG"). Geen nieuw systeem — augmentatie van de bestaande lagen.

---

## 6. Datamodel-impact (AUGMENT)
- `Offering` → `kind` (enum, default `project`) + `embed_url`/`embed_html` (oEmbed) + optioneel
  `event_at`/`location` voor workshop/event. Additieve Alembic-migratie; bestaande rijen = `project`.
- `Member`/`Profile` → zelf-gekozen `discipline`-facet (meervoudig).
- Spam-triage → een `triage_status` + `triage_reason` (of hergebruik `Member.status` +
  een `AuditLog`-detail) zodat de review-queue de AI-reden toont. Veilige default: zonder
  `AI_ENRICH_ENABLED` valt de triage terug op **manueel-iedereen-reviewen** (de queue van nu).

---

## 7. Fasering (concrete bouw-volgorde, ná akkoord)

- **Fase A — Toegang herframen (geen oordeel).** Registratie/pending/approval/afwijzing-microcopy +
  genadige toestanden + welkomst-mail als verwelkoming. Géén AI nodig; pure framing + state. *Snelst,
  laagste risico, lost het "schofferen"-probleem direct op.*
- **Fase B — AI-spam-triage + auto-welkom.** Triage-call (spam-likelihood) → auto-welkom voor echt,
  flag naar de queue voor twijfel. Gegated op `AI_ENRICH_ENABLED`; KILL-fallback = manueel-reviewen.
- **Fase C — Showcase-generalisatie.** `Offering.kind` + agent-herkenning-uit-link + oEmbed-embeds
  (video/audio eerst — de grootste "dit-is-niet-voor-mijn-werk"-gaten), dan workshop/gallery/writing.
- **Fase D — Discipline-facet + discovery-verrijking.** Self-select discipline + filter/match op
  discipline en werk-type.

Elke fase: eigen tests in dezelfde sessie + browser-verificatie + deploy (zoals altijd).

---

## 8. Edge cases & risico's (vooraf benoemd)
- **Vals-positieve spam-flag** (echt mens als spam gemarkeerd): altijd een neutrale recovery-route
  ("mail ons"); de AI-flag is *advies*, jij beslist; KILL de auto-flag bij te veel false-positives →
  terug naar manueel-reviewen (engine blijft).
- **Leeg/half profiel**: geen spam, maar nog niets te tonen → "nieuw"-staat + zachte aanmoediging via
  de agent; niet afwijzen.
- **Off-topic (geen AI-affiniteit)**: neutraal "dit lijkt niet over AI te gaan — klopt dat?" (vraag,
  geen oordeel); blijft een mensbeslissing, nooit een harde "niet geschikt".
- **Embed faalt / kwaadaardige URL**: oEmbed/unfurl achter de SSRF-guard; faalt het, link-fallback;
  geen autoplay; sanitize embed-HTML (XSS).
- **NSFW/abuse in werk-items**: lichte moderatie-affordance (admin verbergen) — bestaande community-
  moderatie-lijn.
- **AVG**: zelf-gekozen discipline + showcase = expliciete eigen invoer; export/delete dekt het
  (bestaat). Embeds laden third-party content → benoem in de privacy-tekst.
- **Bestaande leden/teaser-wachtlijst**: ongemoeid; de pivot verbreedt instroom, migreert niets weg.
- **Spam-volume bij echt open**: rate-limit (bestaat) + Turnstile op registratie + de triage als
  eerste zeef vóór jouw queue.

---

## 9. Niet in scope (nu)
- Betalingen/marktplaats-transacties, native mobiele app, realtime chat (WhatsApp/Telegram blijven
  de chatkanalen), eigen video/audio-hosting (we embedden, we hosten geen media).

---

## 10. Succescriteria (het geheel)
1. Een wildvreemde met AI-affiniteit kan zich aanmelden, bouwt met de agent een showcase van echt
   werk, en is **binnen zonder ooit een oordeel over z'n persoon te krijgen** — auto-welkom als geen spam.
2. Een trainer toont een workshop, een video-AI'er een showreel, een coder een project — **elk in
   zijn eigen native vorm**, gebouwd uit een link.
3. Jouw op-last blijft laag: je reviewt alleen wat de AI als twijfel/spam markeert; de rest stroomt door.
4. Spam/bots halen de showcase niet — de effort-as-signal + triage houden het signaal hoog.
5. De gids/matchmaking wordt rijker en multidisciplinair, op hetzelfde holistische datamodel
   (geen herbouw).
</content>
