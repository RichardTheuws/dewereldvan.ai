# PRD — Sectie-niveau zichtbaarheid ("Openbaar, maar alleen wat ik kies")

**Status**: LIVE (v0.106.0, 2026-07-11)
**Datum**: 2026-07-11
**Relatie**: `app/services/visibility.py` (de zichtbaarheids-poort), `PRD-ledenpagina.md`,
`PRD-open-showcase.md` (§3.3 gelaagde zichtbaarheid = standing, NIET veld-privacy — dit is nieuw),
`app/templates/ai/_publish_panel.html` (de publiceer-UI), `docs/STYLEGUIDE.md`.

---

## 1. Aanleiding & kern-inzicht

Zichtbaarheid is nu **binair op profiel-niveau** (`Visibility` = `members` | `public`). "Alleen leden"
(default) dekt al de wens "helemaal niet in het publieke deel" — besloten, niet in de publieke gids,
`noindex`. Wat **ontbreekt** is de tussenweg: *publiek aanwezig zijn, maar alleen met specifieke info*.
Een lid kan nu niet zeggen "toon me publiek met naam + discipline, maar houd mijn bio, mijn vraag en
mijn contact besloten". Openbaar = het hele profiel openbaar, alles-of-niets.

**Kern-inzicht**: we hebben géén derde `Visibility`-waarde nodig. Houd de binaire poort
(members/public) en voeg één veld toe — `public_sections` — dat bij `public` bepaalt **welke blokken**
een niet-lid (bezoeker) ziet. Leden zien altijd alles (binnen de bestaande members-poort). Zo blijft
de bestaande poort intact en is "beperkt openbaar" gewoon "openbaar met een subset zichtbaar".

## 2. Doel

1. Een lid dat openbaar wil, kiest **per blok** wat een bezoeker ziet: bio, wat ik maak, wat ik zoek,
   waar ik voor opensta (beacons). Naam + foto + discipline zijn de **altijd-zichtbare basiskaart**
   (anders betekent "openbaar" niets).
2. **Nul regressie**: bestaande openbare profielen blijven volledig openbaar.
3. **Geen lek**: een besloten-gehouden blok mag ook niet via discovery-filters of meta-tags uitlekken.
4. Laag in op-last: ~4 schakelaars, geen per-item-explosie.

## 3. Ervaring (publiceer-dok, `_publish_panel.html`)

Bij "Openbaar" verschijnen schakelaars ("Toon publiek:"):

- **Naam + discipline + foto** — altijd aan (uitgegrijsd, de basiskaart).
- ☐ **Bio** ("over jou")
- ☐ **Wat ik maak** (offerings/projecten)
- ☐ **Wat ik zoek** (needs)
- ☐ **Waar ik voor opensta** (open_to-beacons)

Default bij eerste keer openbaar: **alles aan** (= huidige "volledig openbaar", geen verrassing).
Alles uit = een puur "visitekaartje" (naam + discipline + foto). Heldere, gewone microcopy
(Styleguide): *"Kies wat bezoekers zien. Leden in de community zien altijd je volledige profiel."*

Het **AVG-consent-vinkje spiegelt de keuze dynamisch**: het somt exact de aangevinkte blokken op
("…naam, discipline, foto, bio openbaar en vindbaar te maken"). Consent blijft verplicht voor openbaar.

## 4. Datamodel

- **`Profile.public_sections: list[str] | None`** (JSON, nullable). Bevat de slugs van de blokken die
  voor een **bezoeker** zichtbaar zijn wanneer `visibility=public`. Toegestane slugs:
  `bio`, `makes`, `needs`, `open_to`. De basiskaart (naam/foto/discipline/headline) staat er NIET in —
  die is altijd publiek bij `public`.
- **Semantiek**: `None` = **alle** blokken publiek (legacy + backwards-compatible; bestaande openbare
  profielen ongewijzigd). Een lijst = alleen die blokken publiek; de rest = alleen-leden.
- Migratie `00XX_profile_public_sections` (additief, nullable, geen backfill). Verdwijnt mee met het
  profiel (CASCADE op member) — AVG.
