import type {
  Activity,
  ActivityData,
  Boat,
  BoatMember,
  BoatNote,
  BoatSessionNote,
  Club,
  ClubMember,
  Device,
  DeviceHealth,
  FileRef,
  ImageRef,
  Mark,
  NavSourceCandidate,
  Post,
  Regatta,
  Session,
  SessionAnalysis,
  SessionCrew,
  SessionPhysio,
  SessionStream,
  UserSummary,
} from "@/types";
import {
  DEMO_ACTIVITY_ID,
  DEMO_BOAT_CLASS_ID,
  DEMO_BOAT_ID,
  DEMO_CLUB_ACTIVITY_ID,
  DEMO_CLUB_ID,
  DEMO_CREW_ID,
  DEMO_DEVICE_ID,
  DEMO_DEVICE_TYPE_ID,
  DEMO_PAST_ACTIVITY_ID,
  DEMO_REGATTA_ID,
  DEMO_SESSION_ID,
  DEMO_SESSION_UPLOAD_ID,
  DEMO_SKIPPER_ID,
  nextDemoId,
} from "./ids";
import {
  demoAvgHr,
  demoEndIso,
  demoEnergy,
  demoGps,
  demoHeartRate,
  demoHrv,
  demoLeewardPosition,
  demoLegs,
  demoManeuverSummary,
  demoManeuvers,
  demoMaxHr,
  demoMinHr,
  demoPolarTarget,
  demoRespiration,
  demoStartIso,
  demoTotalKcal,
  demoTrueWind,
  demoViolin,
  demoVmgSeries,
  demoWindwardPosition,
} from "./track";

// A session's series are fetched straight from `download_url` by
// `useStreamJson`, which never goes through `request()` — inlining them as
// data: URIs is what lets that hook load demo data unchanged. Same trick for
// images: an <img> resolves a data: URI without a round trip.
const jsonUrl = (value: unknown): string =>
  `data:application/json,${encodeURIComponent(JSON.stringify(value))}`;

const imageUrl = (from: string, to: string, glyph: string): ImageRef => ({
  image_id: nextDemoId(),
  url:
    "data:image/svg+xml," +
    encodeURIComponent(
      `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 200">` +
        `<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">` +
        `<stop offset="0" stop-color="${from}"/><stop offset="1" stop-color="${to}"/>` +
        `</linearGradient></defs>` +
        `<rect width="320" height="200" fill="url(#g)"/>` +
        `<text x="160" y="128" font-size="88" text-anchor="middle">${glyph}</text></svg>`,
    ),
});

const daysFromNow = (days: number): string =>
  new Date(Date.now() + days * 86_400_000).toISOString();

// --- people -------------------------------------------------------------------

const skipper: UserSummary = {
  id: DEMO_SKIPPER_ID,
  first_name: "Marco",
  last_name: "Bianchi",
  email: "marco.bianchi@example.it",
  profile_image: null,
};

const crewMember: UserSummary = {
  id: DEMO_CREW_ID,
  first_name: "Giulia",
  last_name: "Ferrari",
  email: "giulia.ferrari@example.it",
  profile_image: null,
};

// --- boat ---------------------------------------------------------------------

export const demoBoat: Boat = {
  id: DEMO_BOAT_ID,
  name: "Brezza",
  boat_class_id: DEMO_BOAT_CLASS_ID,
  sail_number: "ITA 1234",
  loa_m: 5.05,
  club_id: DEMO_CLUB_ID,
  is_guest: false,
  guest_created_by: null,
  members: [
    { user_id: DEMO_SKIPPER_ID, role: "owner", default_sailing_role: "skipper", user: skipper },
    { user_id: DEMO_CREW_ID, role: "admin", default_sailing_role: "crew", user: crewMember },
  ],
  photos: [imageUrl("#1b3b5f", "#2f9be0", "⛵")],
  cert: null,
  mbsa: null,
};

export const demoBoatMembers: BoatMember[] = demoBoat.members ?? [];

