# PRD — dewereldvan MCP-server: "praat met dewereldvan vanuit je eigen AI-tool"

**Status:** 🟡 TER GOEDKEURING (2026-06-19) — wacht op akkoord/forks vóór bouw
**Versie-doel:** 0.29.0 (MINOR — nieuwe entiteit + MCP-laag + tunnel-ingress)
**Aanleiding (eigenaar):** activatie — zoveel mogelijk WhatsApp-groepsleden een profiel laten maken. De
leden zijn AI-bouwers die de hele dag in agentic tooling leven; de website is een context-switch, hun editor
is thuis. Eigenaars-idee: laat coders dewereldvan.ai vanuit hun eigen systeem "praten".

---

## 0. Eén regel

Een **MCP-server** zodat AI-bouwers dewereldvan.ai als tool koppelen aan Claude Code / Cursor / hun eigen
agents en er rechtstreeks mee werken: hun **profiel bouwen/bijwerken**, de gids doorzoeken, hun matches
ophalen en intro's sturen — **zonder hun editor te verlaten**. Dunne laag over de bestaande services;
auth via een persoonlijk token.

## 1. Waarom dit activatie aanjaagt (de hefboom)

- **Nul context-switch**: je maakt je profiel ín de tool waar je toch al zit. Schrijven (een profiel
  oplevert) gebeurt waar de maker werkt.
- **Het ís de wow** (Ervaringsmandaat, letterlijk voor wie dagelijks met AI bouwt): "ik voegde mezelf toe
  aan dewereldvan vanuit Claude Code."
- **Ingebouwde groei-loop**: één `claude mcp add dewereldvan …`-commando + "kijk wat je nu kunt" is precíés
  de demo die in de WhatsApp-groep rondgaat. Elke gekoppelde coder werft de volgende.

## 2. Datamodel — `PersonalToken` (klein, hergebruikt het magic-link-patroon)

| Veld | Type | Opmerking |
|---|---|---|
| `id` | int PK | |
| `member_id` | FK member, **CASCADE**, index | het token handelt UITSLUITEND namens dit lid |
| `token_hash` | String(64), unique, index | **alleen de hash** (sha256+SECRET_KEY, `security.hash_token`); de ruwe token wordt één keer getoond, nooit opgeslagen |
| `label` | String(80) | bv. "Claude Code op mijn MacBook" |
| `created_at` | DateTime server_default | |
| `last_used_at` | DateTime, nullable | voor zichtbaarheid + opschoning |
| `revoked_at` | DateTime, nullable | intrekken zonder verwijderen (audit) |

Eén Alembic-migratie. AVG: `PersonalToken` in `delete_member_completely`; bij `suspend` worden tokens
ingetrokken. **Nooit role-escalatie**: een token = "act as dit approved lid", precies de invite-grant-grens.

## 3. De MCP-server (transport + auth)

- **Officiële MCP Python SDK** (FastMCP, Streamable HTTP) — niet zelf het protocol bouwen. Nieuwe dep
  (`mcp`). Gemount op de bestaande web-container onder **`/mcp`** (hergebruikt dezelfde DB-sessie + services;
  lage op-last, geen tweede stack).
- **Auth = persoonlijk Bearer-token (PAT)**. De client stuurt `Authorization: Bearer <token>`; een
  ASGI-auth-laag verifieert (`verify_token` tegen `token_hash`, niet-revoked), resolvet het lid en scope't
  élke tool-call tot dat lid. Geen lid → 401. Per-token rate-limit (glijdend uur-venster).
- **Tunnel-ingress**: nieuwe Cloudflare-hostname **`mcp.dewereldvan.ai → http://web:8000/mcp`** (DNS CNAME
  proxied via CF API; zelfde tunnel `dewereldvan-app`). Geen open poorten.

## 4. De tools (read + write — write ís de activatie-hefboom)

Alle tools handelen namens het geauthenticeerde lid; schrijven loopt door dezelfde Pydantic-validatie als
het web; lezen respecteert zichtbaarheid + de consent-poort.

| Tool | Doet | Hergebruikt |
|---|---|---|
| `wie_ben_ik` | mijn profiel (kopregel, bio, projecten, zoekvragen, tags, compleetheid, zichtbaarheid) | `profile_service.get_or_create_profile` |
| `werk_profiel_bij` | kopregel/bio/"wat ik maak"/tags/zichtbaarheid bijwerken | `profile_service.update_profile` / `set_tags` |
| `voeg_project_toe` | een project ("wat ik maak") toevoegen (title, description?, url?) | `profile_service.add_offering` |
| `voeg_zoekvraag_toe` | een "waar ik naar zoek" toevoegen | `profile_service.add_need` |
| `zoek_makers` | de gids doorzoeken (tag/maakt/zoekt) | `members_service.list_public_profiles` |
| `mijn_matches` | mijn vraag↔aanbod-koppelingen | `match_service.list_for_member` |
| `stel_voor` | een intro sturen aan een maker (slug + bericht) | `connection_service.create_intro` + mail |
| `hoe_werkt_dewereldvan` | korte, gegronde uitleg (resource) | gecureerde tekst |

