# Implementatie-spec (DEFINITIEF, build-klaar) — Agent-Shell Fase 1

**VERSION-doel:** `0.15.0` (MINOR — nieuwe feature, backwards-compatible)
**Status:** afgeleid via understand→design→red-team workflow (`wf_162a87d1`, 12 agents). 6 blockers
gesloten in de Finalize-stap; elke fix draagt een `RT-FIX`-marker + dekkende test.
**Bron-PRD:** [PRD-agent-shell.md](PRD-agent-shell.md).

> Dit is het build-contract voor Fase 1. De geordende stappenlijst onderaan is bedoeld om sequentieel
> uitgevoerd te worden (datamodel → engine → router → templates → suggesties → a11y/footer → tests).

---

## 0. Uitgangspunten (hard, niet-onderhandelbaar)

1. **Opus 4.8-contract**: `client.messages.stream(...)` krijgt NOOIT `temperature`/`top_p`/`top_k`/
   `budget_tokens`; `thinking={"type":"adaptive"}` blijft; `stop_reason=="refusal"` blijft VÓÓR
   `content` gecheckt. De surface-tool wijzigt geen enkele `stream()`-parameter — alleen `TOOLS` groeit.
2. **Grounding-poort**: de engine produceert NOOIT HTML of modeltekst-als-interface. `surface` levert
   uitsluitend een gevalideerd `{view, params}`-signaal; de **router** rendert het echte fragment uit
   de DB in een **eigen `SessionLocal`**. Onbekende view / verzonnen slug / lege rij → `None` → géén
   surface-event (identiek aan de bestaande kaart-poort).
3. **AVG één-schrijf-pad**: `concierge_turn` wordt expliciet gewist in `delete_member_completely`
   (niet op cascade leunen — de SQLite-suite zet `PRAGMA foreign_keys` niet aan).
4. **Geen tweede palette/stijl**: hergebruik `cosmic.css`-tokens, de `concierge-card--in`-keyframe en
   de bestaande fragment-templates.
5. **Dual-shell, één engine**: de root-route kiest de shell op login+approved-state (lid → agent-canvas;
   anders → `index.html`). `TOOLS` blijft voor iedereen identiek; de route-laag vertaalt
   `navigate→surface` voor leden (`_NAV_TO_SURFACE` + `/leden/{slug}`-patroon).
6. **History-discipline (hard)**: `concierge_state` slaat NOOIT een lege/whitespace turn op en NOOIT
   iets anders dan platte `str` (geen tool_use/thinking-blokken cross-turn). De `pending or "Hallo"`-
   bodemgarantie blijft ook voor leden. Voorkomt het permanente-400-vergiftigingspad.

---

## 1. Datamodel + migratie (eerst)

- **`app/models/concierge.py`**: `ConciergeTurn` (id, member_id FK `member.id` ondelete CASCADE +
  index, role `String(20)`, content `Text`, created_at server_default now). `Text` aan import.
  Relationship `member` ↔ `Member.concierge_turns`.
- **`app/models/member.py`**: TYPE_CHECKING-import `ConciergeTurn`; relationship
  `concierge_turns` (cascade all, delete-orphan) onder `nudge_dismissals`.
- **`app/models/__init__.py`**: import + `__all__`.
- **`alembic/versions/0009_concierge_turn.py`** (NEW): `down_revision="0008_widen_audit_action"`,
  `create_table` + index `ix_concierge_turn_member_id`, reversibele downgrade, geen dialect-guard.
- **`app/services/account_deletion.py`** (AVG): `ConciergeTurn` in de import-tuple uit `app.models`
  (anders `NameError`); `db.execute(delete(ConciergeTurn).where(... == member_id))` direct vóór de
  AiChatTurn-delete; docstring bijwerken.

## 2. Engine — `app/services/concierge_service.py`

- `SURFACE_REGISTRY: dict[str, set[str]]` = `{members_grid:{tag,maakt,zoekt}, member_detail:{slug},
  ideas_list:set(), roadmap_board:set(), profile_view:{slug}}`.
