# PRD — Discovery-verdieping (gerichte media-pass)

**Status**: in aanbouw · **Versie doc**: 1.0.0 · **Datum**: 2026-06-20
**Aanleiding**: Richard (2026-06-20) na een perfecte brede ontdekking (12 projecten):
"doe ook een search op **media-items** (nieuwsberichten waarin ik genoemd word) voor
meer context — bied het aan als verdiepingsopdracht ('kom je weleens in het nieuws?
dan kan ik media over je zoeken'), evt. later ook events."

## Inzicht
De brede ontdekking vindt vooral **eigen werk** (projecten/sites). Media *over* een
persoon (interviews, artikelen, persvermeldingen) is een andere zoekintent en komt er
in de brede pass vaak bekaaid vanaf. Een **gerichte tweede pass** met een media-focus
haalt die context op — en is een natuurlijk, aanbiedend agent-moment ("zal ik dieper
graven?") i.p.v. alles in één keer.

## Ontwerp (hergebruikt de footprint-engine + achtergrond-job)
- **Focus-parameter op de engine**: `footprint_service.discover(..., focus="broad"|"media")`.
  `media` voegt aan de zoek-opdracht toe: zoek SPECIFIEK media WAARIN deze persoon
  genoemd/geïnterviewd wordt (nieuws, interview, podcast, panel/keynote, persvermelding) —
  NIET de eigen projecten; classificeer als `media`/`talk`; bevestig met de ankers.
- **Append-model** (geen nieuw run-schema): de media-pass draait als dezelfde
  achtergrond-job en **voegt** nieuwe findings toe aan de bestaande `DiscoveryRun`
  (`append=True`), **gededupeerd op URL** (projecten blijven, media erbij). De
  bestaande live-tail / terugkeer-view / chip werken ongewijzigd; `seen_at` reset zodat
  het klaar-seintje opnieuw afgaat.
- **Het aanbod (opt-in, agent stelt voor)**: na de brede ontdekking verschijnt een kaart
  op het resultaat én bij `done`: *"Kom je weleens in het nieuws of media? Dan zoek ik
  ook naar interviews, artikelen en vermeldingen óver jou."* → [Ja, zoek media] /
  [nee, hoeft niet]. "Ja" start de media-pass (append) → live-tail → bevestigen zoals 1b.
- **Crystalliseren**: media → nieuws-`Post` met rol-badge (al ondersteund door 1b). Geen
  nieuwe schrijf-paden nodig.

## Niet-doelen (v1)
- **Events** als aparte focus (`focus="events"` → agenda-`Post`) — fast-follow: de
  focus-parameter generaliseert, maar events crystalliseren naar de agenda en vragen een
  eigen aanbod-copy ("organiseer/spreek je op events?"). Eerst media.
- Geen aparte run per modus (append houdt het schema simpel; re-run dedupt).
- Geen oordeel "positief/negatief" over media (de copy blijft neutraal: "kom je in het
  nieuws", niet "ben je regelmatig positief in het nieuws").

## Eerlijke punten
- **Precisie**: media-disambiguatie is lastiger dan eigen-domein (naamgenoten in het
  nieuws). Zelfde poort als 1b: ankers + confidence + bevestigrij; auto-crystalliseren
  alleen ≥`HIGH_CONFIDENCE`.
- **Kosten/latency**: een tweede engine-pass. Daarom opt-in (alleen op "Ja"), append +
  dedup voorkomt dubbel werk.

## Succes / KILL
- **Succes**: een lid klikt "zoek media" en ziet gegronde vermeldingen óver zich
  verschijnen die de meeste leden bevestigen.
- **KILL** de media-pass als de precisie laag is (veel naamgenoot-ruis) → de focus blijft,
  maar zet 'm achter een strengere drempel of laat 'm vallen; de brede pass blijft intact.
