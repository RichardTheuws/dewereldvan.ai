# PRD — Footprint-presence: eigen aanwezigheid ≠ nieuws

**Status**: GEBOUWD (optie A) — v0.110.0, 2026-07-11
**Versie**: 0.1.0
**Datum**: 2026-07-11
**Raakt**: `app/services/footprint_service.py` (classifier + crystallize), discovery-flow
(`app/routers/discovery.py`, `discovery/_crystallized.html`/`_undone.html`), evt. `ProfileLink`
**Volgt uit**: de anti-lek-reeks v0.108.0–v0.109.0 + de mens-gecureerde feed-opschoning van 2026-07-11
(7 presence-pagina's verborgen). Zie `context/status.md` "Open taken".

---

## 1. Aanleiding & kern-inzicht

De discovery/footprint-engine zoekt het lid online op en crystalliseert vondsten. Elke vondst krijgt een
`type ∈ {project, media, blog, talk, social, other}`. De crystallize-routing:

| type | wordt | 
|------|-------|
| `project` | `Offering` (eigen werk) |
| `blog` | nieuws-`Post` (rol `geschreven`) |
| `talk` / `media` | nieuws-`Post` (rol `vermeld`) |
| `social` / `other` | nieuws-`Post` (rol `gedeeld`) |

**Het probleem**: de taxonomie mengt twee assen door elkaar:
1. **Wát** het is (project / artikel / talk / social-profiel / bio-pagina).
2. Of het de **eigen aanwezigheid** van het lid is (identiteit) óf **content óver** het lid (dekking).

Daardoor belanden **presence-pagina's** — de eigen identiteits-/profielpagina's van het lid — in de
nieuwsfeed. Concreet in productie (2026-07-11): `nl.linkedin.com/in/frankoonk`, `instagram.com/frankoonk/`,
`eve.law/arbiters/wouter-dammers/` (arbiter-bio), `legaldutch.nl/advocaat/wouter-dammers/` (advocaat-bio),
`heliview.nl/…/speaker/wouter-dammers/` (spreker-bio), `cheeseinabox.nl/author/herriaan/` (auteurspagina),
`cheeseinabox.nl/` (eigen bedrijfssite). Dat is **geen nieuws** — het is de online-aanwezigheid van het lid.

**Waarom er geen automatische post-hoc regel is**: een `Post` bewaart het footprint-`type` NIET (alleen de
afgeleide `role`), en de lek-items zijn zelfs `role=gedeeld`. URL-vorm helpt niet: `eve.law/arbiters/x`
(presence) en `oost.nl/nieuws/x` (nieuws) zijn niet te scheiden. Een URL-heuristiek vangt hooguit
LinkedIn/Instagram. Het enige betrouwbare moment om te onderscheiden is **bij de ingestie**, waar de
classifier (Opus + web_search) de pagina echt bekijkt. Daar hoort de fix.

---

## 2. Doel

1. **Presence-pagina's komen niet meer in de nieuwsfeed** — niet bij auto-crystallisatie, niet bij de
   1-klik-bevestiging.
2. **Echte dekking blijft nieuws**: artikelen, podcasts, interviews, keynotes ÓVER het lid (Omroep
   Veldhoven, BNR Cryptocast, Frankwatching, oost.nl) blijven gewoon nieuws.
3. **Eigen werk blijft project**: `project` → `Offering` ongewijzigd.
4. **Lage op-last**: geen terugkerende handmatige curatie meer; de poort zit in de classifier.

---

## 3. Aanpak — een presence-categorie bij de bron

### 3.1 Taxonomie
Voeg één type toe: **`presence`** = "de eigen aanwezigheids-/identiteitspagina van het lid": social-profielen
(LinkedIn/Instagram/X/YouTube-kanaal/TikTok/Threads), directory-/bio-listings (advocaat/arbiter/spreker/
auteur-pagina's) en de eigen landings-/bedrijfssite (géén specifiek artikel).

`VALID_TYPES` → `{project, presence, media, blog, talk, social, other}` (of: `social` vervangen door
`presence` — zie §6.1). `RECORD_TOOL.input_schema` enum + `SYSTEM_PROMPT` bijwerken met een scherpe,
voorbeeld-gedreven definitie + het onderscheid presence (identiteit) ⇄ media/talk/blog (dekking/content).

### 3.2 Classifier-prompt (de kern van de fix)
`SYSTEM_PROMPT` krijgt een expliciete beslisregel:
> Is dit de **eigen profiel-/bio-/aanwezigheidspagina** van de persoon (social-profiel, directory-listing,
> eigen landings-/bedrijfssite zonder specifiek artikel)? → `presence`.
> Is dit een **specifiek stuk content ÓVER of DÓÓR** de persoon (artikel, podcast, interview, keynote,
> nieuwsbericht)? → `media`/`talk`/`blog`.
> Bouwt/maakt de persoon dit als **product**? → `project`.

Met 2–3 concrete voorbeelden (LinkedIn-profiel → presence; "X geïnterviewd in podcast Y" → media;
"eigen SaaS-tool" → project).

### 3.3 Crystallize-routing — wat wordt een presence-vondst?
Twee opties; **aanbeveling = A (droppen/weren)** als eerste stap, B als optionele verrijking.

**A. Weren (aanbevolen, laagste op-last)**: `presence` crystalliseert **niet** naar nieuws. In de
discovery-resultaten tonen we presence-vondsten in een aparte, informatieve groep ("Je online aanwezigheid
— staat al op je radar") **zonder** crystallize-knop, of we laten ze weg. Auto-crystallisatie slaat
`presence` over. Geen nieuwe entiteit, geen feed-vervuiling.

**B. Herclassificeren naar het profiel (optioneel, fase 2)**: `presence` → `ProfileLink` met een nieuwe
`ProfileLinkKind.social`, getoond als compacte **"Vind me online"-strip** op het profiel (openbaar profiel
toont 'm; besloten profiel niet aan bezoekers — volgt de bestaande poort). Vereist: `undo_crystallize`
kind `"link"`, `_crystallized.html`/`_undone.html` een `link`-tak, en de profiel-strip-UI. Meer werk, maar
geeft het lid waarde i.p.v. de vondst weg te gooien.

> Aanbeveling: **A nu** (lost het lek + de op-last op), **B als aparte vervolg-PRD** wanneer er vraag is
> naar een socials-strip. Reden: A raakt alleen de classifier + één routing-tak (klein, laag risico); B
> voegt UI + datamodel toe zonder dat de behoefte bewezen is.

### 3.4 Bestaande items (migratie)
Historische nieuws-`Post`s zijn niet betrouwbaar terug te classificeren (geen bewaarde `type`, `role=gedeeld`).
Daarom **geen automatische migratie**: de 7 reeds mens-verborgen presence-items blijven `hidden=true`
(reversibel). Optioneel eenmalig: een admin-lijst van bestaande `source_kind=member`-nieuwsitems met een
"is dit presence?"-toggle — maar dat is curatie, geen code-poort (buiten scope; §7).

---

## 4. Afdwingen / raakvlakken (één bron)

- **Classifier** (`footprint_service`): `SYSTEM_PROMPT` + `RECORD_TOOL`-enum + `VALID_TYPES`.
- **Crystallize** (`footprint_service.crystallize`): `presence`-tak (weren of ProfileLink). Idempotentie
  op URL blijft.
- **Auto-crystallisatie** (`discovery.py` chokepoint + de SSE-`load`-kaart): `presence` triggert geen
  auto-nieuws. De "hoge confidence → auto"-poort geldt alleen voor `project`/dekking.
- **Discovery-resultaatweergave** (`discovery/_result.html` + kaarten): presence-vondsten apart of weg.
- **Geen** wijziging aan `post_service.list_news` nodig (de v0.109.0-auteurspoort blijft); presence komt
  simpelweg niet meer als nieuws binnen.

---

## 5. Testplan

- **Classifier-eenheid** (mock record_findings): een LinkedIn-/bio-URL → `type=presence`; een
  podcast-/artikel-URL → `media`/`blog`; een eigen tool → `project`. (Prompt-gedrag borgen we met een
  vaste mock-respons; de echte LLM-call niet in de suite.)
- **Crystallize**: `ftype=presence` → géén nieuws-`Post` (optie A) resp. een `ProfileLink` (optie B);
  `ftype=media` → wél nieuws; `project` → `Offering` (ongewijzigd). Idempotent op URL.
- **Auto-pad**: een `presence`-kandidaat met hoge confidence crystalliseert niet naar nieuws.
- **Regressie**: bestaande discovery/crystallize/undo-tests groen; de v0.108–0.109 anti-lek-tests groen.

## 6. Edge cases

1. **Eigen site die óók artikelen host** (`cheeseinabox.nl/` vs `…/blog/x`): de landings-/over-pagina =
   `presence`; een specifiek artikel = `blog`/`media`. Classifier beslist per URL.
2. **Bio-pagina die een talk aankondigt** (spreker-listing): `presence` (het is een directory-listing);
   de talk zelf kan los een agenda-event zijn — niet hier forceren.
3. **Eigen product-site** (`businesschoice.nl`): als het een build/product van het lid is → `project`
   (`Offering`), niet `presence`. Als het een mention/artikel is → nieuws.
4. **False positive** (echt artikel als `presence` bestempeld → ten onrechte geweerd): mitigatie = de
   bestaande mens-in-de-lus (lage confidence → bevestigrij; het lid ziet de vondst en kan 'm alsnog
   koppelen). Presence is bewust conservatief gedefinieerd (identiteitspagina, geen losse content).
5. **`social` vs `presence`**: `social` wordt overbodig (een social-profiel ís presence). §6.1: `social`
   uit de enum halen en naar `presence` mappen, of behouden en beide off-feed routeren.
6. **AVG/besloten**: presence van een besloten lid dat tóch als nieuws bestond → al afgevangen door de
   v0.109.0-auteurspoort; deze PRD voorkomt dat het überhaupt nieuws wordt.

### 6.1 Open beslissing
- **`social` behouden of vervangen door `presence`?** Aanbeveling: **vervangen** (social-profiel = presence;
  minder enum-ruis). Legacy `social`-strings vallen via de `not in VALID_TYPES → "other"`-poort netjes terug.

## 7. Niet nu (expliciet)

- **Automatische her-classificatie van historische nieuws-Posts** — geen betrouwbaar signaal; blijft
  mens-curatie (de 7 zijn al verborgen).
- **De "Vind me online"-profiel-strip (optie B)** — aparte vervolg-PRD als er vraag naar is.
- **Een socials-CRUD in de profielbouwer** — buiten scope.

## 8. Succescriteria

- Een discovery-run over een lid met LinkedIn/Instagram/bio-listings levert **nul** nieuwe nieuws-items uit
  presence-pagina's (auto én bevestigd); dekking (artikelen/podcasts) landt wél als nieuws.
- De nieuwsfeed blijft schoon zonder handmatige `hidden`-curatie na een nieuwe run. Browser-geverifieerd
  (bezoeker + lid) + test-gedekt (classifier-mock + crystallize-routing).
- Geen regressie op eigen-werk (`project` → `Offering`) of op de v0.108–0.109 anti-lek-poort.
