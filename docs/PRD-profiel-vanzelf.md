# PRD: het profiel vult zich vanzelf

**Status**: voorstel, wacht op goedkeuring · **Datum**: 2026-11-03 · **Eigenaar**: Richard

## 1. Probleem (gemeten op 2026-11-03)

Na de open uitnodiging in de groep meldden zich op één dag 8 mensen aan. Daarvan kwamen er 7 binnen, maar
maar 1 staat openbaar mét inhoud. 5 van de 7 haakten af op `/profiel/ai/bouwen`.

Wat de data laat zien:

- **De AI vindt mensen wel, maar niemand ziet het resultaat.** Van alle 13 ontdek-runs ooit zijn er
  2 bekeken (`discovery_run.seen_at`). Vandaag: Walter Heck kreeg 10 vondsten (o.a. LinkedIn "CTO
  HeleCloud", 2 talks, 2 media), Thomas Uland 2, Robin Scholten 2. Geen van drieën heeft ze gezien.
- **De ontdekking duurt te lang om op te wachten.** Gemiddeld 13 minuten; Thomas' run 19 minuten. De
  pagina belooft "een paar minuten".
- **Zelfs hoge-zekerheidsvondsten landen niet op het profiel.** Auto-koppelen (confidence ≥ 90) gebeurt
  in de browser: de kaart POST't pas als hij gerenderd wordt. Wie weg is, krijgt niets gekoppeld.
- **De ontdekking vult de basisvelden nooit.** Kopregel, bio en rollen komen alleen uit het chatgesprek.
  Presence-vondsten (LinkedIn, eigen site) bevatten precies die informatie, maar worden bewust niet als
  nieuws gekoppeld, en verder ook nergens gebruikt.
- **Publiceren staat onderaan een lange pagina** en staat standaard op "Nee". Robin (65%) staat nog besloten.

Gevolg: wie de "laat de AI het doen"-route kiest, ziet een leeg profiel en vertrekt. Er gaat geen mail achteraan
(bewuste keuze: geen e-mail behalve de magic-link), dus ze komen ook niet terug.

## 2. Doel en meting

Een nieuw lid dat op "Zoek mij op" klikt, heeft binnen een minuut een gevuld concept-profiel in beeld, en ziet
meteen bovenaan één knop om het openbaar te zetten.

- **Succes**: van de volgende 10 nieuwe leden staan er ≥ 5 openbaar mét inhoud binnen 24 uur (nu 1 van 7).
- **Meting**: `member.created_at` → `profile.visibility = public` + `has_content_clause()`.

## 3. Oplossing

1. **Snelle eerste ronde.** De ontdekking begint met een korte presence-ronde (naam + e-maildomein, max
   ±60 s) die alleen de eigen pagina's zoekt (site, LinkedIn). De bestaande brede en media-rondes lopen
   daarna gewoon door op de achtergrond.
2. **Concept-profiel uit presence.** Zodra de eerste ronde klaar is, schrijft de server een concept in de
   **lege** velden: kopregel, bio en rollen, plus de eigen site als link. Gevulde velden raakt hij nooit aan.
   Alles blijft besloten tot het lid zelf publiceert.
3. **Auto-koppelen op de server.** Vondsten met confidence ≥ 90 worden bij het afronden van de run op de
   server gekoppeld (project → werk-item, talk/media → nieuws), via dezelfde `footprint_service.crystallize`.
   Wie wegklikt, komt dus terug bij een gevuld profiel.
4. **Live in beeld.** De bouwpagina laat de velden verschijnen terwijl de eerste ronde loopt (de bestaande
   materialisatie), met een eerlijke voortgangsregel in gewone taal ("Ik zoek je site en LinkedIn op…").
5. **Publiceren bovenaan.** Zodra er inhoud is: één kaart bovenaan "Je profiel staat klaar. Zet het openbaar"
   met de knop **Openbaar zetten** en een link "eerst bekijken als bezoeker". Het bestaande keuzeblok onderaan blijft.
6. **Eén duidelijke start.** Op `/welkom` en bovenaan `/profiel/ai/bouwen` is "Zoek mij op en bouw mijn
   profiel" de hoofdknop; het chatveld blijft eronder staan voor wie zelf wil vertellen.
7. **Eenmalige backfill** voor de leden van vandaag met afgeronde, ongeziene runs (Walter, Thomas, Robin):
   stap 2 en 3 toepassen. Niets publiceren.

## 4. Randgevallen

- **Gewoon e-maildomein** (gmail, outlook, hotmail, icloud): geen domein-hint, alleen naam. Geen vondst
  met confidence ≥ 80 → geen concept, wel de vraag "Plak je website of LinkedIn".
- **Naamgenoot**: alleen presence met confidence ≥ 85 vult velden. Lager → als suggestie tonen
  ("Ben jij dit?"), niet invullen.
- **Bedrijfsaccount** (zoals Empathree): de kopregel en bio beschrijven het bedrijf; de rol "Organisatie" in plaats van een functietitel.
- **Lid heeft al iets ingevuld**: nooit overschrijven; alleen lege velden.
- **Lid klikt "Opnieuw beginnen"**: het concept en de auto-koppelingen gaan mee weg (bestaand gedrag).
- **AI uit of fout** (`AI_ENRICH_ENABLED=false`, time-out, weigering): geen concept, de chat blijft werken,
  er komt een rustige melding. Nooit een half concept.
- **Kosten**: alleen voor ingelogde, goedgekeurde leden (bestaande regel: anonieme bezoekers krijgen nooit betaalde AI).
  De presence-ronde is kort; de dure rondes lopen al.
- **Privacy**: het concept staat op besloten tot het lid zelf klikt. Er wordt niets openbaar zonder klik.
  De zichtbaarheidspoort (`visibility.py`) blijft de enige poort.
- **Onjuiste bio**: het lid kan elk veld aanklikken en aanpassen (bestaande inline-edit). De kaart zegt
  eerlijk: "Dit heb ik over je gevonden. Klopt iets niet? Klik erop en pas het aan."

## 5. Buiten scope

- Een e-mail of push om mensen terug te halen (strijdig met de notificatiekeuze; los besluit).
- Profielen opbouwen voor mensen die zich niet zelf hebben aangemeld.
- Aanpassingen aan de brede en media-rondes zelf.

## 6. Tests

- Concept vult alleen lege velden; gevulde velden blijven gelijk.
- Presence < 85 vult niets; gmail-domein geeft geen domein-hint.
- Run-afronding koppelt ≥ 90 op de server, ook zonder browser; `crystallize` blijft idempotent (geen dubbele werk-items).
- AI-fout → geen concept, geen 5xx.
- Publiceer-kaart verschijnt alleen bij inhoud en niet-openbaar; de knop zet `visibility=public` + consent.
- Browsercheck als nieuw lid (mobiel + desktop), met AI aan op een testaccount dat daarna gewist wordt.
