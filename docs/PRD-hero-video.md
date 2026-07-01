# PRD — Video in de hero

**Status**: APPROVED + GEÏMPLEMENTEERD (v0.100.0, 2026-07-01)
**Datum**: 2026-07-01
**Relatie**: bouwt voort op [PRD-hero-studio.md](PRD-hero-studio.md) (v0.99.x).

## Probleem / doel
De hero (cover) kan nu alleen een AI-gegenereerd beeld zijn. Een lid moet ook een
**video** als hero kunnen zetten — bewegend beeld is de sterkste eerste indruk.
Anders dan de beelden (hotlink fal, nul opslag) moet een video **gehost** worden.

## Ontwerp
- **Model**: `Profile.cover_video_url` (nullable). Hero-precedentie: **video → beeld → nevel**
  (de avatar-foto blijft los).
- **Opslag**: mp4 onder `UPLOAD_DIR` (named volume `outbox:/app/data`), geserveerd via de
  bestaande `/uploads`-StaticFiles-mount — Starlette's `FileResponse` ondersteunt Range,
  dus streaming/seek werkt. Cap `max_video_bytes` (64 MB), type-allowlist `video/mp4` +
  magic-byte-check (`ftyp`). Oude video wordt bij vervanging/verwijderen gewist (AVG).
- **Rendering**: gedeeld fragment `profiles/_cover_media.html` (video-of-beeld) in álle
  hero-plekken (`view.html`, `ai/_cover.html`, studio). `<video autoplay muted loop
  playsinline preload>` met het cover-beeld als `poster`. Muted-autoplay = browser-veilig;
  een subtiele **unmute-pill** maakt audio bereikbaar (de anthem heeft geluid).
- **Bediening** (hero-studio): "Video als hero" — mp4 uploaden; en "Videohero verwijderen"
  → terug naar het beeld. Zit in `_cover_studio.html` (dus op bouwen/edit/concierge).
- **Routes** (member-only): `POST /profiel/ai/cover/video`, `POST /profiel/ai/cover/video/verwijderen`.

## Edge cases
| # | Geval | Gedrag |
|---|-------|--------|
| 1 | Te grote/niet-mp4 upload | Vriendelijke 400, hero blijft ongewijzigd. |
| 2 | Video + geen beeld | Video-hero; nevel als poster-fallback. |
| 3 | Video verwijderd | Terug naar cover-beeld → nevel. |
| 4 | Reduced-motion | Geen autoplay-nadruk; poster/eerste frame blijft staan (browser-gedrag). |
| 5 | Autoplay geblokkeerd (mobiel/laag data) | Muted+playsinline maximaliseert autoplay; anders toont de poster. |
| 6 | Oud videobestand bij vervangen | Wordt gewist (geen wees-bestanden). |

## Buiten scope (later)
In-app transcode/compressie (nu: faststart-remux bij de operator-plaatsing), meerdere
video-formaten, per-video trimmen.
