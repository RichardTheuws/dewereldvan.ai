# PRD — Verificatie- & toegangs-links

**Versie**: 0.1.0 · **Datum**: 2026-06-18 · **Status**: 🟡 APPROVAL PENDING

## 1. Doel
Lichtgewicht, vanuit de telefoon/WhatsApp bruikbare manieren om (a) nieuwe leden te
**verifiëren** en (b) gericht **adminrechten** toe te kennen — bovenop de bestaande
approval-flow, niet in plaats daarvan. Drie link-types, één gedeeld token-mechanisme.

## 2. Context (bestaand — hergebruiken)
- Leden: open registratie → `status=pending` → admin keurt goed in `/admin/queue` →
  passwordless **magic-link** login (signed tokens, 15 min, single-use). `ADMIN_EMAILS`
  auto-admin. Rollen: `member|admin`; status: `pending|approved` (+ evt. rejected).
- Signed-token-infra (magic-links) + admin-guard + audit-log bestaan al → hergebruiken.
- **Niet** een tweede auth-systeem bouwen; deze links zijn dunne, geauditeerde acties
  bovenop het bestaande model.

## 3. De drie link-types

### 3a. Verificatie-link (lid → groep → admin klikt)
Een nieuw/`pending` lid krijgt een **unieke verificatie-link** (signed token → member-id).
Het lid plakt 'm in de WhatsApp-groep; een **admin** herkent de persoon en klikt → het lid
wordt `approved`.
- **Authz is de kern**: het token zegt *wélk* lid, de *actie* vereist een ingelogde **admin**.
  Niet-ingelogd → magic-link login eerst, dan de verifieer-pagina. Ingelogd niet-admin → nette
  weigering ("alleen beheerders kunnen verifiëren"). Zo is leaken in de groep ongevaarlijk:
  het onthult hoogstens wélk lid, niet de macht om goed te keuren.
- **Human-in-the-loop**: de bevestig-pagina toont naam + e-mail; de admin klikt alleen voor wie
  hij in de groep herkent. Idempotent (al-approved → no-op melding).

### 3b. Admin-toekenningslink (jij → 1 persoon)
Een **one-time, kort geldige** link die adminrechten verleent aan een **specifieke persoon**.
Jij genereert 'm en stuurt 'm 1-voor-1.
- **E-mail-gebonden** (default, veilig): het token is gekoppeld aan een doel-e-mail; alleen wie
  als dat lid is ingelogd kan 'm verzilveren. Anderen met de link → geweigerd. Single-use,
  expiry (default 48 u), alleen door een bestaande admin te genereren. Audit verplicht.

### 3c. Wachtlijst-invite (admin → wachtlijst-lid) — *directe use-case*
Voor de 6 bestaande wachtlijst-aanmeldingen: admin genereert per e-mail een **invite** die het
lid direct als `approved` aanmaakt + een magic-link levert om in te loggen en het profiel te
bouwen. Hergebruikt 3a's mechaniek, maar admin-geïnitieerd (geen groep-stap nodig).

## 4. Datamodel (additief, Alembic)
- `member`: + `verify_token` (uniek, nullable) of een aparte tabel `access_token`
  (`kind` = verify|admin_grant|invite, `token`, `member_id`/`target_email`, `expires_at`,
  `used_at`, `created_by`). **Voorkeur: één `access_token`-tabel** (generiek, audit-baar,
  meerdere types) i.p.v. losse kolommen.
- Audit: hergebruik bestaande `audit_log` (`action` = member_verified | admin_granted |
  invite_sent, actor + target + ts).

## 5. Routes (alle onder bestaande guards; CSRF)
- `POST /admin/leden/{id}/verify-link` (admin) → genereer/roteer verify-token, toon de te-delen URL.
- `GET  /verify/{token}` → bevestig-pagina (vereist admin-sessie; anders login-first) →
  `POST /verify/{token}` → zet `approved` + audit + redirect.
- `POST /admin/admin-grant-link` (admin) → genereer e-mail-gebonden grant-token, toon URL.
- `GET/POST /admin-grant/{token}` → na login als doel-lid: rol→admin (single-use, expiry) + audit.
- `POST /admin/wachtlijst/invite` (admin) → maak member(s) uit wachtlijst-e-mail(s) + magic-link.

## 6. Edge cases & safeguards
- **Leaked verify-link** → ongevaarlijk (actie vereist admin); toont alleen naam/e-mail.
- **Verify door verkeerde admin / spam-lid** → bevestig-pagina + audit; admin-oordeel is de control.
- **Admin-grant leaked** → e-mail-gebonden + single-use + expiry → niet door een ander te claimen.
- **Token verlopen/gebruikt** → nette melding + (verify) regenereerbaar; (grant) admin maakt nieuwe.
- **Dubbele/typo wachtlijst-e-mail** (bv. `maarten@…​.vom`) → de-dupe + validatie vóór invite;
  ongeldige adressen overslaan met melding.
- **Idempotentie** overal (her-klik = no-op, geen dubbele approval/rol).
- **Rate-limit** op token-generatie + audit op elke privilege-wijziging.
- **AVG**: wachtlijst-e-mails zijn voor launch-notificatie; invite = gerichte 1-op-1 actie,
  geen bulk-marketing; opt-out respecteren.

## 7. Fasering
- **F1**: `access_token`-tabel + verify-link (3a) + admin-guard + audit + bevestig-UI (kosmisch).
- **F2**: admin-toekenningslink (3b, e-mail-gebonden, single-use).
- **F3**: wachtlijst-invite (3c) + migratie wachtlijst → member (sluit een open taak in status.md).

## 8. Succescriterium
Een admin kan vanuit WhatsApp, op de telefoon, een lid in <10 s verifiëren door op een geplakte
link te klikken; en een doelpersoon admin maken met één gerichte, single-use link — beide
geauditeerd, geen enkele privilege-escalatie mogelijk via een geleakte link.

## 9. Open (jouw beslissing — echte voorkeuren)
1. **Verify-link geldigheid**: lang geldig (gemak) **of** vervalt na bv. 7 dagen (veiliger)?
   *Voorstel: 7 dagen + regenereerbaar.*
2. **Na verify**: lid meteen `approved` (kan direct bouwen) — *voorstel: ja.*
3. **Admin-grant**: e-mail-gebonden (veilig) **of** open single-use (makkelijker doorsturen)?
   *Voorstel: e-mail-gebonden.*
4. **Wachtlijst nú uitnodigen** voor een eerste test, of eerst F1/F2 afbouwen en dán?
   *Voorstel: eerst de verify-flow live op preview, dán 2–3 mensen handmatig uitnodigen als
   gecontroleerde test (niet alle 6 tegelijk).*
