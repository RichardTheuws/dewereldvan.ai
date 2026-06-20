# PRD — De Scout (de concierge die voor je werkt terwijl je weg bent)

**Status**: ter goedkeuring · **Versie doc**: 2.0.0 · **Datum**: 2026-06-20
**Aanleiding**: (1) de platform-audit-FAIL "nul terugkeer-trigger na onboarding";
(2) Richards eis: écht vooruitstrevend worden i.p.v. bestaande patronen combineren.

> **v2.0 pivot (Richard, 2026-06-20): GEEN e-mail.** "E-mail is een achterhaald
> concept" — en een re-engagement-digest is precies het bestaande patroon. De Scout
> levert **pull-only, in de eigen surfaces van het lid**: in hun eigen AI-tool via de
> MCP-server, en als briefing in de canvas. Dat is 2026-native, uniek van ons (de
> graaf + de MCP), en het laat de hele opt-in/spam-vraag verdampen.

## Eén zin
De **Scout** is de proactieve modus van de bestaande concierge: een staande, per-lid
agent die de ledengraaf afspeurt op wat voor *jou* relevant is en je een **klein,
gegrond setje uitkomsten** brengt — **in je eigen AI-tool (via MCP)** en als briefing
in de canvas, elk als **één-klik-actie**. Hij handelt nooit zonder jouw klik; hij
brengt kansen, jij beslist.

## Waarom dit de sprong is (en niet weer een feature)
Alles tot nu is reactief/pull en bekend patroon. De Scout voegt het enige toe dat een
concurrent niet kan kopiëren: **agency over een graaf die niemand anders heeft**
(de scherpste AI-makers van NL/BE + hun werk + vraag/aanbod), **bezorgd in de tool
waar het lid de hele dag al zit**. Het kwaliteitsverschil:
1. **Uitkomsten, niet meldingen.** De hoogwaardige item-soort is een *intro-voorstel*:
   "ik denk dat jij en X elkaar moeten spreken omdat … — zal ik je voorstellen?" →
   één klik → de bestaande, consent-gepoorte intro-flow (`stel_voor` zit al in de MCP).
2. **Bezorgd in hun eigen agent.** Niet "wij sturen je iets," maar "jouw eigen
   AI-assistent haalt kansen uit het netwerk." Dát is de 2026-native sprong — en hij
   versterkt de activatie-koers (nóg een reden om de MCP te koppelen).
3. **Continuïteit.** Bij terugkeer in de canvas begroet de concierge je met wat hij
   vond: "Terwijl je weg was vond ik 2 dingen voor je." Een agent met geheugen + initiatief.

**Géén tweede persona.** De Scout is dezelfde concierge, andere modus. Eén stem.

## Niet-doelen (v1)
- **Geen e-mail** (bewust geschrapt — zie pivot). Geen push-notificaties/web-push.
- Geen ML-aanbevelingsmodel/pgvector — goedkope SQL-kandidaten + één gegronde
  Claude-call per lid (zelfde patroon als `match_service`).
- Geen zelf-onderhoudende profielen / vrije "watch-list" in v1 (Fase 3).
- Geen auto-verzonden intro's — nooit. Alles is tonen + 1-klik bevestigen.

## Eerlijke math: netwerk-dichtheid
De waarde schaalt met dichtheid. Bij een dunne community vindt de Scout vaak weinig en
zegt hij eerlijk "deze week niets" (geen geforceerde items). Dat is correct gedrag.
Implicatie: de Scout botst NIET met de activatie-koers maar versterkt 'm — pull-bezorging
in de eigen tool geeft geactiveerde leden een reden om terug te komen, en intro-voorstellen
creëren het netwerk-effect. Verwacht vroeg rustige weken; niet rijk-rekenen.