- `surface`-tool in `TOOLS` (enum `list(SURFACE_REGISTRY)`, optionele `params`-object).
- `tool_surface(args)`: valideer view ∈ registry; whitelist param-keys; **alleen `str`/`int`-waarden**
  door (list/dict/None gedropt), stringify+strip. Onbekende view → `{"error": ...}`.
- `run_tool`: `if name == "surface": return tool_surface(args), []`.
- `stream_concierge(...)`: extra param `on_surface`; in de tool_use-tak ná `run_tool`, als
  `name=="surface"` en result een dict met `"view"` → `on_surface({"view":..., "params":...})`.
  **Geen enkele `stream()`-parameter wijzigt.**

## 3. Router — `app/routers/concierge.py`

- `_SURFACE_LOADERS` (module): view → `(template, ctx)`-builder. Loaders krijgen
  `(db, params, member_id, is_admin)` — GEEN request-gebonden ORM-`member` (thread-safety). Lid wordt
  zo nodig in `surface_db` herladen via `db.get(Member, member_id)`.
  - `members_grid` → `members/_grid.html`
  - `member_detail`/`profile_view` → `concierge/_card.html` (via `_public_profile_by_slug`; `None` →
    grounding-stop)
  - `ideas_list` → `ideas/_list.html`
  - `roadmap_board` → `roadmap/_board.html`
- `_nav_to_surface(url)`: `/leden|/ideeen|/roadmap` → vaste view; `/leden/{slug}` (regex) →
  `member_detail`; `/logout` + overig → `None` (echte navigate).
- `_render_surface_by_signal(signal)`: eigen `SessionLocal`; loader → `None` bij geen rij; wrap in
  **precies één** `<section class="surface-card" data-surface="{view}" role="group" aria-label="Interface">`.
  `_member_id`/`_is_admin` vóór de threadpool-hop uit de request-`db` lezen.
- Zesde kanaal `surface_ch`; `surface_done` in init **én** de `while not (...)`-conditie (anders drain-hang).
- Nav-tak: lid-navigate → `_nav_to_surface` → surface-event; lege render → **fallback naar
  navigate-event** (nooit stil niets); anoniem/`/logout`/overig → navigate-event.
- Surface-tak: `surface_ch.get` → `_render_surface_by_signal` → `event: surface` + choreografie-pauze.
- **State**: `post_message` persisteert user-turn alleen bij non-empty tekst; `stream()` laadt
  `concierge_state.load_messages(db, member.id, limit=20)` met non-empty bodemgarantie (`pending or
  "Hallo"`); ná de drain assistant-turn alleen bij non-empty buffer in een eigen `SessionLocal`.
- `GET /concierge/chips` (chips-route); `_nudge_view_model` krijgt een `surface:`-tak.

### `app/services/concierge_state.py` (NEW)
Platte-tekst helpers: `append_turn(db, member_id, role, content)` — coerce→`str`, weiger leeg/whitespace
(return `None`), geen JSON-blok; `load_messages(db, member_id, limit=20)` — laatste N oplopend, lege
defensief weggefilterd; `clear_turns`.

## 4. Templates

- **`_concierge.html`** (EDIT): host-id-blok (`#concierge-materialisatie`/`-flow`/`-results`)
  conditioneel achter `{% if not concierge_host_owned %}` (default false) → geen dubbele ids op de canvas.
- **`concierge/_canvas.html`** (NEW): standalone cosmic-doc ZONDER `_cosmic_nav`; `noindex`; htmx +
  htmx-ext-sse **synchroon in de head**; host-div draagt `hx-ext="sse"`; **GEEN `aria-live` op `<main>`**
  (enige polite-region = `#concierge-flow`); `{% set concierge_host_owned = true %}` vóór de
  `_concierge.html`-include; `#canvas-suggesties`-mount; footer-fallback; `_cosmic_bg`/`_preview_banner`/
  `ai/_cosmic_canvas` hergebruikt; eenvoudige microcopy.
- **`concierge/_stream.html`** (EDIT): verse `sse-swap="surface"`-proxy (beforeend in
  `#concierge-results`); `htmx:afterSwap`-listener uitgebreid met focus + announce voor
  `data-surface`-fragmenten naast de bestaande `concierge-card--in`-animatie. NIET direct op
  `#concierge-results` binden.
