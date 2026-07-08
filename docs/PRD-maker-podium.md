# PRD — Maker-podium & scene-gids

**Status**: DRAFT — wacht op goedkeuring
**Datum**: 2026-07-08
**Relatie**: `PRD-hero-video.md` (cover-video v0.100.x), `PRD-hero-studio.md`, `PRD-open-showcase.md`
(werk-item-model + gelaagde zichtbaarheid §3.3), `docs/STYLEGUIDE.md` (kosmische diepte, één look),
`PRD-concierge-intelligentie.md` (nudges).

---

## 1. Aanleiding & kern-inzicht

Analyse van de veelgedeelde tutorial "award-winning websites met Claude Code + Sonnet 5"
(Viktor Oddy, juli 2026) leert dat de "geanimeerde 3D-websites" die nu viraal gaan **geen echte 3D**
zijn — geen Three.js, geen WebGL. De look ontstaat uit drie bouwstenen:

1. **AI-gegenereerde video-assets**: een referentiebeeld wordt gepersonaliseerd met een image-model
   ("vervang de konijn door de kat, houd de achtergrond"), daarna met motion-transfer
   (referentievideo + nieuw beeld → bv. Seedance 2.0) omgezet in een korte clip van 4–10 s, 1080p.
2. **Scroll-scrubbing**: `video.currentTime` wordt per animation-frame aan de scrollpositie
   gekoppeld — de video speelt niet, hij wordt *gescrubd*; terugscrollen keert de beweging om.
3. **Grote typografie + scroll-onthulling** eroverheen.

Precies deze pipeline is voor onze doelgroep — mensen die met AI bouwen — zelf uitvoerbaar.
Het portfolio van een lid hoort aan te sluiten bij wat de maker maakt: een videomaker verdient een
levende scene, een schrijver een rustig beeld. Vandaag is elke profielcover functioneel gelijk
(beeld → video click-to-play → nevel).

## 2. Doel

1. **Elk lid kan zijn profiel een eigen, levende scene geven** die bij zijn werk past — binnen de
   kosmische identiteit (geen tweede look).
2. **Het platform leert leden hóé** (prompts + tools + stappen): de scene-gids is zelf een bewijs
   van de missie — een community die met AI bouwt, laat zien hoe je met AI bouwt.
3. **Lage op-last**: hergebruik van de bestaande hero-video-upload en reveal-motor; geen nieuwe
   infrastructuur, geen JS-buildpipeline, geen AI-kosten voor anonieme bezoekers.

## 3. Ervaring (drie fasen)

### 3.1 Fase 1 — Scene-gids "Maak je eigen scene"

Een gids-pagina in de kosmische stijl (heldere, directe taal) die de pipeline stap voor stap
uitlegt, met **kopieerbare prompt-kaarten** (klik = prompt op klembord):

1. **Kies een referentie** — een motion-design of beeld dat qua sfeer past (eigen werk, Pinterest,
   promptbibliotheken zoals motionsites.ai).
2. **Personaliseer het beeld** — twee beelden naar een image-model; promptpatroon:
   *"Vervang [onderwerp] in het eerste beeld door [het tweede]. Houd achtergrond en stijl."*
3. **Beeld → video (motion-transfer)** — referentievideo + je beeld naar een video-model
   (bv. Seedance 2.0 via Higgsfield); promptpatroon: *"Animeer het beeld zoals de bijgevoegde
   video; de beweging moet gelijk zijn."* Kies de duur van de referentie (4–10 s), 1080p volstaat
   voor web.
   Technisch advies in de gids: exporteer met veel keyframes (bv. `ffmpeg -g 12`) zodat
   scroll-scrubben soepel blijft.
4. **Zet hem op je profiel** — upload als hero-video via de bestaande studio-flow (64 MB-cap).
5. **Kies je cover-stand** — stilstaand beeld, afspeelbare film, of scroll-scene (fase 2).

Tool-namen worden neutraal genoemd (Higgsfield, Seedance, ChatGPT-beelden, …) met de kanttekening
dat elk vergelijkbaar model werkt; geen sponsoring, geen affiliatie.

