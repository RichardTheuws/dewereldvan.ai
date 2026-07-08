# Video-stijlgids — dewereldvan.ai

**Status**: v1.0 (2026-07-08)
**Relatie**: `docs/STYLEGUIDE.md` (kosmische diepte — de moederstijl), video-studio-skill
(`~/.claude/skills/video-studio/`, incl. `reference/commercial-craft.md` als kwaliteitslat).
**Doel**: elke video (feature-demo op de homepage, socials, uitleg) voelt als hetzelfde
universum als de site — zonder per video opnieuw stijlkeuzes te maken.

---

## 1. Merk-DNA (uit de site, verplicht)

| Element | Waarde | Gebruik in video |
|---|---|---|
| Achtergrond | `#04040e` (bijna-zwart indigo) | Basis voor alle kaarten/titels; nooit puur zwart naast site-beeld |
| Goud (accent) | `#f6cd86` | Spaarzaam: highlights, keyword-accent, glow — nooit vlakken |
| Indigo/blauw | `#3a6bff` / nevel `#6034a8` | Sfeer/glow, secundaire accenten |
| Tekst | `#f4f1ff` (primair), `#9097c4` (gedempt) | Titels resp. sub-labels |
| Titelfont | **Fraunces** 600–800 (serif) | Alle headlines; italic voor de "welkom"-toon |
| Labelfont | **JetBrains Mono**, uppercase, letter-spacing ~0.3em | Eyebrows, lower-thirds, feature-labels |
| Bodyfont | Spline Sans | Langere toelichting (spaarzaam in video) |
| Toon | Eenvoudig, direct, warm — **niet zweverig** | Microcopy-regels van de site gelden ook on-screen |

## 2. Vaste bumpers (in `assets/video/`)

Opgenomen van de echte site-intro (1920×1080, 30 fps, geen audio — zie §5):

| Asset | Duur | Inhoud | Gebruik |
|---|---|---|---|
| `intro-warp.mp4` | 10,2 s | 3D-wereld → uiteenvallen → wordmark → **warp-flits (eindigt op wit)** | Standaard opener: cut op de witte piek direct naar je eerste content-shot (dip-from-white) |
| — intro zonder warp | 9,45 s | zelfde, eindigt op wordmark-hold | geen apart bestand: trim `intro-warp.mp4` op `-to 9.45` |
| `intro-kort.mp4` | 3,3 s | particles → wordmark vormt | Socials/shorts of tweede video in een reeks |
| `outro.mp4` | 2,9 s | wordmark lost op in particles → fade-to-black | Vaste afsluiter van elke video |

**Herproductie** (bv. na een intro-redesign): Playwright headed, viewport 1920×1080,
`recordVideo`; ga naar `https://dewereldvan.ai/` (first-time-flow) of `/?intro=1`
(sinds v0.102.2 toont ook die de 3D-act), klik "Betreed de wereld", neem ±17 s op.
Knippunten in de opname zoeken via frame-strips (`ffmpeg -vf fps=6,tile=…`). De outro
is het morph-segment omgekeerd: `ffmpeg -ss <TRANS> -to <wordmark-hold> -vf "reverse,fade=out:…"`.

## 3. Titels & kaarten (commercial-craft, niet onderhandelbaar)

- Titels in **Fraunces 700+**, groot; altijd met backing (scrim of glas-plaat:
  `rgba(255,255,255,.04)` + 1px rand `rgba(255,255,255,.14)`, radius 16–999px zoals de site-pills).
- Eyebrow erboven in JetBrains Mono uppercase (`#9097c4`), exact zoals `dwv-intro__eyebrow`.
- Hold lang genoeg om 2× te lezen (≥ 2,5 s bij één regel).
- Tekst-PNG's genereren via ImageMagick met de echte fonts — geen ffmpeg-drawtext.
- Keyword-highlight in goud, maximaal één per kaart.

## 4. Beeld & montage

- **Overgangen**: cross-dissolve 0,4–0,6 s of dip-to-white via de warp-flits; harde cut
  alleen bewust op een beat. Nooit een hard-cut-ketting.
- **Screencaptures** van het product: Playwright `recordVideo` op 1920×1080 (geen
  macOS-schermopname-permissies nodig, geen menubalk/dock-ruis), langzaam en gelijkmatig
  scrollen (scroll-animaties zijn het product). Cursor alleen in beeld als hij iets doet.
- **Grade**: de site is al kosmisch — géén extra kleurgrade op UI-captures; alleen
  subtiele grain (4–6) op AI-gegenereerde tussenshots zodat alles één textuur deelt.
- **Hero ademt**: op stilstaande momenten lichte scale-drift (1,00→1,03) i.p.v. bevroren beeld.
- Master 16:9 1080p30; 9:16-derivaten via bewuste reframe (crop/pan), nooit uitrekken.

## 5. Audio

De captures zijn stil (de site-anthem is Web Audio en wordt niet mee-opgenomen). In post:
- Bed: etherisch warm pad (laag, -24 LUFS onder VO), pentatonische zachte chimes bij
  reveals — zelfde vocabulaire als de site-anthem (A-majeur-achtig, sine/soft).
- Warp-moment: rising sweep + shimmer; outro: lange zachte uitfade (geen abrupte stop).
- Loudness: totaal -16 LUFS (socials -14); duck het bed onder voice-over.

## 6. Recept feature-demo homepage (±30–45 s)

1. `intro-warp.mp4` (10,2 s) → cut op de witte piek naar het eerste product-shot.
2. 2–4 product-shots (Playwright-capture) met per shot één Fraunces-titelkaart
   (wat zie je + waarom fijn), cross-dissolves.
3. Afsluiten met CTA-kaart ("Bouw je profiel op dewereldvan.ai", goud accent) → `outro.mp4`.
4. QA vóór oplevering: frame-strip ≤ 0,7 s + cut-paren + leesbaarheid + de €600-test
   (video-studio-skill §5/§7).
