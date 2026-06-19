# PRD — Matchmaking: vraag ↔ aanbod (Tier 1, het vlaggenschip)

**Status:** 🟡 TER GOEDKEURING (2026-06-19) — wacht op akkoord/forks vóór bouw
**Versie-doel:** 0.27.0 (MINOR — nieuwe entiteiten + match-engine + surface)
**Aanleiding:** de platform-audit (2026-06-19) — drie onafhankelijke verkenners noemden
**offering↔need-matchmaking** als grootste gat tussen wat er staat en wat de visie belooft
("wie zoekt wat ik maak", PRD.md §3 Fase 3). Het datamodel ligt klaar; alleen de waarde-laag ontbreekt.

---

## 0. Eén regel

De `Need` die leden invullen gaat eindelijk werk doen: het platform koppelt **andermans `Need`** aan
**jouw `Offering`** (en omgekeerd), legt in gewone taal uit *waarom* het past, brengt beide leden actief
samen (persistente intro + notificatie), en haalt ze terug met een wekelijkse digest. Van *nette ledengids*
naar *netwerk dat waarde teruggeeft*.

## 1. Het probleem (gegrond)

- `Need` (`app/models/need.py`) wordt vandaag **nergens** tegen `Offering` gematcht — alleen voor de
  `zoekt`-filter (`members_service.py:92`) en account-deletion. Data wordt verzameld die niets doet.
- De enige "matchmaking" is tag-overlap (`nudge_service._tag_overlap_candidate`): "Jij en X werken allebei
  aan {tag}" — mensen-met-dezelfde-hashtag, niet vraag↔aanbod.
- `connect:{slug}` zet enkel een chat-prompt klaar ("Stel me voor aan X"); **niets persisteert, niemand
  wordt genotificeerd**. Elke "connect" is een dood spoor.
- De funnel lekt 100% na onboarding: e-mail is puur transactioneel (login/approval/invite). Nul
  terugkeer-trigger.

## 2. Datamodel (holistisch, klein — augment, geen herbouw)

Hergebruikt de bestaande `Offering`/`Need` (titel + description + tags via het profiel). Twee nieuwe
entiteiten:

### `MatchSuggestion` — een gevonden koppeling (need ↔ offering), gepersisteerd
| Veld | Type | Opmerking |
|---|---|---|
| `id` | int PK | |
| `need_id` | FK need, **CASCADE** | de vraag |
| `offering_id` | FK offering, **CASCADE** | het aanbod dat erbij past |
| `seeker_member_id` | FK member, CASCADE, index | denorm: wie zoekt (= eigenaar van de need) |
| `maker_member_id` | FK member, CASCADE, index | denorm: wie maakt (= eigenaar van de offering) |
| `score` | int (0-100) | rangschikking; door de engine gezet |
| `rationale` | Text | de in-gewone-taal "waarom past dit" (door de engine) |
| `status` | enum `new · seen · dismissed · acted` | sticky dismiss; "acted" = er is een intro op gestuurd |
| `created_at` / `updated_at` | DateTime | |

Uniek `(need_id, offering_id)` (idempotent herrekenen). Zelf-match uitgesloten (`seeker != maker`).
Gepersisteerd zodat: dismiss blijft plakken, de digest/chip ernaar kan verwijzen, en we niet elke
paginaload herrekenen.

### `Connection` — een persistente intro (verzilvert de match)
| Veld | Type | Opmerking |
|---|---|---|
| `id` | int PK | |
| `from_member_id` | FK member, CASCADE | de initiatiefnemer |
| `to_member_id` | FK member, CASCADE | de ontvanger |
| `match_suggestion_id` | FK, **SET NULL**, nullable | de context (welke need↔offering) |
| `message` | Text | het door de initiatiefnemer bevestigde intro-bericht |
| `status` | enum `pending · accepted · declined` | |
| `created_at` / `responded_at` | DateTime | |

Op `pending` → e-mail + chip naar `to_member`. Op `accepted` → contact/voortzetting ontsloten (consent-poort).
AVG: beide entiteiten in `delete_member_completely` (suggesties CASCADEn via need/offering; connections
expliciet wissen).

## 3. De match-engine (de kern-keuze — zie §8 fork 1)

**Aanbeveling: LLM-geoordeelde complementariteit met goedkope SQL-kandidaatgeneratie.** Voor een besloten
community van tientallen–lage-honderden leden is dit de slimste route:

1. **Kandidaten (goedkoop, bestaande SQL):** per `Need`, haal kandidaat-`Offering`s op van *andere* leden
   via tag-overlap + `title/description ILIKE` (hergebruikt het `members_service`-patroon). Cap op N
   kandidaten.
2. **Oordeel (één gebatchte Claude-call):** laat Claude per need de kandidaten rangschikken op échte
   complementariteit en een korte, gegronde *waarom-zin* schrijven ("jij bouwt voice-agents; Hendrik zoekt
   spraak-evaluatie — dat sluit aan"). Gebruikt de **bestaande `ANTHROPIC_API_KEY`** (geen embeddings-
   provider, geen nieuwe infra). Profieltekst = data, nooit instructies (bestaande grounding-discipline).
3. **Persist:** schrijf/actualiseer `MatchSuggestion`-rijen (score + rationale + status).

Dit is écht AI-native (redeneren over complementariteit, niet substring-matchen), privacy-vriendelijk (alleen
naar Anthropic, wat al gebeurt bij profielbouw), en lage op-last. **pgvector + embeddings is de opt-in
schaal-stap** wanneer N groeit — niet nu nodig.