**Fase 2 (na akkoord):** `bouw_profiel_uit_link(url)` — laat de bestaande AI-profielbouw-pipeline een profiel
optrekken uit een site/GitHub vanuit de editor. Bewust Fase 2: het is de zwaarste call (LLM + fetch, traag/
async) en verdient een eigen, robuuste vorm; de structured write-tools leveren de activatie al.

## 5. De "verbind je tool"-sectie (op het profiel)

Een klein paneel op de profielpagina: **"Verbind je AI-tool"** → genereer een token (één keer getoond) +
kant-en-klare config om te kopiëren:

```
claude mcp add --transport http dewereldvan https://mcp.dewereldvan.ai \
  --header "Authorization: Bearer dwv_…"
```

Plus een Cursor/generieke JSON-variant. Tokens beheren (label, laatst gebruikt, intrekken) in hetzelfde
paneel. Dit is de onboarding van de MCP-server.

## 6. Architectuur — hergebruik vs. nieuw
- **Hergebruik:** `profile_service` (alle schrijf-functies bestaan), `members_service`, `match_service`,
  `connection_service`, `security.generate_token`/`hash_token`/`verify_token` (zoals magic-link), de
  Cloudflare-tunnel + CF-API-deploy-flow.
- **Nieuw:** `PersonalToken`-model + migratie; de `mcp`-dep + de FastMCP-app gemount op `/mcp`; de
  Bearer-auth-laag (token→lid, scoped); de tool-definities (dunne wrappers); de "verbind je tool"-UI +
  token-CRUD-routes; de `mcp.dewereldvan.ai`-ingress.

## 7. Edge cases & guardrails
| Risico | Mitigatie |
|---|---|
| **Token-lek** | Alleen de hash opgeslagen (ruwe token één keer getoond); intrekbaar; `last_used_at`; rate-limit per token; HTTPS-only via de tunnel. |
| **Scope-creep van een token** | Een token = "act as dit approved lid"; nooit admin/role-escalatie; geschorst lid → tokens dood. |
| **Prompt-injection** | Tool-uitvoer is data voor het lid z'n eigen agent; schrijven loopt door dezelfde validatie; geen tool kan andermans data muteren. |
| **Zichtbaarheid/consent** | `zoek_makers` respecteert zichtbaarheid; `stel_voor` loopt door de consent-poort (contact pas ná accept). |
| **AVG** | `PersonalToken` in `delete_member_completely`; intrekken bij suspend. |
| **Protocol-onderhoud** | Officiële MCP-SDK i.p.v. zelfbouw → spec-updates komen via de dep. |
| **Op-last** | Gemount in de bestaande container (geen tweede service); read-tools zijn pure SQL; alleen Fase-2 `bouw_profiel_uit_link` doet een LLM-call. |

## 8. Fasering
- **Fase 1 (v0.29.0):** `PersonalToken` + migratie + token-CRUD + "verbind je tool"-UI; FastMCP op `/mcp` +
  Bearer-auth; de 8 read/write-tools (§4 minus `bouw_profiel_uit_link`); `mcp.dewereldvan.ai`-ingress;
  docs. Tests (token-auth, scoping, elke tool, AVG, Postgres-pariteit).
- **Fase 2 (na akkoord):** `bouw_profiel_uit_link` (AI-profielbouw vanuit de editor) + rijkere resources +
  evt. OAuth-flow naast PAT.

---

## 9. Open beslissingen (echte forks — aanbeveling per fork; bevestig in de chat)

1. **Auth-model** — (A, aanbevolen) **persoonlijk Bearer-token (PAT)**: lid-vriendelijk, één keer
   `claude mcp add` met een header, hergebruikt het magic-link-hashpatroon. (B) **OAuth**: de "nettere"
   standaard, maar zwaarder te bouwen/onderhouden en meer onboarding-stappen voor het lid.
2. **Fase-1-reikwijdte** — (A, aanbevolen) **structured read+write eerst** (de 8 tools, snel + robuust);
   `bouw_profiel_uit_link` in Fase 2. (B) **meteen ook `bouw_profiel_uit_link`** (max wow, maar de zwaarste
   call → trager eerste ship, async-vorm nodig).
3. **Hosting** — (A, aanbevolen) **gemount op `/mcp` in de web-container** achter `mcp.dewereldvan.ai`
   (hergebruikt DB/services, lage op-last). (B) aparte MCP-service/container (meer isolatie, meer op-last).