**Vindbaarheid**: de concierge biedt de gids proactief aan via een nieuw nudge-kind
(`scene_guide`) aan leden die wél werk-items maar nog een statische cover hebben; daarnaast een
link vanuit de hero-studio ("Wil je een levende scene? Volg de gids").

### 3.2 Fase 2 — Het podium: scroll-scene op de cover

Per profiel een **cover-stand** (`cover_mode`):

| Stand | Gedrag |
|---|---|
| `beeld` (default) | Huidig gedrag: cover-beeld of nevel. |
| `film` | Huidig gedrag v0.100.4: poster + click-to-play met geluid. |
| `scene` (nieuw) | Video is gedempt en speelt **niet**; hij scrubt met de scrollpositie over de eerste viewport-hoogtes. Terugscrollen keert de beweging om. Geen audio, geen knoppen. |

De platform-chrome (nav, secties, typografie, kleuren) blijft overal kosmisch en identiek — de
expressie zit in de scene zélf, niet in vrije styling. Dit is het "maker-podium": een begrensde
zone waar het werk van de maker het beeld bepaalt.

### 3.3 Fase 3 — Eigen code/3D via sandboxed embeds

Voor makers die écht interactief werk tonen (creative coding, 3D-scenes, prototypes): de
embed-allowlist wordt uitgebreid met creatieve providers (CodePen, Spline, Sketchfab; definitieve
lijst bij implementatie). Rendering altijd:

- **click-to-activate** (poster/preview eerst; geen third-party requests vóór de klik — AVG),
- iframe met `sandbox="allow-scripts"` **zonder** `allow-same-origin`,
- alleen op de werk-item-detailpagina en als kaart-preview, niet als cover.

## 4. Techniek (AUGMENT, geen herbouw)

### 4.1 Model
- `Profile.cover_mode` — enum (`beeld` | `film` | `scene`), default `beeld`; Alembic-migratie.
  Hergebruikt `Profile.cover_video_url` (v0.100.0: upload onder `UPLOAD_DIR`, Range-streaming,
  64 MB-cap, MP4-magic-byte-validatie). Géén nieuw opslagpad.
- Fase 3: uitbreiding `embed_service._PROVIDERS` (app/services/embed_service.py); geen nieuw
  `OfferingKind` — het blijft een embed op een bestaand werk-item.

### 4.2 Scroll-scrub (uitbreiding `profiles/_cover_media.html` + reveal-director)
- Activatie via de bestaande IntersectionObserver-laag (`ai/_cosmic_canvas.html`); tot de cover
  in beeld is: alleen poster, `preload="none"` → bij in-view `preload="metadata"`.
- rAF-loop met lerp: `video.currentTime = doelprogressie × duration` (zelfde smoothing-idee als
  de tutorial: kleine lerp-factor, `!video.seeking`-guard tegen stapelende seeks).
- Scrub-bereik gekoppeld aan de scrollafstand over de cover-sectie (100 vh), niet aan de hele
  pagina — korte profielen houden zo een volledig bereik.
- **Uitschakelaars**: `prefers-reduced-motion: reduce` → statisch poster-beeld (bestaande
  motion-dovers gelden); `Save-Data: on` → poster + fallback naar `film`-gedrag; metadata-fout of
  niet-scrubbare stream → poster (precedentie video → beeld → nevel blijft intact).
- Geen nieuwe dependencies, geen buildstap: inline JS naast de bestaande cover-JS.

### 4.3 Scene-gids
- Statische route + Jinja-template (bv. `/gids/scene`), alleen-leden zichtbaar is niet nodig —
  de gids is publiek en statisch (nul AI-kosten; harde constraint "anon nooit betaalde AI" blijft
  onaangeraakt).
- Prompt-kaarten als herbruikbare partial met kopieerknop (navigator.clipboard + nette fallback).
- Nudge: nieuw kind `scene_guide` in `app/services/nudge_service.py` (selectievoorwaarde:
  ≥1 werk-item ∧ `cover_mode=beeld` ∧ geen video), kaart via het bestaande `_nudge.html`-patroon
  (`data-concierge-go` → gids-URL), dismiss-persistentie zoals bestaande nudges.