- **`concierge/_footer_fallback.html`** (NEW): subtiele glyph-toggle (`aria-expanded`/`aria-controls`,
  Escape sluit) → route-menu met **echte `<a href>`**-knoppen (progressive enhancement: JS doet in-stroom
  surface alleen als de agent beschikbaar is, anders volgt de browser de href); Uitloggen = echte link;
  `<noscript>`-fallback; reduced-motion-tak.
- **`concierge/_chips.html`** (NEW): focusbare chip-buttons + dismiss naar bestaande
  `/concierge/nudge/dismiss`; `surface:`/`navigate:`/`connect:`-acties; hergebruikt `_nudge.html`-look.
- **`app/static/cosmic.css`** (EDIT): `.surface-card` (neutrale single-node wrapper) +
  `.canvas`/`.canvas-chips`/`.canvas-fallback`-tokens; nieuwe animaties met
  `@media (prefers-reduced-motion: reduce)`-tak. Geen tweede palette.

## 5. Root-route — `app/main.py`
`index()` splitst op login+approved → `concierge/_canvas.html`; anders (anoniem ÉN pending/geschorst) →
`index.html` met de VOLLEDIGE bestaande context-keys (`member_count`/`preview_stars`/`canonical`/
`base_url`). Imports `current_member` + `MemberStatus`.

## 6. Suggestie-chips — `app/services/nudge_service.py`
`select_chips(db, viewer, ctx, ...)` NAAST `select_nudge`: ≤3 deterministische chips uit **echte
SQL-tellingen** (verzonnen aantal = hallucinatie), `ViewContext{view,params}`-dataclass, action-type
`surface:<view>` naast `navigate:`/`connect:`, stabiele dismiss-kinds. Anoniem → alleen neutrale chips.

## 7. Tests — `tests/test_agent_shell_fase1.py` (NEW) + uitbreidingen
Dekt: registry-grens, params-whitelist+type-coercion, grounding (incl. besloten/geschorst → `None`),
single-top-level-node per surface, `concierge_turn` persist + AVG-wis (niet-vacuous: seed-eerst),
lege/refusal-turns nooit gepersisteerd, bodemgarantie, dual-shell-routing + `noindex`, single-host
(elke host-id exact 1×), canvas draagt `hx-ext="sse"`, één live-region, footer-fallback echte hrefs +
`<noscript>`, `navigate→surface` incl `/leden/{slug}` + nav-fallback, SSE-integratie (`surface`+`done`),
chip-selectie, **Opus-contract-regressie** (geen sampling/budget-params; `thinking` adaptive; `tools`
bevat `surface`). Plus `test_concierge_migration.py` (0009 round-trip) en `test_account_deletion.py`
(seed `ConciergeTurn`). Draai `pytest` (SQLite, geen Postgres).

## 8. Geordende stappen
1. Datamodel (concierge.py + member.py + __init__.py).
2. Migratie 0009.
3. AVG (account_deletion.py).
4. Engine (concierge_service.py: registry + tool + handler + run_tool + on_surface).
5. State-helper concierge_state.py (NEW).
6. Router state (post_message + stream messages-load + assistant-persist).
7. Router surface (loaders + render-poort + _nav_to_surface + surface_ch + nav-tak).
8. _concierge.html host-id conditioneel.
9. _canvas.html (NEW).
10. _stream.html surface-proxy + a11y.
11. _footer_fallback.html + _chips.html (NEW).
12. cosmic.css tokens.
13. main.py dual-shell.
14. nudge_service.py select_chips + chips-route.
15. Tests.
16. pytest groen.
17. VERSION 0.15.0 + CHANGELOG + commit.

> Volledige red-team-analyse + code-skeletten: workflow-run `wf_162a87d1` (transcript bewaard in de
> sessie-map). De 6 gesloten blockers: history-vergiftiging, dubbele host-ids, multi-node surface,
> a11y live-region-nesting, navigate→surface-gat, footer-fallback zonder agent.
