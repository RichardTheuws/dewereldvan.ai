# PRD — Notificatie-kanalen (lid-gekozen, uitbreidbaar)

**Status**: in aanbouw · **Versie doc**: 1.0.0 · **Datum**: 2026-06-20
**Aanleiding**: Richard (2026-06-20): "geen e-mail meer behalve de magic-link;
als een lid Telegram heeft, laat het lid de voorkeur kiezen — en maak dit
uitbreidbaar naar andere/nieuwe kanalen. E-mail is een verouderd concept."
Zie memory [[dewereldvan-notificaties]].

## Inzicht: AUGMENT, geen tweede notificatie-systeem
De app heeft al **state-derived pull-chips** (nudge_service): de chip wordt
afgeleid uit domein-staat (ontdekking klaar, nieuwe match, wachtende intro) en
verschijnt als het lid de canvas opent. Dat blijft het **in-app kanaal** — geen
notificatie-inbox erbij. We voegen alleen een **push-laag** toe: een `notify()`-
dispatcher die — náást de pull-chip — een bericht stuurt naar het door het lid
**gekozen push-kanaal** (Telegram). Default = in-app (pull, geen push).

## Niet-doelen
- Geen e-mail voor notificaties (alléén de magic-link blijft e-mail).
- Geen notificatie-inbox/lees-status (de pull-chips dekken in-app al).
- Geen per-event-granulariteit in v1 (één voorkeurskanaal per lid).

## Ontwerp
### Datamodel (migratie 0020)
- `member_channel(member_id, channel, address, link_token, verified_at, created_at)`
  — uniek (member_id, channel). Pre-link: `link_token` gezet, `address`/`verified_at`
  leeg. Na koppeling: `address` = telegram chat_id, `verified_at` = nu, `link_token` leeg.
- `notification_pref(member_id uniek, channel)` — gekozen kanaal; default `in_app`.
Beide CASCADE op het lid + in `delete_member_completely` (AVG).

### Kanaal-abstractie (`notification_service`)
- `Notification(kind, title, body, url)` — één te bezorgen gebeurtenis.
- Notifier-registry: `in_app` (no-op push: de pull-chip dekt 't) + `telegram`.
- `notify(db, member, notif)`: kies het voorkeurskanaal; push als 't een verifieerd
  push-kanaal is, anders no-op (in-app pull dekt 't). Best-effort, faalt nooit hard.
- Uitbreidbaar: nieuw kanaal = een Notifier + enum-waarde + (evt.) koppel-flow.

### Telegram (`telegram_service`, gegate op `TELEGRAM_BOT_TOKEN`)
- Koppelen: "Verbind Telegram" → eenmalige `link_token` → deep-link
  `t.me/<bot>?start=<token>`. Het lid opent 'm; de bot-**webhook**
  (`POST /telegram/webhook`, secret-header) ontvangt `/start <token>` → map token →
  lid, sla chat_id op, `verified_at`. Webhook ipv polling: we hebben al een tunnel
  (lage op-last). Eenmalige `setWebhook` idempotent bij startup als de creds er zijn.
- Verzenden: Bot API `sendMessage(chat_id, text)`.

### Voorkeur-UI
Sectie "Notificaties" (op de verbind-pagina): kies kanaal + "Verbind Telegram"
(toont de deep-link). Zichtbaar dat in-app altijd werkt; Telegram = optionele push.

### Bedrading (events → notify, e-mail eruit)
- Ontdekking klaar → `notify(member, DiscoveryReady)` (náást de bestaande chip).
- Matchmaking-intro → `notify(to_member, IntroReceived)` i.p.v. de intro-e-mail.
- (Magic-link blijft e-mail — enige uitzondering.)

## Eerlijke trade-off
Een lid met default in-app (geen Telegram) dat de app niet opent, mist een
realtime seintje (voorheen ging er een mail). Bewuste keuze (Richard): e-mail
eruit; Telegram is dé manier voor realtime push.

## Setup (Richard, eenmalig)
1. Maak een bot via **@BotFather** → `TELEGRAM_BOT_TOKEN` + bot-username.
2. Zet in de M4-`.env`: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`,
   `TELEGRAM_WEBHOOK_SECRET` (willekeurig). Redeploy → webhook registreert zichzelf.

## Fasering
- **Nu**: model + dispatcher + in-app(no-op) + Telegram (link+webhook+send) + UI +
  bedrading (discovery + intro) + e-mail eruit. Gegate op de bot-creds.
- **Later**: per-event-voorkeuren; extra kanalen (WhatsApp/push/MCP-agent-push).