### 4.4 Zichtbaarheid & veiligheid
- Het podium volgt de bestaande profiel-zichtbaarheid (`visibility_service.can_view`); geen
  aparte laag nu. Per-sectie-zichtbaarheid blijft de latere route uit `PRD-open-showcase.md §3.3`.
- Cover-video blijft eigen upload (geen hotlink-video: scrubben vereist Range-requests en
  voorspelbare beschikbaarheid; externe hosts breken dat). Werk-item-media blijft hotlink/oEmbed
  zoals vandaag (`safe_url`-filter, provider-allowlist).

## 5. Edge cases

| # | Geval | Gedrag |
|---|---|---|
| 1 | `prefers-reduced-motion: reduce` | Geen scrub; statisch poster-beeld; bestaande reveal-dovers gelden. |
| 2 | `Save-Data: on` of metadata laadt niet | Poster + `film`-fallback (click-to-play); nooit stille witte vlek. |
| 3 | mp4 met weinig keyframes | Scrub oogt schokkerig; gids-advies (`-g 12`), geen server-block (niet betrouwbaar detecteerbaar). |
| 4 | `cover_mode=scene` maar geen video (verwijderd) | Terugval naar `beeld`; studio zet de stand zichtbaar terug. |
| 5 | iOS Safari | Scrub vereist `muted playsinline` + geladen metadata; bij seek-fouten → `film`-fallback. |
| 6 | Zeer lange video als scene | Scrub-bereik blijft de cover-scroll; gids adviseert 4–10 s. Bestaande 64 MB-cap begrenst. |
| 7 | Embed-provider buiten allowlist (fase 3) | Vriendelijke weigering met verwijzing naar ondersteunde providers. |
| 8 | Third-party embeds & AVG (fase 3) | Click-to-activate: geen derde-partij-request vóór expliciete klik. |
| 9 | Anonieme bezoeker op gids of profiel | Nul AI-kosten (alles statisch/server-rendered); noindex-regels ongewijzigd. |
| 10 | Lid zonder werk-items opent de gids | Gids werkt gewoon; de nudge verschijnt alleen bij leden met werk-items (relevantie). |

## 6. Acceptatie- en succescriteria

1. Een lid maakt met de gids in ≤ 15 minuten een eigen scene en zet die live, zonder hulp.
2. De profielpagina laadt **geen video-bytes vóór in-view** (parity met v0.100.4); Lighthouse-
   performance van `/leden/{slug}` verslechtert niet.
3. Alle beweging dooft onder `prefers-reduced-motion`; scrub degradeert overal naar poster/film.
4. Tests in dezelfde sessie als de implementatie: unit (cover_mode-precedentie + terugval,
   nudge-selectie `scene_guide`), render (scrub-attributen aanwezig bij `scene`, gids-pagina
   rendert, kopieer-kaarten aanwezig), fase 3: allowlist-uitbreiding + sandbox-attributen.
5. Browser-check op mobiel én desktop vóór "af" (werkstijl-afspraak).

## 7. Fasering

- **Fase 1** — scene-gids + concierge-nudge + link vanuit hero-studio. Geen migratie.
- **Fase 2** — `cover_mode` + scroll-scrub + studio-keuze (drie standen). Migratie + JS.
- **Fase 3** — creatieve embed-providers, sandboxed + click-to-activate.

Elke fase is zelfstandig shipbaar; fase 1 levert al waarde zonder één regel model-wijziging.

## 8. Niet in scope (nu)

- **Vrije styling per profiel** (fonts, kleuren, layouts) — botst met "introduceer geen tweede
  look"; expressie loopt via de scene, niet via thema's.
- **Three.js/WebGL of een JS-buildpipeline** — de tutorial bewijst dat het effect zonder kan;
  een buildpipeline verhoogt de op-last blijvend.
- **Zelf hosten van leden-video's buiten de bestaande upload** (geen transcoding-pipeline,
  geen CDN-beheer).
- **Publieke promptmarkt** (motionsites-kloon) — de gids cureert een handvol patronen; een markt
  is een ander product.
- **Per-sectie zichtbaarheid** — blijft bij `PRD-open-showcase.md §3.3`.
