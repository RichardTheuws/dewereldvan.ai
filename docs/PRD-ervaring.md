# PRD — Onboarding-ervaring, slimme interface & centrale pagina's

**Versie**: 0.1.0 · **Datum**: 2026-06-18 · **Status**: 🟡 APPROVAL PENDING
**Leidend**: `docs/STYLEGUIDE.md` + het Ervaringsmandaat in `CLAUDE.md` (alles verbaast, altijd).

## 1. Doel
Maak van álle randen van het platform — de eerste aanraking, feedback geven, meedenken — een
bijzondere, kosmische ervaring, en geef de interface actieve intelligentie. Concreet drie sporen:
A) een verrassende **onboarding**, B) **feedback/suggesties overal**, C) **centrale pagina's**
(roadmap + ideeënbus). Geen kale formulieren; alles volgt de styleguide.

## 2. A — Onboarding-ervaring
- **Gestylede e-mails** (magic-link + goedkeuring) in de kosmische identiteit (HTML-mail), niet
  een platte tekstlink. Achter de bestaande `EmailSender` (Cloudflare).
- **Cinematische eerste login**: aankomst-animatie ("Welkom in de wereld van…"), de constellatie
  onthult de eigen ster, daarna vloeiend dóór naar **"Bouw je profiel met AI"** (de gesprek-flow
  uit `docs/PRD-ai-profiel.md`). Eén doorlopende, verbluffende ervaring — geen losse stappen.
- Warme, peer-to-peer microcopy; lege/tussen-staten ook af.

## 3. B — Slimme interface (feedback + suggesties overal)
- **Altijd-bereikbare feedback-affordance** op elke pagina (subtiel "✦ deel je gedachte" → kosmisch
  paneel). Slaat feedback op met paginacontext. Optioneel: Claude categoriseert/ vat samen voor de admin.
- **Contextuele suggesties**: de UI biedt proactief next steps (profiel-completeness, "voeg een
  project toe", relevante tags) — klein en tasteful, niet pusherig.

## 4. C — Centrale pagina's
- **Roadmap** (`/roadmap`): levende, transparante roadmap (fasen + status), kosmische stijl,
  admin-curated (DB-backed `roadmap_item`). Toont waar het platform heen gaat.
- **Ideeënbus** (`/ideeen`): leden dienen ideeën in, kunnen op elkaars ideeën **stemmen/reageren**;
  admin kan een idee **promoten naar de roadmap**. Sluit de lus feedback → idee → roadmap.

## 5. Datamodel (additief, Alembic)
- `feedback` {member fk?, page_path, body, kind, ai_summary?, created_at}
- `idea` {member fk, title, body, status (open|gepland|gedaan|afgewezen), created_at}
- `idea_vote` {idea fk, member fk, unique(idea,member)}
- `roadmap_item` {title, description, status, phase, order, linked_idea_id?}

## 6. Beslissingen (veto welkom)
- **Zichtbaarheid**: roadmap + ideeënbus voorlopig **besloten (alleen-leden)**; roadmap kan bij de
  publieke launch openbaar (statement van ambitie). Ideeënbus blijft besloten.
- **Stemmen**: lichtgewicht upvote (één per lid per idee). Geen downvotes.
- **Roadmap-bron**: admin-curated; ideeën voeden 'm (promotie-knop), niet auto-gegenereerd.
- **Moderatie**: admin kan ideeën/feedback verbergen.

## 7. Edge cases & safeguards
- AVG: feedback/ideeën zijn ledendata → verwijderbaar; geen PII afdwingen.
- Anti-spam: rate-limit op feedback/idee-indiening per lid.
- CSRF op alle POSTs; require_member; besloten content `noindex` + login-gated.
- Lege staten ("nog geen ideeën — start de eerste") in volle kosmische glorie.

## 8. Fasering
- **E1**: feedback-affordance overal + opslag + admin-overzicht.
- **E2**: ideeënbus (indienen, stemmen, status) + admin-moderatie/promotie.
- **E3**: roadmap-pagina (DB-backed, admin-curated) + koppeling met ideeën.
- **E4**: gestylede e-mails + cinematische onboarding die doorvloeit naar de AI-profielbouw.

## 9. Succescriterium
Elk van deze randen voelt als onderdeel van één verbluffend geheel: een lid dat binnenkomt wordt
verrast, kan overal moeiteloos meedenken, en ziet transparant waar de wereld heen gaat.
