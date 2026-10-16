# PRD — De hub: vindbaar voor opdrachtgevers én AI-assistenten

**Status**: GOEDGEKEURD (route) — Richard 2026-10-16 ("direct aan de slag"); fase 1 in aanbouw
**Versie**: 0.1.0
**Datum**: 2026-10-16
**Raakt**: `app/routers/profiles.py`, `members.py`, `seo.py`, `gids.py`, `app/mcp_server.py`,
`app/services/seo_service.py`, `visibility.py`, `notification_service.py`, nieuwe `inquiry`-model/-service,
`docs/vision/01-noordster.md`
**Volgt uit**: hub-onderzoek 2026-10-16 (live-data + markt-scan, zie §1).

---

## 1. Aanleiding

dewereldvan.ai moet de plek worden waar elk AI-bureau, elke trainer en elke developer in NL/BE **op wíl
staan**. Dat is het nu niet. Verdict op de huidige hub: **FAIL**.

**Live-data (prod, 2026-10-16)**: 24 leden (21 uit juni, sinds augustus nul aanwas), laatste mens-login
2026-08-08, 7 publieke profielen, 0 geaccepteerde verbindingen. Alleen de AI-nieuwscuratie draait.

**Waarom niemand er wil staan — er komt niets terug voor wie erop staat:**
- **Geen leads**: een bezoeker die "aanspreken" kiest, krijgt "word lid" (`concierge.py:458`). Een
  opdrachtgever kan niemand bereiken.
- **Geen backlinks**: elke uitgaande link is `nofollow`.
- **Geen statistieken**: een lid ziet niet of z'n profiel bekeken wordt.
- **Geen AI-vindbaarheid**: MCP vraagt een leden-token, geen `llms.txt`, JSON-LD alleen `Person`
  (geen `sameAs`/`Service`/`areaServed`).
- Geen regio-filter op `/leden` (de data bestaat, opt-in), geen bureau-entiteit.

**Marktkans** (scan 2026-10-16, bronnen in de sessie-notities): bestaande NL/BE-overzichten zijn
organisatie- (AIC4NL, Dealroom) of tool-gericht (RankmyAI), of je betaalt voor je plek (Clutch, Sortlist —
waar bureaus juist over klagen). Er is geen open, eerlijke gids van **mensen** in NL+BE. De sterkste nieuwe
drijfveer om ergens te staan is **gevonden worden door AI-assistenten**: bij leveranciersvragen komt ~41%
van de citaties uit sectorgidsen vs ~18% uit eigen sites (citations.press, sep 2026 — cijfer van de partij
zelf), overzichtspagina's worden vaker geciteerd dan losse profielen, en gestructureerde vermeldingen winnen
van vrije tekst. In NL/BE doet geen gids dit.

## 2. De belofte (één zin)

> **Sta op dewereldvan.ai en je wordt gevonden — door opdrachtgevers én door AI-assistenten — en je ziet
> zelf dat het werkt.**

Gratis, niet te koop, gerangschikt op wat je laat zien (niet op wat je betaalt).

## 3. Noordster-wijziging (bewuste omkering)

`docs/vision/01-noordster.md` §6 verwierp een "generieke publieke directory van heel NL/BE" en meet succes
in geaccepteerde intro's tussen leden. Dat wordt bijgesteld:

- **Blijft**: open en gastvrij, mensen centraal, de graaf/agent als intelligentie, geen scraping, geen
  vermelding zonder toestemming, privacy-poort via `visibility.py`.
- **Verandert**: de hub is wél een publieke gids — maar **alleen van wie er zelf voor kiest** (opt-in
  openbaar), niet "iedereen scrapen". De waarde-eenheid wordt **een echte aanvraag of vermelding die een lid
  oplevert**, niet alleen een intro tussen leden.
- **Nieuwe maatstaf** (hoofd): **aanvragen van buiten per maand**. Support: (1) aantal openbare, complete
  vermeldingen; (2) aandeel leden dat in de AI-steekproef genoemd wordt.