## Bezorging (pull-only, in de surfaces van het lid)
- **Primair: het eigen AI-tool van het lid (MCP).** Een MCP-tool
  `wat_is_er_voor_mij` (alias `scout`) die het gegronde rapport teruggeeft (matches,
  nieuwe makers in jouw domein, intro-voorstellen, relevante events), plus de
  bestaande `stel_voor` om te handelen. Het lid (of zijn agent) vraagt het op wanneer
  het uitkomt — geen kanaal om te checken; het komt waar hun aandacht al is. Optioneel
  later: een MCP-**resource** (`scout://mij`) die agents kunnen lezen/subscriben.
- **Secundair: in-canvas briefing** bij terugkeer (Fase 2): de canvas toont het laatste
  rapport; de concierge kan het uitspreken. Zelfde inhoud, andere surface.
- **Geen opt-in/consent-knop nodig**: pull-only → niets ongevraagd. De MCP-koppeling
  (token genereren) ís al een bewuste opt-in; de canvas is login-gated. Daarmee is de
  eerdere opt-in/opt-out-e-mailvraag van de baan.

## Het ontwerp

### Interesse-model = je profiel (zero-config, organisch)
Geen nieuw "wat wil je volgen"-formulier. De Scout leidt relevantie af uit wat er al is:
**offerings** (wie wil wat jij maakt), **needs** (wie biedt wat jij zoekt), **tags/domein**
(aangrenzende makers), en **`member_memory`** (rijkere context voor de framing).

### Assembler (twee lagen, grounding-poort) — lazy + 24u cache
Spiegelt het bewezen match-patroon: goedkope kandidaten → gegronde synthese. Wordt
**lazy** opgebouwd wanneer de MCP-tool wordt aangeroepen of de canvas opent, en
**gecachet** als `ScoutDigest` (TTL ~24u) zodat een herhaalde vraag dezelfde dag geen
nieuwe Claude-call doet. Geen nachtelijke batch-bezorging nodig (de nachtjob mag het
optioneel pre-warmen, maar het hoeft niet).
1. **Deterministisch verzamelen (SQL, geen LLM)** — sinds `scout_last_run_at`:
   - nieuwe **matches** (`match_service`, status=new, ≥ `MATCH_MIN_SCORE`);
   - **nieuwe makers in jouw domein** (approved recent, tag-overlap ≥ 1);
   - **nieuwe needs die matchen op jouw offerings** ("iemand zoekt nu wat jij maakt");
   - **inkomende intro's** die op je antwoord wachten;
   - **relevante agenda/nieuws** in jouw domein.
2. **Eén Claude-call per lid (gated op `AI_ENRICH_ENABLED`)** die UITSLUITEND uit de
   kandidaten kiest wat écht de moeite waard is, een korte gewone-taal framing schrijft,
   en per intro-voorstel de waarom-zin formuleert. **Grounding-poort**: kandidaten mét
   echte ids; een item zonder geldige id valt weg (zoals bij match/concierge).

### Relevantiebar + caps (respecteer expert-tijd — kritisch)
Liever 1 raak ding dan 5 middelmatige. Harde drempel per signaal-soort; **top 3 items**
max; **max 1–2 intro-voorstellen**; niets boven de bar → een eerlijk "deze week niets".

### Datamodel (één migratie)
- `ScoutDigest` (FK `member_id` CASCADE): `created_at`, `body` (framing-tekst),
  `items` (JSON: `[{type, ref_id, title, action_url}]`), `seen_at` (nullable). Het
  gecachete rapport dat zowel de MCP-tool als de canvas rendert; AVG: mee gewist met de
  member-row.
- `member.scout_last_run_at` (datetime, nullable) — cache-/venster-stempel.
- (Geen `digest_cadence`/opt-out-veld — er is geen uitgaand kanaal.)

## Ervaring & copy
- Toon: "de agent werkte terwijl je weg was" — continuïteit + initiatief. Eenvoudige,
  directe NL-taal (geen zweverigheid). Via MCP: compacte, gestructureerde tekst die
  goed leest in een editor/agent.
- Elk item = één klik naar een echte actie (intro-voorstel → bestaande intro-flow;
  nieuwe maker → profiel; event → agenda).

