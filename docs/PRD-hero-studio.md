# PRD — Hero-studio (lid-controle over de cover, met verwondering)

**Status**: APPROVED + GEÏMPLEMENTEERD (v0.99.0, 2026-06-30)
**Auteur**: Claude + Richard
**Datum**: 2026-06-30
**Relatie**: vervangt de enkel-knop-cover uit [PRD-ai-profiel.md](PRD-ai-profiel.md) §F2/F3;
volgt [STYLEGUIDE.md](STYLEGUIDE.md) ("kosmische diepte").

---

## 1. Probleem

Het hero-beeld van een lid (`profile.cover_image_url`) ontstaat nu volledig
automatisch: de art-director-AI (`cover_art_service.build_prompt`) leidt één
visuele metafoor af uit het profiel, fal.ai (*flux/schnell*) rendert één beeld,
en de UI (`ai/_cover.html`) biedt **één hendel**: "Nieuwe cover" — een blinde
re-roll die het vorige beeld weggooit.

Het lid heeft dus **geen echte controle**: geen keuze uit varianten, geen sturing
op sfeer/kleur, geen intentie meegeven, geen favoriet vastzetten. Tegelijk mag de
oplossing géén rauw prompt-tekstveld worden — dat is "een formuliertje op een
pagina" en schendt het ervaringsmandaat.

## 2. Doel

Geef het lid **echte controle** over de hero, uitsluitend via gecureerde,
verrassende keuzes die binnen de kosmische stijl (`_COVER_STYLE`) blijven — zodat
identiteit en graceful-fail gegarandeerd blijven en de magie behouden blijft.

**Niet-doelen**: geen rauw prompt-veld; geen losstaande beeld-upload (de foto-
upload bestaat al als aparte laag); geen verandering aan de fallback-keten
foto → cover → initialen.

## 3. Ervaring (flow)

1. Na het opstellen van het profiel verschijnt — zoals nu — automatisch één cover.
2. Onder het beeld: **"Open de hero-studio"**. Daarin:
   - **Een constellatie van varianten.** Eén generatie levert 3–4 covers tegelijk
     (fal `num_images`). Ze verschijnen samen; het lid kiest er één.
   - **Sfeer-chips** (geen tekstveld), binnen het kosmische palet:
     - *Accent*: violet · cyaan · aurora · ember
     - *Energie*: serene ↔ elektrisch
     - *Motief-nadruk*: optionele klemtoon op een eigen tag/onderwerp
   - **Eén zachte intentie-regel** ("waar wil je dat dit beeld over gaat?") — gewone
     taal, max ~120 tekens, gaat als extra brief naar de art-director (géén rauwe
     prompt; wordt altijd in `_COVER_STYLE` ingebed).
   - **"Hou deze"** → zet de gekozen cover vast (`cover_locked`), zodat auto-regen
     (her-materialisatie/discovery) hem niet meer overschrijft.
3. Microcopy: simpel en direct (geen zweverige taal). De verwondering zit in het
   beeld en het samen verschijnen van varianten, niet in de woorden.

## 4. Techniek

- **Interface**: `ImageGenerator.generate()` uitbreiden naar N beelden.
  Voorkeur: `generate(prompt, *, count=1) -> list[GeneratedImage]` (of een nieuwe
  `generate_many`), zodat bestaande callers (`count=1`) ongewijzigd blijven.
  - `FalImageGenerator`: stuur `"num_images": count` mee; parse alle
    `result["images"][i]["url"]`. Bij minder beelden dan gevraagd: lever wat er is.
  - `NoopImageGenerator`: lever `count`× `GeneratedImage(url=None)`.