## 4. Fase 1 — scope (in deze volgorde)

### 4.1 Aanvraag door een bezoeker ("Stel een vraag aan X")
- Op een **openbaar** profiel met `open_to` gevuld (klantwerk/trainingen/spreken/interviews/samenwerkingen)
  of zonder `open_to` maar met de sectie publiek: een kaart "Stel een vraag aan <naam>". Velden: je naam,
  je e-mail, organisatie (optioneel), onderwerp (keuze uit de `open_to`-waarden van het lid + "iets
  anders"), bericht (20–2000 tekens), vinkje toestemming (gegevens alleen naar dit lid, 180 dagen bewaard).
- **Nul betaalde AI** (harde constraint). Spam-poort: Turnstile (zoals `/proef`), honeypot-veld,
  minimale invultijd, per-IP-limiet (5/24u), per-profiel-limiet (20/24u), dedupe op (e-mail, profiel,
  bericht-hash) binnen 24u.
- **Bezorging**: opgeslagen als `Inquiry`; het lid krijgt een push via z'n gekozen kanaal
  (`notification_service.notify`, Telegram) + een in-app chip. **Geen e-mail** (bestaand besluit: e-mail
  alleen voor de magic-link). Het lid antwoordt zelf vanuit z'n eigen mail (mailto met onderwerp).
- **Lid-inbox** `/aanvragen`: lijst, status (nieuw/gelezen/beantwoord/spam), "markeer als spam" (telt mee
  voor IP-blok). Inhoud wordt na 180 dagen gewist (job); de account-wis neemt aanvragen mee.
- Bezoeker ziet daarna een bevestiging met wat er gebeurt ("<naam> krijgt je vraag nu, en antwoordt je
  zelf per mail"). Geen belofte over reactietijd.

### 4.2 Leesbaar voor AI
- **`/llms.txt`**: korte beschrijving van de hub + links naar de overzichtspagina's (4.3) en naar
  `/makers.json`. Alleen openbare profielen.
- **`/makers.json`** (openbaar, read-only, gecachet): per openbaar profiel: naam, url, headline,
  disciplines, `open_to` (alleen als sectie publiek), tags, tools, regio-label (alleen als ingevuld),
  eigen site. Elke veld via `visibility.public_section_visible`.
- **MCP anoniem read-only**: zonder token alleen `zoek_makers` (en een nieuw `lijst_disciplines`) over
  **openbare** profielen; met token blijft alles zoals het is. Ratelimit per IP.
- **JSON-LD verrijkt**: `makesOffer` met `Service` per `open_to`-waarde, `hasOccupation`, `contactPoint`.
  *Gebouwd v0.112.0.* `sameAs` wacht op de "Vind me online"-strip (presence wordt nu niet bewaard) en
  `areaServed` op een publieke regio-opt-in (de Dichtbij-regio is daar niet voor gegeven).
- **Backlink**: links naar het eigen werk (projecten, builds) zijn **dofollow** op een openbaar profiel en
  de projectpagina. Affiliaties blijven `nofollow`. *Gebouwd v0.112.0* (er bestaat geen apart
  website-veld; eigen werk is de eerlijke bron).

### 4.3 Overzichtspagina's
- `/gids/<discipline>` (bouwers, trainers, video-ai, audio-ai, publicatie, design): intro-tekst
  (statisch, geen AI), de openbare leden in die discipline, filter op `open_to`, `ItemList`-JSON-LD, in de
  sitemap.
- **Regio** (*nog niet gebouwd*: de Dichtbij-regio is opt-in voor samenkomen, niet voor publieke weergave —
  eerst een eigen opt-in "toon mijn regio publiek"): `/gids/<discipline>/<provincie>` pas zodra ≥3 openbare leden in die combinatie; daaronder
  `noindex` en niet in sitemap (dunne pagina's schaden). PC2 → provincie-mapping in `geo_service`.
- Regio-filter op `/leden`.

### 4.4 Lid-dashboard "Je vindbaarheid"
- Weergaven van je profiel (laatste 30 dagen, telling per dag, bots eruit via UA-heuristiek, geen IP
  opgeslagen — alleen dag-teller), aantal aanvragen, aantal keren in `/makers.json`/MCP-resultaat.
- **AI-steekproef** (maandelijks, alleen voor openbare leden): we vragen Claude met web-search 2–3
  realistische vragen ("wie geeft AI-trainingen in <regio>?", "<discipline> NL") en noteren of het lid
  genoemd wordt en of dewereldvan.ai als bron verschijnt. **Eerlijk benoemd** als "steekproef met Claude",
  niet als "ChatGPT-ranking". Kosten onder een eigen maandcap; leden-AI, dus valt niet onder de
  bezoekers-cap.

## 5. Bewust NIET in fase 1
- **Organisatie/bureau-profiel** (bureau met teamleden) — fase 2; zonder 4.1–4.4 heeft een bureau nog
  niets aan een vermelding.
- **Default openbaar** — verworpen (privacy-invariant). Wél: bij onboarding/profielbouw "openbaar en
  vindbaar" als logische keuze aanbieden met uitleg wat het oplevert.
- **Vooraf vullen met gevonden bureaus** — verworpen (AVG + eigen ethiekregels: niemand op de kaart zonder
  toestemming).
- **Betaalde/uitgelichte plekken** — verworpen: onafhankelijkheid ís het verkoopargument.
- Reviews/endorsements, KvK-verificatie, boekingen voor workshops — later, op basis van vraag.

## 6. Edge cases
| Situatie | Gedrag |
|---|---|
| Profiel wordt besloten terwijl er aanvragen open zijn | Inbox blijft voor het lid; formulier verdwijnt; nieuwe POST → 404 |
| Lid geschorst / gewist | Formulier weg; bij wissen gaan aanvragen mee (account_deletion) |
| Lid heeft geen push-kanaal | Alleen in-app chip; dashboard toont "koppel Telegram om direct te horen" |
| Turnstile niet geconfigureerd | Formulier uit (veilige default, zoals `/proef`), kaart toont "even niet beschikbaar" |
| Dubbele submit (race) | Idempotent via savepoint-patroon ([[dewereldvan-idempotent-race]]) |
| Bot vult honeypot / te snel | Stil 200 met bevestiging, niets opgeslagen |
| Lid stuurt zichzelf een aanvraag (ingelogd) | Toegestaan maar niet geteld in dashboard |
| Bezoeker-e-mail ongeldig | Validatie-fout, geen opslag |
| `public_sections` verbergt `open_to` | Onderwerp-keuze valt terug op "iets anders"; JSON/JSON-LD tonen geen `open_to` |
| Discipline-pagina zonder openbare leden | Nette lege staat + uitnodiging "werk je zelf als …? Zet je profiel op openbaar"; `noindex` |
| Regio-combinatie <3 leden | `noindex`, niet in sitemap, wel bereikbaar |
| Profielweergave door het lid zelf / admin | Niet geteld |
| AI-steekproef-cap bereikt | Rest van de maand overgeslagen, dashboard toont laatste meting + datum |
| MCP anoniem misbruik | Per-IP-limiet; alleen openbare velden, dus geen datalek mogelijk |

## 7. Succescriterium fase 1
Gemeten 2026-12-31: **≥15 openbare, complete vermeldingen** (nu 7), **≥5 echte aanvragen van buiten**
(nu 0), en elke openbare vermelding heeft minstens één AI-steekproef-meting. Halen we na de uitnodigings-
ronde (zie §8) minder dan de helft hiervan, dan is de propositie niet sterk genoeg → herzien, niet
doorbouwen.

## 8. Na fase 1 — activatie (geen code)
De bouw lost het stilstaan niet alleen op. Zodra 4.1–4.4 live staan: de oude WhatsApp-groep en nieuwe
bureaus/trainers persoonlijk uitnodigen met de belofte uit §2 en een eigen AI-steekproef als haakje.
