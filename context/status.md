# Project Status

**Laatste update**: 2026-06-17

## Huidige Focus
Teaser is **live op https://dewereldvan.ai** (community warm maken). Fase 0+1-code staat
gecommit (v0.4.0). Volgende: Fase 0+1 echt deployen op de M4 + Cloudflare-e-mail aansluiten.

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
