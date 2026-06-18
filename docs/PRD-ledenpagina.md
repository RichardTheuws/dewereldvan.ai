# PRD — Publieke ledenpagina, detailpagina's & profielverrijking

**Versie**: 0.1.0 · **Datum**: 2026-06-18 · **Status**: 🟡 APPROVAL PENDING
**Leidend**: `docs/STYLEGUIDE.md` + Ervaringsmandaat in `CLAUDE.md`. Alles "bizar gaaf", kosmisch.

## 1. Doel
De publieke buitenkant van dewereldvan.ai: een automatisch, verbluffend overzicht van de leden
en hun werk, met rijke detailpagina's per persoon én per project — gebouwd voor **linkwaarde/SEO**.
Plus twee profielverrijkingen die elk profiel persoonlijker en sterker maken.

## 2. Profielverrijking
### 2a. Profielfoto-upload (altijd beschikbaar, magisch)
- Elk lid kan **altijd** een eigen profielfoto uploaden (los van de AI-flow).
- **Magische UX**: drag-and-drop op een kosmisch veld, de foto "materialiseert" in een sterren-ring,
  ronde crop met live preview, zachte gloed. Geen kale `<input type=file>`.
- Opslag: M4-volume (`data/uploads/`, gitignored), geserveerd door de app; client-side resize +
  servervalidatie (type/grootte). Later evt. object-storage als volume krap wordt.
- Valt terug op de AI-cover/initialen als er (nog) geen foto is.

### 2b. Prominentie-keuze (persoon ↔ projecten)
- Bij het aanmaken vraagt de flow: *"Wil je dat we vooral jóú in de spotlight zetten
  (trainer, spreker, beleidsmaker) of vooral je projecten (bouwer, SaaS)?"*
- Slaat `profile.emphasis` op (`person` | `projects` | `balanced`), bewerkbaar.
- **Stuurt de layout-prominentie** op zowel het profiel als de ledenpagina-kaart:
  `person` → foto/headline/bio groot, projecten secundair; `projects` → projectkaarten met beeld
  groot, persoon compact; `balanced` → gelijk.

## 3. Publieke ledenpagina (`/leden`)
- Een levende **constellatie van leden** (kosmisch): elk lid een ster/kaart; hover onthult
  headline + kernbeeld; klik → detailpagina. Filter/zoek op tag, "wat ik maak", "waar ik zoek".
- **Automatisch**: vult zichzelf met alle **publieke** profielen (besloten profielen niet getoond).
- Respecteert `emphasis` in de kaartweergave. Lege/laad-staten ook in volle kosmische glorie.

## 4. Detailpagina's
- **Persoon** — `/leden/{slug}` (bestaat; verrijken tot de kosmische identiteit): cover/foto-hero,
  headline, bio, rollen/affiliaties, projecten-met-beeld, "waar ik zoek", tags.
- **Project** — nieuw `/projecten/{slug}` (of `/leden/{slug}/p/{project-slug}`): eigen rijke pagina
  per project (naam, omschrijving, beeld, link naar de echte site, de maker). Publiek + indexeerbaar.

## 5. Linkwaarde / SEO (expliciet doel)
- **Schone, stabiele slugs** (persoon + project), canonical URLs, geen wegwerp-querystrings.
- **OG/Twitter-tags** + **JSON-LD** structured data: `Person` voor leden, `CreativeWork`/
  `SoftwareApplication` voor projecten.
- **`sitemap.xml`** (alle publieke personen + projecten) + `robots.txt`.
- Alleen **publieke** content indexeerbaar; besloten = `noindex` + login-gated (bestaand patroon).
- Snelle, server-rendered pagina's (al de stack) → goede Core Web Vitals.

## 6. Datamodel (additief, Alembic)
- `profile`: + `emphasis` (enum person|projects|balanced, default balanced), + `photo_url`.
- `offering` ("project"): + `slug` (uniek, stabiel) voor de projectdetailpagina.
- (foto los opgeslagen op volume; alleen de URL/pad in de DB.)

## 7. Beslissingen (veto welkom)
- Foto-opslag op M4-volume (lage op-last) i.p.v. externe bucket; later herzien bij groei.
- Ledenpagina + projectpagina's **publiek** (showcase + linkwaarde); besloten profielen blijven verborgen.
- Emphasis default `balanced` als het lid niets kiest.

## 8. Edge cases & safeguards
- Upload: alleen afbeeldingstypes, maxgrootte, server-side hervalidatie, EXIF strippen (privacy).
- AVG: foto verwijderbaar; publiek tonen = bestaande consent-poort hergebruiken.
- Slug-botsing → suffix; slugs stabiel houden (linkwaarde) ook na rename (redirect oud→nieuw).
- Geschorste/besloten leden nooit publiek (bestaande `can_view`-poort doortrekken naar projecten).

## 9. Fasering
- **L1**: profielfoto-upload (magisch) + `emphasis`-vraag/-opslag + layout-prominentie.
- **L2**: publieke ledenpagina `/leden` (kosmische constellatie + filters).
- **L3**: projectdetailpagina's `/projecten/{slug}` + verrijkte persoonspagina.
- **L4**: SEO-laag (sitemap, JSON-LD, OG, canonical, robots).

## 10. Succescriterium
Een buitenstaander landt op `dewereldvan.ai/leden`, is verbluft, klikt door naar een persoon of
project, en elke pagina is rijk, snel en deelbaar — en bouwt linkwaarde op voor de community.