export const demoBoatNotes: BoatNote[] = [
  {
    id: nextDemoId(),
    boat_id: DEMO_BOAT_ID,
    title: "Assetto sartie — Ora media (10-14 nodi)",
    body:
      "<p>Sartie a <strong>24</strong> sul tensiometro, strallo di prua alla terza tacca. " +
      "Con l'Ora piena scarico di mezzo nodo la drizza randa per aprire il grasso in testa.</p>" +
      "<ul><li>Trasto: 2 cm sopravento</li><li>Vang: in tiro solo oltre i 12 nodi</li></ul>",
    position: 0,
    created_at: daysFromNow(-52),
    updated_at: daysFromNow(-9),
  },
  {
    id: nextDemoId(),
    boat_id: DEMO_BOAT_ID,
    title: "Derive e timoni",
    body:
      "<p>Deriva sottovento tutta abbassata in bolina, alzata di un terzo in poppa. " +
      "Controllare il gioco delle casse timone a inizio stagione: l'anno scorso vibravano sopra i 12 nodi.</p>",
    position: 1,
    created_at: daysFromNow(-40),
    updated_at: daysFromNow(-40),
  },
];

export const demoBoatSessionNotes: BoatSessionNote[] = [
  {
    session_id: DEMO_SESSION_ID,
    activity_id: DEMO_ACTIVITY_ID,
    started_at: demoStartIso,
    notes:
      "<p>Ora entrata puntuale verso le 15. Bolina buona sulle mure a dritta, " +
      "meno pulita a sinistra: virate troppo lente.</p>",
    notes_shared: true,
  },
];

// --- club ----------------------------------------------------------------------

export const demoClub: Club = {
  id: DEMO_CLUB_ID,
  name: "Circolo Velico Riva Nord",
  description:
    "<p>Circolo dell'alto Garda dedicato alla vela leggera e ai catamarani. " +
    "Allenamenti il martedì e il giovedì pomeriggio, regate sociali una domenica al mese.</p>",
  address_line_1: "Viale Giancarlo Maroni 4",
  address_line_2: null,
  city: "Riva del Garda",
  state_province: "TN",
  postal_code: "38066",
  country: "Italia",
  lat: 45.8869,
  lng: 10.8419,
  website: "https://example.it/riva-nord",
  contact_email: "segreteria@example.it",
  founded_year: 1968,
  is_active: true,
  osm_ref: null,
  logo: imageUrl("#0f2f3f", "#3fbf7f", "🏛"),
  members: [
    { user_id: DEMO_SKIPPER_ID, status: "active", created_at: daysFromNow(-720), user: skipper },
    { user_id: DEMO_CREW_ID, status: "active", created_at: daysFromNow(-400), user: crewMember },
  ],
};

export const demoClubMembers: ClubMember[] = demoClub.members ?? [];

export const demoRegatta: Regatta = {
  id: DEMO_REGATTA_ID,
  name: "Trofeo Ora del Garda",
  description: "<p>Tre prove sul percorso a bastone davanti a Riva. Deriva singola e catamarani.</p>",
  image: null,
  club_id: DEMO_CLUB_ID,
  class_id: null,
  scoring_system: "low_point",
  start_date: daysFromNow(21).slice(0, 10),
  end_date: daysFromNow(22).slice(0, 10),
  status: "planned",
  race_days: [],
};

export const demoClubActivities: Activity[] = [
  {
    id: DEMO_CLUB_ACTIVITY_ID,
    name: "Allenamento di flotta — partenze",
    type: "training",
    status: "planned",
    description: "<p>Sequenze di partenza e primo lato di bolina. Ritrovo in segreteria alle 14:30.</p>",
    visibility: "club",
    club_id: DEMO_CLUB_ID,
    group_id: null,
    race_id: null,
    created_by: DEMO_SKIPPER_ID,
    started_at: daysFromNow(4),
    ended_at: null,
    thumbnail: null,
  },
  {
    id: DEMO_PAST_ACTIVITY_ID,
    name: "Allenamento poppa e strambate",
    type: "training",
    status: "completed",
    description: "<p>Lavoro sulle strambate con onda formata.</p>",
    visibility: "club",
    club_id: DEMO_CLUB_ID,
    group_id: null,
    race_id: null,
    created_by: DEMO_SKIPPER_ID,
    started_at: daysFromNow(-11),
    ended_at: daysFromNow(-11),
    thumbnail: null,
  },
];