**Trigger:** de engine draait (a) periodiek via cron (lage op-last, unattended) en (b) bij een profiel-edit
die een need/offering raakt. Niet per request.

## 4. De ervaring — verweven in de agent-shell

- **Nieuwe surface `matches`** in de agent-canvas: "wat is er voor mij?" / "laat mijn matches zien" →
  `surface(matches)` materialiseert de match-kaarten in-stroom (kosmisch, met de waarom-zin prominent +
  een **"stel me voor"-actie**). Grounding-poort: alleen echte, gepersisteerde suggesties.
- **Chip (push):** "Iemand zoekt wat jij maakt" / "3 makers bieden wat jij zoekt" — als eerste regel in de
  canvas bij binnenkomst (push, niet pull), gegrond op `MatchSuggestion.status = new`.
- **Connect/intro:** "stel me voor aan X" rendert een voorgevuld intro-formulier (draft-patroon, 1-klik
  bevestigen) → persisteert een `Connection` → mailt de ontvanger + chip. Ontvanger accepteert/wijst af in
  de canvas; bij accept ontsluit contact/voortzetting.

## 5. Re-engagement-digest (terugbrengen — Fase 3)

Wekelijkse cron-mail per lid (hergebruikt `EmailSender` + de match-data): "nieuwe matches voor jouw vraag ·
nieuwe makers in jouw vakgebied · nieuwe ideeën/events". Unattended, lage op-last; e-mail faalt nooit silent
(bestaande `EmailSendError`-discipline). Opt-out-link verplicht (AVG).

## 6. Architectuur — hergebruik vs. nieuw
- **Hergebruik:** `Offering`/`Need` + tags, het `members_service`-kandidaatpatroon, de surface- +
  `draft_*`-machinerie, de concierge-tool-loop + grounding-poort, `EmailSender`, de nudge/chip-laag, de
  cosmic-kaart-esthetiek.
- **Nieuw:** `MatchSuggestion` + `Connection`-modellen + migratie; `match_service` (kandidaten → Claude-
  oordeel → persist); `connection_service` (intro + notificatie + accept); `surface(matches)`-loader +
  `draft_intro`-tool; cron-job(s) voor herrekenen + digest; e-mailtemplates (match-intro, digest).

## 7. Edge cases & guardrails
| Risico | Mitigatie |
|---|---|
| **Zichtbaarheid/privacy** | Zie fork 2. Contactgegevens pas ná `Connection.accepted` (consent-poort); de match-kaart toont alleen wat het profiel al deelt. |
| **Prompt-injection via profieltekst** | Tekst gaat als DATA naar Claude, nooit als instructie (bestaande discipline); de engine schrijft alleen `score`+`rationale`, kan geen tools/acties triggeren. |
| **Verzonnen matches** | De engine kiest UITSLUITEND uit echte kandidaat-offering-ids; geen id → geen suggestie (grounding-poort, spiegelt de surface-tool). |
| **Cold start (weinig leden)** | Weinig matches → de surface degradeert naar een nette "we zoeken nog mee"-staat, geen lege/kale lijst. |
| **Op-last / kosten** | Engine batcht + draait op schema/bij-edit, niet per request; kandidaten gecapt; één Claude-call per need-batch. |
| **Dood spoor** | Elke match heeft een actie (intro); elke intro notificeert; accept/decline sluit de lus. |
| **AVG** | Beide entiteiten in `delete_member_completely`; digest met opt-out; intro-mail alleen aan goedgekeurde leden. |
| **Dubbele/afgewezen suggesties** | Uniek `(need_id, offering_id)`; `dismissed` blijft sticky; geen self-match. |

## 8. Fasering
- **Fase 1 (v0.27.0):** `MatchSuggestion` + migratie + `match_service` (SQL-kandidaten → Claude-oordeel →
  persist) + `surface(matches)` + push-chip + cron-herrekenen. Tests (incl. Postgres-pariteit).
- **Fase 2 (v0.28.0):** `Connection` + `draft_intro` + notificatie-mail + accept/decline + contact-ontsluiting.
- **Fase 3 (v0.29.0):** wekelijkse re-engagement-digest (cron + e-mailtemplate + opt-out).

---

## 9. Open beslissingen (echte forks — aanbeveling per fork; bevestig in de chat)

1. **Match-engine** — (A, aanbevolen) LLM-geoordeeld + SQL-kandidaten (geen nieuwe infra, gebruikt de
   bestaande Anthropic-key, schaalt prima op community-grootte); (B) pgvector + embeddings (beste bij grote
   N, maar vereist een embeddings-provider + Postgres-image-swap + extra op-last); (C) puur structureel
   (tags/text, geen LLM) — goedkoopst maar niet "slim", blijft substring-niveau.
2. **Matchbereik/zichtbaarheid** — over wie matcht het? (A, aanbevolen) alle **goedgekeurde** leden incl.
   members-only profielen (de community is besloten → interne waarde; contact pas ná intro-accept); (B)
   alleen **publieke** profielen (conservatiever, maar de helft staat default besloten → halve community
   onzichtbaar voor matching).
3. **Proactiviteit** — (A, aanbevolen) push: top-match als eerste regel in de canvas + wekelijkse digest; (B)
   alleen pull (chip bij geopend veld), zoals nu — laagste waarde, geen terugkeer-trigger.
