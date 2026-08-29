import type { LegalDocByLang } from "./types";

/**
 * Privacy Policy (informativa ex artt. 13-14 GDPR) — IT (governing) + EN.
 *
 * ⚠️ DEVELOPER NOTE (not shown to users): good-faith draft grounded in the
 * GDPR (Reg. UE 2016/679) and D.Lgs. 196/2003 as amended by D.Lgs. 101/2018.
 * It MUST be reviewed by a qualified professional and reconciled with the
 * ACTUAL processing you carry out in production (hosting/storage providers,
 * any non-EU transfers, retention periods, analytics/cookies). Placeholders in
 * [square brackets] need real values.
 *
 * Keep PRIVACY_VERSION in sync with CURRENT_PRIVACY_VERSION in backend/legal.py.
 */
export const PRIVACY_VERSION = "2026-08-05";

const CONTROLLER = "Federico Forzano";
const EMAIL = "f.forzano@ieee.org";
const PEC = "f.forzano@pec.it";
const SERVICE_URL = "xgsail.com";

export const privacy: LegalDocByLang = {
  it: {
    title: "Informativa sulla Privacy",
    lead:
      "La presente Informativa descrive il trattamento dei dati personali degli utenti del servizio XGSail nella versione ospitata (hosted) accessibile all'indirizzo " +
      SERVICE_URL +
      ", ai sensi degli artt. 13 e 14 del Regolamento (UE) 2016/679 (“GDPR”). L'Informativa è documento distinto dai Termini e Condizioni d'uso.",
    sections: [
      {
        title: "1. Titolare del trattamento",
        blocks: [
          {
            type: "p",
            text:
              "Titolare del trattamento per la versione hosted è " +
              CONTROLLER +
              " (email: " +
              EMAIL +
              "; PEC: " +
              PEC +
              "; indirizzo: Via Giuseppe Saragat, 1, 44122 Ferrara (FE), Italia).",
          },
          {
            type: "p",
            text:
              "Per le istanze self-hosted gestite da terzi, titolare del trattamento è il soggetto che gestisce l'istanza: la presente Informativa non si applica a tali installazioni.",
          },
        ],
      },
      {
        title: "2. Categorie di dati trattati",
        blocks: [
          {
            type: "ul",
            items: [
              "Dati dell'account: indirizzo email, password (conservata solo in forma di hash), nome e cognome (se forniti), data di nascita (facoltativa), immagine del profilo (facoltativa), preferenze (es. unità di misura, lingua).",
              "Dati di attività e sessione: tracce GPS (dati di geolocalizzazione), dati di sensori, orari, parametri di navigazione e prestazione, foto e video caricati.",
              "Dati relativi a barche, club, gruppi ed equipaggi gestiti dall'Utente.",
              "Dati tecnici e di utilizzo: indirizzo IP, log di sistema, informazioni sul dispositivo/browser, cookie e identificatori tecnici necessari al funzionamento.",
              "Dati di terzi caricati dall'Utente: se l'Utente inserisce dati riferibili ad altre persone (ad es. membri dell'equipaggio), è responsabile di averle informate e, ove necessario, di averne acquisito il consenso.",
            ],
          },
        ],
      },
      {
        title: "3. Finalità e basi giuridiche",
        blocks: [
          {
            type: "ul",
            items: [
              "Fornire il Servizio e gestire l'account, incluse archiviazione ed elaborazione dei contenuti caricati e le funzioni di condivisione — base giuridica: esecuzione del contratto (art. 6.1.b GDPR).",
              "Garantire la sicurezza, prevenire abusi e usi impropri, e assicurare il corretto funzionamento tecnico — base giuridica: legittimo interesse del Titolare (art. 6.1.f GDPR).",
              "Adempiere a obblighi di legge e gestire eventuali contestazioni — base giuridica: obbligo legale (art. 6.1.c) e legittimo interesse (art. 6.1.f).",
              "Riscontrare le richieste di esercizio dei diritti dell'interessato — base giuridica: obbligo legale (art. 6.1.c).",
            ],
          },
          {
            type: "p",
            text:
              "Il Titolare non effettua profilazione né attività di marketing tramite il Servizio e non vende i dati personali a terzi.",
          },
        ],
      },
      {
        title: "4. Dati di geolocalizzazione",
        blocks: [
          {
            type: "p",
            text:
              "Le tracce GPS caricate o registrate dall'Utente costituiscono dati personali di geolocalizzazione. Sono trattate esclusivamente per fornire le funzioni di analisi, replay e condivisione della sessione, secondo le impostazioni di visibilità scelte dall'Utente. Il caricamento di tali dati è volontario e sotto il controllo dell'Utente.",
          },
        ],
      },
      {
        title: "5. Natura del conferimento",
        blocks: [
          {
            type: "p",
            text:
              "Il conferimento dei dati dell'account (in particolare l'email) è necessario per registrarsi e utilizzare il Servizio; il mancato conferimento impedisce la creazione dell'account. Il conferimento degli altri dati (es. tracce, foto, dati anagrafici facoltativi) è libero e legato alle funzioni che l'Utente sceglie di utilizzare.",
          },
        ],
      },
      {
        title: "6. Destinatari e responsabili del trattamento",
        blocks: [
          {
            type: "p",
            text:
              "Allo stato, l'applicazione e i dati sono ospitati su un server gestito direttamente dal Titolare: non sono coinvolti fornitori di hosting o di archiviazione terzi in qualità di responsabili del trattamento. Restano fermi i servizi cartografici di terze parti descritti al successivo punto 7, che il browser dell'Utente contatta direttamente e che agiscono come titolari autonomi. I dati possono essere comunicati esclusivamente:",
          },
          {
            type: "p",
            text:
              "Nome, cognome (se forniti) e immagine del profilo, se caricati, sono inoltre visibili agli altri utenti del Servizio: nei contesti collaborativi dell'applicazione (equipaggi, membri di barche, club e gruppi) e tramite la funzione di ricerca persone, che consente a qualunque utente autenticato di trovare qualunque altro utente attivo digitandone nome o email, allo scopo di invitarlo. La ricerca persone non mostra mai l'indirizzo email dei risultati; l'indirizzo email di un membro dell'equipaggio resta invece visibile, nell'elenco dell'equipaggio di una sessione, a chiunque possa vedere quella sessione secondo le impostazioni di visibilità scelte per l'attività (v. punto 4).",
          },
          {
            type: "ul",
            items: [
              "a eventuali fornitori tecnici che dovessero rendersi in futuro strettamente necessari all'erogazione del Servizio, previa loro nomina a responsabili del trattamento ai sensi dell'art. 28 GDPR (in tal caso la presente Informativa sarà aggiornata);",
              "ad autorità pubbliche, ove richiesto dalla legge.",
            ],
          },
          {
            type: "p",
            text: "I dati non sono diffusi né ceduti a terzi per finalità commerciali.",
          },
        ],
      },
      {
        title: "7. Servizi cartografici di terze parti",
        blocks: [
          {
            type: "p",
            text:
              "Le funzionalità di mappa del Servizio (visualizzazione delle tracce, carta nautica, punti d'interesse nautici, ricerca di un indirizzo) si appoggiano a servizi cartografici pubblici gestiti da soggetti terzi. Tali servizi vengono contattati direttamente dal browser o dall'app dell'Utente, senza passare dai server del Titolare (ad eccezione della miniatura delle tracce, si veda sotto): di conseguenza tali soggetti ricevono autonomamente alcuni dati e agiscono come titolari autonomi del trattamento, non come responsabili ai sensi dell'art. 28 GDPR.",
          },
          {
            type: "p",
            text: "I servizi utilizzati e i dati che ricevono sono:",
          },
          {
            type: "ul",
            items: [
              "OpenStreetMap Foundation (tile.openstreetmap.org) — mappa di base: indirizzo IP, user agent e coordinate delle porzioni di mappa visualizzate;",
              "OpenSeaMap (tiles.openseamap.org) — livello opzionale della carta nautica: indirizzo IP, user agent e coordinate delle porzioni di mappa visualizzate, solo se l'Utente attiva il livello;",
              "Overpass API (overpass-api.de) — livello opzionale dei punti d'interesse nautici: indirizzo IP, user agent e coordinate dell'area di mappa inquadrata, solo se l'Utente attiva il livello;",
              "Nominatim (nominatim.openstreetmap.org) — geocodifica di un indirizzo in coordinate: indirizzo IP, user agent e il testo dell'indirizzo cercato, solo quando l'Utente preme il pulsante di ricerca da indirizzo.",
            ],
          },
          {
            type: "p",
            text:
              "Fa eccezione la miniatura statica della traccia mostrata nelle liste di uscite e attività: in quel caso è il server del Servizio, non il browser o l'app dell'Utente, a richiedere le porzioni di mappa a OpenStreetMap Foundation per comporre l'immagine, poi servita dal Servizio stesso — è quindi l'indirizzo IP del server, non quello dell'Utente, a raggiungere tale servizio.",
          },
          {
            type: "p",
            text:
              "Nessuna di queste richieste viene effettuata finché l'Utente non apre una schermata contenente una mappa (o, per i livelli opzionali e per la geocodifica, finché non li attiva espressamente), ad eccezione della miniatura descritta sopra, generata quando la traccia viene elaborata dal Servizio. Tali servizi non impostano cookie sul dominio del Servizio. La base giuridica è l'esecuzione del contratto (art. 6.1.b GDPR) per le funzionalità di mappa richieste dall'Utente. Si invita a consultare le rispettive informative: osmfoundation.org/wiki/Privacy_Policy per i servizi della OpenStreetMap Foundation (mappa di base, Nominatim), e le condizioni d'uso pubblicate da OpenSeaMap e da Overpass API.",
          },
          {
            type: "p",
            text:
              "Le mappe includono le attribuzioni richieste dalle rispettive licenze: i dati di base sono © contributori OpenStreetMap, disponibili con licenza Open Database License (ODbL); il livello nautico è © contributori OpenSeaMap.",
          },
        ],
      },
      {
        title: "8. Trasferimenti extra-UE",
        blocks: [
          {
            type: "p",
            text:
              "I dati sono trattati e conservati su un server situato nell'Unione Europea (Italia): allo stato non è previsto alcun trasferimento verso Paesi terzi (extra SEE). Qualora, in futuro, il trattamento comportasse un trasferimento extra-SEE, esso avverrà solo in presenza di adeguate garanzie ai sensi degli artt. 44 e ss. GDPR (ad es. decisione di adeguatezza o Clausole Contrattuali Standard) e la presente Informativa sarà aggiornata.",
          },
        ],
      },
      {
        title: "9. Periodo di conservazione",
        blocks: [
          {
            type: "p",
            text:
              "I dati dell'account e i contenuti sono conservati per il tempo in cui l'account resta attivo. In caso di cancellazione dell'account, i dati sono cancellati o resi anonimi entro tempi tecnici ragionevoli, salvo l'obbligo o il diritto di conservarli per il tempo necessario ad adempiere obblighi di legge o a far valere/difendere un diritto. I log tecnici sono conservati per un periodo limitato per finalità di sicurezza.",
          },
        ],
      },
      {
        title: "10. Diritti dell'interessato",
        blocks: [
          {
            type: "p",
            text: "L'Utente può in ogni momento esercitare i diritti previsti dagli artt. 15-22 GDPR:",
          },
          {
            type: "ul",
            items: [
              "accesso ai propri dati e loro rettifica;",
              "cancellazione (“diritto all'oblio”) e limitazione del trattamento;",
              "opposizione al trattamento fondato sul legittimo interesse;",
              "portabilità dei dati;",
              "revoca del consenso, ove il trattamento sia basato sul consenso, senza pregiudizio per la liceità del trattamento precedente.",
            ],
          },
          {
            type: "p",
            text: "Le richieste possono essere inviate ai contatti del Titolare indicati al punto 1.",
          },
        ],
      },
      {
        title: "11. Reclamo all'autorità di controllo",
        blocks: [
          {
            type: "p",
            text:
              "L'interessato ha diritto di proporre reclamo all'autorità di controllo competente. In Italia è il Garante per la protezione dei dati personali (www.garanteprivacy.it). Gli utenti residenti in altri Stati membri dell'UE possono rivolgersi all'autorità di controllo del proprio Paese.",
          },
        ],
      },
      {
        title: "12. Minori",
        blocks: [
          {
            type: "p",
            text:
              "Il Servizio non è destinato ai minori di 14 anni. Se un genitore o tutore ritiene che un minore abbia fornito dati senza adeguato consenso, può contattare il Titolare per la cancellazione.",
          },
        ],
      },
      {
        title: "13. Cookie e tecnologie simili",
        blocks: [
          // DEVELOPER NOTE (not shown to users): se in futuro verranno
          // introdotti cookie non tecnici/di analisi o di terze parti,
          // aggiornare questa sezione e predisporre un meccanismo di consenso
          // (cookie banner) conforme al provvedimento del Garante.
          {
            type: "p",
            text:
              "Il Servizio utilizza cookie e archiviazione locale strettamente necessari al funzionamento (ad es. per l'autenticazione e la sicurezza), che non richiedono consenso.",
          },
        ],
      },
      {
        title: "14. Modifiche all'Informativa",
        blocks: [
          {
            type: "p",
            text:
              "La presente Informativa può essere aggiornata nel tempo. In caso di modifiche rilevanti, l'Utente ne è informato e gli può essere richiesto di prenderne nuovamente visione al successivo accesso. La data di efficacia e la versione sono indicate in cima al documento.",
          },
        ],
      },
    ],
  },
  en: {
    title: "Privacy Policy",
    lead:
      "This Privacy Policy describes how personal data of users of the XGSail service, in its hosted version available at " +
      SERVICE_URL +
      ", is processed, pursuant to arts. 13 and 14 of Regulation (EU) 2016/679 (“GDPR”). This Policy is a separate document from the Terms of Service. This is a translation; in case of conflict the Italian version prevails.",
    sections: [
      {
        title: "1. Data controller",
        blocks: [
          {
            type: "p",
            text:
              "The data controller for the hosted version is " +
              CONTROLLER +
              " (email: " +
              EMAIL +
              "; certified email/PEC: " +
              PEC +
              "; address: Via Giuseppe Saragat, 1, 44122 Ferrara (FE), Italy).",
          },
          {
            type: "p",
            text:
              "For self-hosted instances operated by third parties, the data controller is whoever operates the instance: this Policy does not apply to such installations.",
          },
        ],
      },
      {
        title: "2. Categories of data processed",
        blocks: [
          {
            type: "ul",
            items: [
              "Account data: email address, password (stored only as a hash), first and last name (if provided), date of birth (optional), profile picture (optional), preferences (e.g. units, language).",
              "Activity and session data: GPS tracks (geolocation data), sensor data, timestamps, navigation and performance parameters, uploaded photos and videos.",
              "Data about boats, clubs, groups and crews managed by the User.",
              "Technical and usage data: IP address, system logs, device/browser information, cookies and technical identifiers necessary for operation.",
              "Third-party data uploaded by the User: if the User enters data relating to other people (e.g. crew members), the User is responsible for having informed them and, where necessary, obtained their consent.",
            ],
          },
        ],
      },
      {
        title: "3. Purposes and legal bases",
        blocks: [
          {
            type: "ul",
            items: [
              "Providing the Service and managing the account, including storing and processing uploaded content and sharing features — legal basis: performance of a contract (art. 6.1.b GDPR).",
              "Ensuring security, preventing abuse and misuse, and ensuring correct technical operation — legal basis: the controller's legitimate interest (art. 6.1.f GDPR).",
              "Complying with legal obligations and handling any disputes — legal basis: legal obligation (art. 6.1.c) and legitimate interest (art. 6.1.f).",
              "Responding to requests to exercise data-subject rights — legal basis: legal obligation (art. 6.1.c).",
            ],
          },
          {
            type: "p",
            text: "The controller does not carry out profiling or marketing through the Service and does not sell personal data to third parties.",
          },
        ],
      },
      {
        title: "4. Geolocation data",
        blocks: [
          {
            type: "p",
            text:
              "GPS tracks uploaded or recorded by the User are geolocation personal data. They are processed solely to provide session analysis, replay and sharing features, according to the visibility settings chosen by the User. Uploading such data is voluntary and under the User's control.",
          },
        ],
      },
      {
        title: "5. Nature of the provision of data",
        blocks: [
          {
            type: "p",
            text:
              "Providing account data (in particular the email address) is necessary to register and use the Service; failure to provide it prevents account creation. Providing other data (e.g. tracks, photos, optional profile details) is optional and tied to the features the User chooses to use.",
          },
        ],
      },
      {
        title: "6. Recipients and processors",
        blocks: [
          {
            type: "p",
            text:
              "At present, the application and the data are hosted on a server operated directly by the controller: no third-party hosting or storage providers are involved as data processors. This is without prejudice to the third-party mapping services described in section 7 below, which the User's browser contacts directly and which act as independent controllers. Data may be disclosed only:",
          },
          {
            type: "p",
            text:
              "First name, last name (if provided) and profile picture, if uploaded, are also visible to other users of the Service: in the application's collaborative contexts (crews, boat/club/group members) and through the people-search feature, which lets any authenticated user find any other active user by typing their name or email, for the purpose of inviting them. People search never shows a result's email address; a crew member's email address remains visible, as with other crew data, in a session's crew list, to anyone who can view that session according to the visibility settings chosen for the activity (see section 4).",
          },
          {
            type: "ul",
            items: [
              "to any technical providers that may in future become strictly necessary to deliver the Service, once appointed as data processors under art. 28 GDPR (in which case this Policy will be updated);",
              "to public authorities, where required by law.",
            ],
          },
          {
            type: "p",
            text: "Data is not disseminated or transferred to third parties for commercial purposes.",
          },
        ],
      },
      {
        title: "7. Third-party mapping services",
        blocks: [
          {
            type: "p",
            text:
              "The Service's map features (track display, nautical chart, nautical points of interest, address lookup) rely on public mapping services operated by third parties. Those services are contacted directly by the User's browser or app, without passing through the controller's servers (except for the track thumbnail, see below): they therefore receive certain data on their own account and act as independent controllers, not as processors under art. 28 GDPR.",
          },
          {
            type: "p",
            text: "The services used, and the data they receive, are:",
          },
          {
            type: "ul",
            items: [
              "OpenStreetMap Foundation (tile.openstreetmap.org) — base map: IP address, user agent and the coordinates of the map tiles displayed;",
              "OpenSeaMap (tiles.openseamap.org) — optional nautical chart layer: IP address, user agent and the coordinates of the map tiles displayed, only if the User enables the layer;",
              "Overpass API (overpass-api.de) — optional nautical points-of-interest layer: IP address, user agent and the coordinates of the map area in view, only if the User enables the layer;",
              "Nominatim (nominatim.openstreetmap.org) — geocoding an address into coordinates: IP address, user agent and the address text searched for, only when the User presses the find-from-address button.",
            ],
          },
          {
            type: "p",
            text:
              "An exception is the static track thumbnail shown in the outings/activities lists: there, it is the Service's own server, not the User's browser or app, that requests the map tiles from OpenStreetMap Foundation to compose the image, which is then served by the Service itself — so it is the server's IP address, not the User's, that reaches that service.",
          },
          {
            type: "p",
            text:
              "None of these requests is made until the User opens a screen containing a map (or, for the optional layers and geocoding, until the User explicitly enables them), except for the thumbnail described above, which is generated when the Service processes the track. These services set no cookies on the Service's domain. The legal basis is performance of the contract (art. 6(1)(b) GDPR) for the map features the User requested. Please refer to their respective policies: osmfoundation.org/wiki/Privacy_Policy for OpenStreetMap Foundation services (base map, Nominatim), and the terms published by OpenSeaMap and the Overpass API.",
          },
          {
            type: "p",
            text:
              "Maps carry the attributions required by the respective licences: base data is © OpenStreetMap contributors, available under the Open Database License (ODbL); the nautical layer is © OpenSeaMap contributors.",
          },
        ],
      },
      {
        title: "8. Transfers outside the EU",
        blocks: [
          {
            type: "p",
            text:
              "Data is processed and stored on a server located in the European Union (Italy): at present no transfer to third countries (outside the EEA) takes place. Should processing in future involve a transfer outside the EEA, it will only occur under appropriate safeguards pursuant to arts. 44 et seq. GDPR (e.g. an adequacy decision or Standard Contractual Clauses), and this Policy will be updated.",
          },
        ],
      },
      {
        title: "9. Retention period",
        blocks: [
          {
            type: "p",
            text:
              "Account data and content are retained for as long as the account remains active. If the account is deleted, data is deleted or anonymised within a reasonable technical timeframe, save for any obligation or right to retain it as necessary to comply with legal obligations or to establish/defend a legal claim. Technical logs are kept for a limited period for security purposes.",
          },
        ],
      },
      {
        title: "10. Data-subject rights",
        blocks: [
          {
            type: "p",
            text: "The User may at any time exercise the rights under arts. 15-22 GDPR:",
          },
          {
            type: "ul",
            items: [
              "access to and rectification of their data;",
              "erasure (“right to be forgotten”) and restriction of processing;",
              "objection to processing based on legitimate interest;",
              "data portability;",
              "withdrawal of consent, where processing is based on consent, without affecting the lawfulness of prior processing.",
            ],
          },
          {
            type: "p",
            text: "Requests can be sent to the controller's contacts indicated in section 1.",
          },
        ],
      },
      {
        title: "11. Complaint to a supervisory authority",
        blocks: [
          {
            type: "p",
            text:
              "The data subject has the right to lodge a complaint with the competent supervisory authority. In Italy this is the Garante per la protezione dei dati personali (www.garanteprivacy.it). Users resident in other EU Member States may contact the supervisory authority of their own country.",
          },
        ],
      },
      {
        title: "12. Minors",
        blocks: [
          {
            type: "p",
            text:
              "The Service is not intended for children under 14. If a parent or guardian believes that a minor has provided data without adequate consent, they may contact the controller for deletion.",
          },
        ],
      },
      {
        title: "13. Cookies and similar technologies",
        blocks: [
          // DEVELOPER NOTE (not shown to users): if non-technical/analytics or
          // third-party cookies are introduced in future, update this section
          // and put in place a consent mechanism (cookie banner) compliant with
          // the Italian DPA (Garante) guidance.
          {
            type: "p",
            text:
              "The Service uses cookies and local storage that are strictly necessary for operation (e.g. for authentication and security), which do not require consent.",
          },
        ],
      },
      {
        title: "14. Changes to this Policy",
        blocks: [
          {
            type: "p",
            text:
              "This Policy may be updated over time. In case of significant changes, the User is informed and may be asked to review it again on their next visit. The effective date and version are shown at the top of the document.",
          },
        ],
      },
    ],
  },
};
