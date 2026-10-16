# PRD — De voordeur: eerst helpen, dan pas werven

**Status**: GOEDGEKEURD — Richard 2026-10-16 ("ga door")
**Versie**: 0.1.0
**Datum**: 2026-10-16
**Raakt**: `app/main.py` (index), `app/templates/index.html`, nieuw `app/routers/zoek.py` +
`app/services/search_service.py`, `stats_service` (doorklik-tellers)
**Volgt uit**: `docs/PRD-hub.md` (hoofdmaatstaf = aanvragen van buiten).

## 1. Aanleiding
Verdict huidige voordeur: **FAIL**. Na de intro ("Betreed de wereld") landt een bezoeker op een pagina die
alleen tegen aankomende makers praat: kop "Geef een link. De agent bouwt je profiel.", een demo met een
fictief profiel, "Word lid", "Waarom je hier een profiel maakt". Wie een trainer, bureau, event of nieuws
zoekt vindt niets — terwijl er live **44 aankomende events, 134 nieuwsitems, 6 gidsen en 7 openbare makers**
staan. Het "Vraag de agent"-blok zegt tegen een bezoeker "Word lid om de hele graaf te doorzoeken".

## 2. Belofte
> Kom binnen met een vraag, ga weg met een antwoord: de juiste maker, het volgende event, het nieuws van
> deze week. Wie zelf met AI werkt, ziet meteen waarom hij hier wil staan.

## 3. Scope
### 3.1 Zoeken zonder AI — `/zoek?q=` (v0.117.0)
- Eén zoekveld over **makers** (via `directory_service.public_makers`: naam, kopregel, wat ik maak, tags,
  tools — alleen publieke blokken), **events** (aankomend of terugkerend: titel, locatie, beschrijving) en
  **nieuws** (titel, AI-duiding). Pure SQL/in-memory, **nul AI** (harde constraint anon).
- Resultaten in drie groepen met aantallen; per groep max 6 + "meer" (→ `/leden?maakt=`, `/agenda`, `/nieuws`).
- Snelkeuzes zonder typen: *Ik zoek een trainer* (→ `/gids/trainers`), *een bouwer of bureau*
  (→ `/gids/bouwers`), *events deze maand*, *nieuws van deze week*.
- Zonder `q`: de lege zoekpagina toont de snelkeuzes. Publiek; `noindex` op resultaatpagina's (eindeloze
  combinaties), de lege `/zoek` mag geïndexeerd.

### 3.2 Nieuwe voordeur (v0.118.0)
Volgorde: (1) kop als vraag ("Wie maakt wat met AI in Nederland en België?") + zoekveld + snelkeuzes;
(2) **Vind een maker**: de gidsen met aantallen + tot 4 makers met zichtbaar werk ("Stel een vraag");
(3) **Binnenkort**: eerstvolgende 4–6 events; (4) **Deze week in AI**: bovenste 4 nieuwsitems (deze week,
anders recentste); (5) **Werk je zelf met AI? Sta erin** — de bestaande demo + "Word lid", onderaan.
De intro blijft; daarna landt de bezoeker in deze content. Ingelogde leden: ongewijzigd (agent-canvas).

### 3.3 Meten
Doorklik vanaf de voordeur: links krijgen `?via=home`; de profielteller telt een `home`-bezoek apart
(`ProfileStatDay.kind = "via_home"`). Zoekopdrachten worden niet opgeslagen (geen zoekwoord-log).

## 4. Edge cases
| Situatie | Gedrag |
|---|---|
| Geen aankomende events | Sectie toont terugkerende meetups; zijn die er ook niet, dan valt de sectie weg |
| Geen nieuws deze week | Toon de 4 recentste items, kop wordt "Recent in AI" |
| Zoekopdracht zonder resultaat | Nette lege staat + snelkeuzes + "Stel je vraag in de gidsen" |
| Zoekterm leeg of 1 teken | Geen zoekactie, snelkeuzes tonen |
| Zoekterm > 100 tekens | Afkappen op 100 |
| Besloten profiel / besloten blok | Komt nooit in resultaten (directory_service-poort) |
| Nieuws van besloten lid | Valt weg voor bezoeker (bestaande `list_news(viewer=None)`-poort) |
| Verlopen event | Niet in zoekresultaten of "Binnenkort" |
| Minder dan 4 makers met werk | Toon wat er is; 0 → alleen de gidsen |
| Ingelogd lid op `/` | Ongewijzigd: agent-canvas. `/zoek` werkt voor iedereen |

## 5. Bewust niet
- AI-zoeken voor bezoekers (betaalde AI anon is uitgesloten; `/proef` blijft de enige gecapte uitzondering).
- Twee aparte voordeuren (keuzemenu bij binnenkomst, dubbel onderhoud).
- Eigen detailpagina's voor events/nieuws (nu linken ze naar de bron; later te overwegen voor SEO).

## 6. Succescriterium
Over 30 dagen: doorklikken vanaf de voordeur naar profiel/gids/event/nieuws zichtbaar in de tellers, en
de eerste aanvraag die via de voordeur binnenkomt.