## AVG / consent / vertrouwen (hoogst zorgvuldig)
- **Pull-only**: niets wordt ongevraagd verstuurd; geen e-mail, geen push.
- **Intro-voorstellen sturen NOOIT zelf iets**: voorstel → klik → de bestaande
  consent-gepoorte intro-flow (ontvanger akkoord vóór contact gedeeld).
- **Zichtbaarheid respecteren**: alleen makers die het lid mag zien
  (`_public_base`/`can_view`) — besloten/geschorst lekt per constructie niet.
- **MCP-scope**: het rapport is strikt gescoped tot het geauthenticeerde lid (zoals de
  bestaande MCP-tools).
- **Wissen**: `ScoutDigest` + stempel mee gewist in `delete_member_completely`.
- Pending/geschorst → geen Scout-rapport.

## Edge cases
- Nieuw lid / lege graaf → niets boven de bar → eerlijk "deze week niets" (geen vulling).
- Lid zonder offerings/needs/tags → zwak model → val terug op "opvallende nieuwe makers"
  of een eerlijke leegte.
- Nooit jezelf aanbevelen; je eigen nieuws niet als "nieuws over jou" tenzij zo gelabeld.
- Geen intro voorstellen aan iemand met wie al een `Connection` bestaat (elke status) of
  een `MatchSuggestion` die acted/dismissed is (dedup).
- Grounding: elk item traceert naar een echte rij; het model kiest/framet, verzint nooit.
- MCP-tool zonder gekoppeld lid / canvas zonder login → geen rapport.

## Fasering
- **Fase 1 (v1)**: assembler (lazy + cache) + `ScoutDigest`-model + de MCP-tool
  `wat_is_er_voor_mij` (incl. intro-voorstellen, met `stel_voor` om te handelen). Levert
  de bezorging dáár waar het publiek al zit + de agentische wow, zonder e-mail.
- **Fase 2**: in-canvas briefing-surface bij terugkeer + concierge spreekt 'm uit
  ("Terwijl je weg was…") + de concierge biedt de Scout organisch aan. Hergebruikt de
  Fase-1-assembler 1:1.
- **Fase 3 (later)**: zelf-onderhoudende profielen, vrije "vertel de Scout wat te volgen",
  generatieve serendipiteit, en — áls clients het ondersteunen — een echte push via
  MCP-resource-subscriptions (geen e-mail).

## Succescriteria & KILL-condities
- **Succes**: een lid krijgt zonder zoeken één gegronde, relevante kans aangereikt die het
  anders had gemist (gemeten: kliks/acceptaties op intro-voorstellen; `wat_is_er_voor_mij`-
  aanroepen die tot een actie leiden).
- **KILL** als na een eerlijke proefperiode de precisie laag is (voorstellen worden
  structureel genegeerd) → ruis voor experts = netto negatief → Scout uit, niet doorduwen.
  Conservatief starten (hoge bar, kleine caps).

## Hergebruik-audit (wat staat er al — ~85%)
| Bouwsteen | Status |
|---|---|
| MCP-server + per-lid-scope + `stel_voor`/`mijn_matches` | `mcp_server` ✓ |
| match-kandidaten + drempel | `match_service` ✓ |
| intro / consent-poort | `connection_service` ✓ |
| per-lid geheugen (framing) | `member_memory` ✓ |
| nieuwe makers / events / nieuws | `members_service` / `post_service` ✓ |
| in-canvas surface/concierge (Fase 2) | concierge-surface + `nudge_service` ✓ |
| **nieuw** | `ScoutDigest`-model, `scout_service` (lazy assembler + cache), MCP-tool `wat_is_er_voor_mij`, in-canvas briefing (Fase 2) |

## Beslissingen
- **Bezorging = pull-only, MCP + canvas; GEEN e-mail** (Richard, 2026-06-20). De eerdere
  opt-in/opt-out-e-mailvraag is daarmee vervallen.