- Helper `visibility.public_section_visible(profile, section, viewer)` → `True` als de kijker lid is
  (ziet altijd alles), óf het profiel legacy-`None` is, óf de sectie in `public_sections` staat.

## 5. Afdwingen (de poort — kritisch, één bron)

Alle checks lopen via `visibility.py` (geen tweede implementatie):

1. **Profieldetail `/leden/{slug}`**: render per blok `public_section_visible(...)`. Lid-kijker → alles;
   bezoeker → alleen publieke blokken. De besloten blokken tonen niets (geen "verborgen"-placeholder
   die alsnog het bestaan verraadt bij gevoelige velden — gewoon weg).
2. **Ledengids-kaart `/leden`** (bezoeker): de kaart toont naam + discipline + foto (basis). Snippets
   uit bio/maak/zoek alleen als dat blok publiek is.
3. **Discovery-filters (anti-lek)**: `list_public_profiles(maakt=/zoekt=/tool=)` matcht voor een
   **bezoeker** alléén op blokken die dat profiel publiek heeft. Een lid dat "wat ik maak" besloten
   houdt, mag niet via een publieke `maakt=`-filter opduiken (de match zelf zou "deze maakt X" lekken).
   Voor een **lid-kijker** telt alles (leden zien alles). → de query wordt kijker-bewust.
4. **SEO/meta + sitemap**: de `og`/description gebruikt bio alleen als bio publiek is; anders een
   neutrale regel ("Maker op dewereldvan.ai"). `noindex` ongewijzigd (alleen `members` = noindex).
5. **"Dichtbij"/auto-selectie** (fase 2 Samenkomen): ongewijzigd — dat draait op leden-context en de
   publieke poort; besloten blokken spelen daar geen rol (leden zien elkaar volledig).

## 6. Edge cases

1. **Openbaar met nul optionele blokken** → alleen de basiskaart publiek. Geldig (het "visitekaartje").
2. **Legacy openbaar (`public_sections = None`)** → volledig publiek, exact als nu. Geen regressie.
3. **public → members** → `public_sections` wordt genegeerd (alles al besloten); we bewaren de waarde
   voor als het lid later opnieuw publiceert (geen her-instellen).
4. **Consent vs keuze**: consent-tekst en werkelijke publieke blokken moeten synchroon zijn; de route
   valideert dat consent hoort bij de aangevinkte set (spiegelt de bestaande `ConsentRequired`).
5. **Discipline vs "wat ik maak"**: discipline (grove categorie, afgeleid uit `Offering.kind`) hoort bij
   de basiskaart en blijft publiek, óók als de offering-details ("wat ik maak") besloten zijn — de
   categorie is een label, niet het werk zelf. Bewust; benoemd in de microcopy.
6. **AVG-wis** → `public_sections` verdwijnt met het profiel (CASCADE).
7. **Directe deep-link naar een besloten item** (bv. `/projecten/{slug}` van een besloten-gehouden
   offering) → moet dezelfde poort respecteren: bezoeker krijgt de members-gate, niet het item.

## 7. Niet nu (expliciet)

- **Per-item/per-veld slotjes** (elk project/need los) — afgewezen: UX-explosie + op-last, botst met
  het lage-op-last-mandaat. Sectie-niveau dekt de behoefte.
- **Een derde `Visibility`-enum-waarde** — onnodig: `public` + `public_sections` is eenvoudiger en
  raakt de bestaande poort niet.

## 8. Succescriteria

- Een lid kan openbaar gaan en met een paar schakelaars kiezen welke blokken een **bezoeker** ziet;
  leden zien altijd het volledige profiel.
- Een besloten-gehouden blok is nergens zichtbaar voor een bezoeker: niet op de detailpagina, niet in
  de gids-kaart, niet via een discovery-filter, niet in meta/sitemap. Browser-geverifieerd (ingelogd
  vs uitgelogd) + test-gedekt (poort + anti-lek-query).
- Bestaande openbare profielen blijven exact zoals ze waren (legacy `None` = volledig publiek).