- **Prompt**: `cover_art_service.build_prompt(profile, *, steer=None)` —
  `steer` = (accent, energie, motief, intentie). De steer-termen worden
  deterministisch ná `_COVER_STYLE` en de metafoor toegevoegd, nooit ervóór, zodat
  de stijl-garantie (geen tekst/gezichten/logo's) leidend blijft.
- **State**: kandidaat-URL's zijn **transient** (niet in de DB) — alleen de
  gekozen/vastgezette cover landt in `profile.cover_image_url`. Kandidaten leven in
  de htmx-render of een korte server-side scratch; bij refresh weg = acceptabel.
- **Model**: nieuw `cover_locked: bool` op `Profile` (Alembic-migratie, default
  `false`). Auto-cover slaat over als `cover_locked` waar is.
- **Routes** (in `ai_profile.py`):
  - `POST /profiel/ai/cover` — genereert nu N varianten i.p.v. 1 (steer optioneel).
  - `POST /profiel/ai/cover/kies` — zet gekozen URL op het profiel.
  - `POST /profiel/ai/cover/lock` — toggelt `cover_locked`.
- **UI**: `ai/_cover.html` herwerkt tot studio-fragment (varianten-grid + chips +
  intentie-regel + kies/hou-knoppen), htmx-swaps op `#cover`.
- **Rate-limit**: hergebruik `rate_limit_ai_enrich_per_hour` (nu 10/u per lid).
  N varianten per klik telt als **één** generatie-event tegen die teller? → zie
  edge cases; voorstel: tel per klik, niet per beeld.

## 5. Edge cases

| # | Geval | Gedrag |
|---|-------|--------|
| 1 | fal levert 0 beelden / netwerkfout | Bestaande graceful-fail: lege variantenset + `cover_error`; vorige cover blijft staan (niet wissen). |
| 2 | fal levert minder dan gevraagd | Toon wat er is; geen fout. |
| 3 | `FAL_KEY` leeg / backend=noop | Studio toont géén variant-beelden, wel de chips uitgeschakeld + uitleg dat covers nu uit staan. Profiel werkt op initialen-fallback. |
| 4 | AI-enrich uit / lege brief | Geen art-director-call; deterministische `cover_prompt` + steer. Intentie-regel wordt dan genegeerd (geen Claude om te interpreteren) — meld dat subtiel. |
| 5 | Rate-limit bereikt | Knop disabled + heldere melding "je hebt het maximum bereikt, probeer later"; geen 500. |
| 6 | Lid heeft een geüploade foto | Foto wint in de weergave-keten; studio meldt "je geüploade foto staat nu vooraan — de hero is je achtergrond". Cover blijft instelbaar. |
| 7 | Intentie-regel met onzin/PII/scheldwoord | Gaat door art-director (die maakt er een abstracte metafoor van); `_COVER_STYLE` verbiedt tekst/gezichten/namen in beeld. Lengte gecapt. |
| 8 | `cover_locked` aan + nieuwe generatie | Auto-regen slaat over; een **expliciete** lid-generatie in de studio mag wél (lock beschermt tegen automatiek, niet tegen de maker zelf). Na kiezen blijft lock staan tot het lid hem opheft. |
| 9 | Dubbel-submit / race op kiezen | Idempotent: laatste keuze wint; geen unieke-constraint, dus geen race-500 (vgl. [idempotent-race learning]). |
| 10 | Heel veel tags / lange bio | Brief al gecapt in `cover_art_service._brief`; steer-motief kiest uit bestaande tags, geen vrije invoer. |

## 6. Acceptatiecriteria

- [ ] Eén klik in de studio toont 3–4 varianten naast elkaar (of een nette lege
      staat bij fail), zonder de bestaande cover te wissen.
- [ ] Sfeer-chips veranderen aantoonbaar de prompt, nooit het stijl-anker.
- [ ] Een gekozen variant landt in `cover_image_url`; "Hou deze" zet `cover_locked`.
- [ ] Vergrendelde cover overleeft her-materialisatie/discovery.
- [ ] Alle edge cases 1–10 hebben een test (pytest, SQLite in-memory).
- [ ] Geen regressie in de foto→cover→initialen-fallback.
- [ ] Visueel getest in een echte browser (mandaat: niet alleen render-strings).

## 7. Buiten scope (later)

Echte multi-image upload voor designers; cover-bibliotheek/historie; animatie/motion
op de hero. Bewust later — zie pivot-memory (galerij = hotlink, nul-opslag tot
designer-vraag).
