# Project Status

**Laatste update**: 2026-06-19

## Huidige Focus
**Agent-Shell Fase 1 gebouwd (v0.15.0)** — voor ingelogde, goedgekeurde leden is de site nu een
levende agent-canvas (geen menu/links; interfaces materialiseren in-stroom via de surface-tool over een
vaste registry). Anoniem/publiek houdt de crawlbare pagina's. Gebouwd via understand→design→red-team
workflow (6 blockers gesloten), 430 tests groen, gecommit+gepusht op `main`. Nog **niet** gedeployed
naar de M4-preview (handmatige stap — wacht op go).

Volgende kandidaten: **Fase 2** (schrijf-surfaces: draft-tools "tonen + 1-klik bevestigen") of
deploy v0.15.0 naar de preview om de canvas live te beoordelen.

## Open Taken
- [ ] Email Sending-scope op het CF-token rond + verzenddomein onboarden (SPF/DKIM)
- [ ] CloudflareEmailSender-adapter toevoegen achter de bestaande EmailSender-interface
- [ ] Fase 0+1-app deployen op M4 → tunnel-ingress overzetten van teaser naar volledige app
- [ ] Wachtlijst-adressen (teaser SQLite) migreren naar de `member`-tabel
- [ ] CF API-token roteren / minimaal e-mail-only runtime-token maken

## Blokkades
- Geen harde blokkades. E-mail kan via console-outbox in dev terwijl CF-scope wordt afgerond.

## Recent Voltooid
- [x] Project geïnitialiseerd, git op `main`, scaffolding + plan (v0.1.0)
- [x] Fase 0+1 gebouwd via multi-agent workflow: fundering + profielen-MVP, CSRF, tests groen (v0.4.0)
- [x] Teaser live op https://dewereldvan.ai — M4 + eigen Cloudflare Tunnel `dewereldvan-teaser`,
      DNS (apex + www) via CF API, wachtlijst → SQLite (v0.5.0)
- [x] Beslissing e-mail: Cloudflare Email Service (Workers Paid actief) — zie decisions.md
