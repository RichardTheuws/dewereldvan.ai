# Vision — de profielbouw als levend, wordend artefact

**Status**: 🟡 TER BEVESTIGING (richting vastleggen vóór herbouw) · **Datum**: 2026-06-18
**Leidend**: `CLAUDE.md` ervaringsmandaat + `docs/STYLEGUIDE.md` (kosmisch + eenvoudige taal).

## Het idee (één zin)
Je profiel **bouwt zichtbaar zichzelf** terwijl je vertelt wie je bent — en je verfijnt het
daarna **inline**, in datzelfde scherm. Geen chat-transcript, geen aparte preview, geen los
bewerk-formulier. Eén doorlopende flow: **tekst → wordend profiel → inline bijschaven.**

## De flow (één geheel)
1. **Vertel.** Eén invoer: "Vertel wie je bent en wat je maakt — plak je links." (tekst, later evt. voice).
2. **Het profiel vult zichzelf, live in beeld.** Terwijl de AI je links ophaalt en synthetiseert,
   verschijnt het **echte profiel** (de kosmische profielpagina-vorm): headline, bio, rollen,
   projecten-met-beeld, "wat ik zoek", tags — ze materialiseren één voor één. De "AI-aan-het-werk"-
   redenering loopt subtiel mee (we hebben dat al).
3. **"Wat klopt nog niet?"** Onderaan (en inline) nodigt het systeem uit om bij te schaven.
   - **Elk veld is inline editable**: klik op de headline/bio/een project → pas direct aan.
   - **Onzekere velden zijn gemarkeerd** ("dit leidde ik af — klopt het?") i.p.v. losse chat-vragen.
   - **De profielfoto** krijgt op z'n plek de mooie upload-mogelijkheid (drag-drop), terwijl de
     basis er al volledig staat. (Auto-crop levert én een nette profielfoto én een goede
     uitsnede voor de overzichtskaart — zie de ledenpagina-feedback.)
4. **Klaar.** Je kiest zichtbaarheid en publiceert. Geen losse stappen meer.

## Wat dit vervangt
De huidige 3-staps (chat-bubbels → aparte draft-preview → apart bewerk-formulier) wordt **één**
levende ervaring. De chat verdwijnt naar de achtergrond; het **artefact** (jouw profiel) staat centraal.

## Ontwerpbeslissingen (mijn voorstel — bevestig/veto)
- **AI-vragen worden inline, geen ping-pong.** De AI bouwt het beste profiel uit je tekst en markeert
  twijfels inline (confirm/aanpas met één tik), i.p.v. losse vervolgvraag-beurten. Minder klikken, meer
  "het deed het gewoon".
- **Inline edit met htmx** per veld (klik → editbaar → opslaan), op de echte profielvorm.
- **Eenvoudige taal** (geen zweverigheid), kosmische visuele identiteit.
- **Respect voor expert-tijd**: één paragraaf in → bijna-af profiel → een paar tikken om te perfectioneren.

## Open vraag voor jou
- **Vervolgvragen**: helemaal inline-markeren (mijn voorstel), of mag de AI tóch af en toe één
  korte vraag stellen als iets cruciaal ontbreekt (bv. je rol)? (Beide kan; bepaalt de flow.)

## Hoe verder
Zodra je de richting + de open vraag bevestigt, leg ik dit vast als de te bouwen spec en herbouw
ik de profielbouw-interactie als één levende flow (ultracode). De net-gefixte enrichment/draft-engine
hergebruiken we eronder — alleen de ervaring eromheen wordt nieuw.