export const demoClubPosts: Post[] = [
  {
    id: nextDemoId(),
    owner_type: "club",
    owner_id: DEMO_CLUB_ID,
    author_id: DEMO_SKIPPER_ID,
    author: skipper,
    body:
      "<p>Sono aperte le iscrizioni al <strong>Trofeo Ora del Garda</strong>. " +
      "Bando e istruzioni di regata in segreteria.</p>",
    images: [],
    created_at: daysFromNow(-3),
    updated_at: null,
    activity_id: null,
    regatta_id: DEMO_REGATTA_ID,
    event: {
      kind: "regatta",
      id: DEMO_REGATTA_ID,
      title: "Trofeo Ora del Garda",
      date: demoRegatta.start_date,
      description: "Tre prove sul percorso a bastone davanti a Riva. Deriva singola e catamarani.",
      image: null,
    },
  },
  {
    id: nextDemoId(),
    owner_type: "club",
    owner_id: DEMO_CLUB_ID,
    author_id: DEMO_CREW_ID,
    author: crewMember,
    body:
      "<p>Ricordo che giovedì il pontile nord resta chiuso per manutenzione: " +
      "alaggio dallo scivolo centrale.</p>",
    images: [imageUrl("#1f2a44", "#4fd0e0", "📷")],
    created_at: daysFromNow(-8),
    updated_at: null,
    activity_id: null,
    regatta_id: null,
    event: null,
  },
];

// --- device --------------------------------------------------------------------

export const demoDevice: Device = {
  id: DEMO_DEVICE_ID,
  device_type_id: DEMO_DEVICE_TYPE_ID,
  external_id: "E1-GARDA-0042",
  owner_user_id: DEMO_SKIPPER_ID,
  owner_boat_id: DEMO_BOAT_ID,
  owner_club_id: null,
  nickname: "E1 di bordo",
  status: "claimed",
  claim_code_expires_at: null,
  claimed_at: daysFromNow(-34),
  registered_at: daysFromNow(-35),
};

export const demoDeviceHealth: DeviceHealth = {
  battery_pct: 82,
  battery_v: 3.94,
  firmware_version: "1.4.2",
  uptime_s: 5_412,
  reported_at: demoEndIso,
};

// --- activity / session ----------------------------------------------------------

export const demoActivity: Activity = {
  id: DEMO_ACTIVITY_ID,
  name: "Allenamento con l'Ora — Campione",
  type: "solo",
  status: "completed",
  description:
    "<p>Bolina lunga controvento verso Gargnano, poppa di rientro su Campione. " +
    "Ora stabile da sud sui 12 nodi.</p>",
  visibility: "private",
  club_id: DEMO_CLUB_ID,
  group_id: null,
  race_id: null,
  created_by: DEMO_SKIPPER_ID,
  started_at: demoStartIso,
  ended_at: demoEndIso,
  thumbnail: imageUrl("#0b2239", "#2f9be0", "🗺"),
};

export const demoSession: Session = {
  id: DEMO_SESSION_ID,
  activity_id: DEMO_ACTIVITY_ID,
  boat_id: DEMO_BOAT_ID,
  started_at: demoStartIso,
  ended_at: demoEndIso,
  status: "processed",
  thumbnail: null,
  trim_start_time: null,
  trim_end_time: null,
  notes:
    "<p>Ora entrata verso le 15:00, subito sui 12 nodi. Bolina sulle mure a dritta molto pulita, " +
    "a sinistra perdo mezzo nodo: <strong>virate troppo lente</strong>, esco basso.</p>" +
    "<ul><li>Provare la prossima volta con il trasto un dito più sopravento</li>" +
    "<li>In poppa il cat plana bene sopra i 13 nodi di vento</li></ul>",
  notes_shared: true,
};

export const demoMarks: Mark[] = [
  {
    id: nextDemoId(),
    activity_id: DEMO_ACTIVITY_ID,
    mark_role: "windward",
    lat: demoWindwardPosition.lat,
    lng: demoWindwardPosition.lng,
    set_at: demoStartIso,
  },
  {
    id: nextDemoId(),
    activity_id: DEMO_ACTIVITY_ID,
    mark_role: "leeward",
    lat: demoLeewardPosition.lat,
    lng: demoLeewardPosition.lng,
    set_at: demoStartIso,
  },
];

export const demoActivityData: ActivityData = {
  activity_id: DEMO_ACTIVITY_ID,
  sessions: {
    [DEMO_SESSION_ID]: {
      session_id: DEMO_SESSION_ID,
      boat: { id: DEMO_BOAT_ID, name: demoBoat.name, sail_number: demoBoat.sail_number },
      sensors: { gps: demoGps },
    },
  },
};

export const demoStreams: SessionStream[] = [
  {
    sensor_type: "gps",
    sample_rate_hz: 0.33,
    row_count: demoGps.length,
    download_url: jsonUrl(demoGps),
    subject_type: "boat",
    subject_user_id: null,
  },
];

export const demoCrew: SessionCrew[] = [
  { user_id: DEMO_SKIPPER_ID, sailing_role: "skipper", user: skipper },
  { user_id: DEMO_CREW_ID, sailing_role: "crew", user: crewMember },
];

export const demoAnalysis: SessionAnalysis = {
  maneuvers: demoManeuvers,
  legs: demoLegs,
  maneuver_summary: demoManeuverSummary,
  leg_comparison: null,
  correlations: null,
  violin: demoViolin,
  sensor_stats: null,
  vmg_series: demoVmgSeries,
  polar_target: demoPolarTarget,
  true_wind: demoTrueWind,
  computed_at: demoEndIso,
};

export const demoPhysio: SessionPhysio[] = [
  {
    session_upload_id: DEMO_SESSION_UPLOAD_ID,
    subject_user_id: DEMO_CREW_ID,
    user: crewMember,
    shared: true,
    is_self: false,
    stats: {
      avg_hr_bpm: demoAvgHr,
      max_hr_bpm: demoMaxHr,
      min_hr_bpm: demoMinHr,
      total_kcal: demoTotalKcal,
      avg_kcal_per_min: 4.2,
      avg_hrv_ms: 46,
      avg_resp_brpm: 19,
      hr_duration_s: 2_865,
      computed_at: demoEndIso,
    },
    hr_zones: {
      hr_max_bpm: 189,
      basis: "tanaka",
      method: "pct_max",
      zones: [
        { zone: 1, min_bpm: 95, max_bpm: 113 },
        { zone: 2, min_bpm: 114, max_bpm: 132 },
        { zone: 3, min_bpm: 133, max_bpm: 151 },
        { zone: 4, min_bpm: 152, max_bpm: 170 },
        { zone: 5, min_bpm: 171, max_bpm: 189 },
      ],
    },
    streams: [
      {
        sensor_type: "heart_rate",
        sample_rate_hz: 0.07,
        row_count: demoHeartRate.length,
        download_url: jsonUrl(demoHeartRate),
        subject_type: "crew_member",
        subject_user_id: DEMO_CREW_ID,
        physio_shared: true,
      },
      {
        sensor_type: "energy",
        sample_rate_hz: 0.07,
        row_count: demoEnergy.length,
        download_url: jsonUrl(demoEnergy),
        subject_type: "crew_member",
        subject_user_id: DEMO_CREW_ID,
        physio_shared: true,
      },
      {
        sensor_type: "hrv",
        sample_rate_hz: null,
        row_count: demoHrv.length,
        download_url: jsonUrl(demoHrv),
        subject_type: "crew_member",
        subject_user_id: DEMO_CREW_ID,
        physio_shared: true,
      },
      {
        sensor_type: "respiration",
        sample_rate_hz: null,
        row_count: demoRespiration.length,
        download_url: jsonUrl(demoRespiration),
        subject_type: "crew_member",
        subject_user_id: DEMO_CREW_ID,
        physio_shared: true,
      },
    ],
  },
];

export const demoSessionPhotos: ImageRef[] = [
  imageUrl("#123a52", "#7fd0e0", "📸"),
  imageUrl("#2a1f44", "#e0b24a", "📸"),
];

export const demoSessionVideos: FileRef[] = [];

// Empty on purpose: with a single recording device there is nothing to
// choose between, and the track-source picker stays out of the demo.
export const demoNavSources: NavSourceCandidate[] = [];
