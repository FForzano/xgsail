// Wire types for the SailFrames REST API. Responses come from the backend's
// generic `ORM.to_dict()`, so these mirror the DB models in docs/er-project.md
// (UUIDs and timestamps are strings on the wire). Only fields the UI touches
// are typed — extra fields simply pass through.

export type UUID = string;

// --- media -------------------------------------------------------------------

/** Parent-mediated media read shape (`image_payload`/`file_payload`). */
export interface ImageRef {
  image_id: UUID;
  url: string;
}
export interface FileRef {
  file_id: UUID;
  url: string;
}
/** Presign response: PUT bytes to `upload_url`, then confirm on the parent. */
export interface ImageUploadTicket {
  image_id: UUID;
  upload_url: string;
}
export interface FileUploadTicket {
  file_id: UUID;
  upload_url: string;
}

// --- users / auth --------------------------------------------------------------

export interface User {
  id: UUID;
  email: string;
  first_name: string | null;
  last_name: string | null;
  dob: string | null;
  is_active: boolean;
  is_superadmin: boolean;
  status: string;
  profile_image_id: UUID | null;
  unit_system: "nautical" | "metric";
  created_at?: string;
}

export interface UserSummary {
  id: UUID;
  first_name: string | null;
  last_name: string | null;
  email: string;
  profile_image: ImageRef | null;
}

export interface Capabilities {
  user: User;
  roles: Array<{ role: string; scope_club_id: UUID | null }>;
  permissions: {
    global: string[];
    byClub: Record<string, string[]>;
  };
  memberships: {
    clubsOwned: UUID[];
    clubsMember: UUID[];
    groups: UUID[];
    boatsOwner: UUID[];
    boatsAdmin: UUID[];
  };
}

export type MembershipStatus = "invited" | "requested" | "active";

export interface MyMemberships {
  clubs: Array<{ club_id: UUID; name: string; status: MembershipStatus; created_at: string }>;
  groups: Array<{
    group_id: UUID;
    name: string;
    role: GroupRole;
    status: MembershipStatus;
    created_at: string;
  }>;
}

// --- boats ----------------------------------------------------------------------

export type HullType = "monohull" | "multihull";
// Mirrors the RYA Portsmouth Yardstick list's "Rig" (S/U) and "Spinnaker"
// (0/A/C) columns.
export type RigType = "sloop" | "una";
export type SpinnakerType = "none" | "asymmetric" | "symmetric";

export interface BoatClass {
  id: UUID;
  name: string;
  description: string | null;
  loa_m: number | null;
  beam_m: number | null;
  sail_area_sqm: number | null;
  crew_size: number | null;
  hull_type: HullType | null;
  rig_type: RigType | null;
  spinnaker_type: SpinnakerType | null;
  py_rating: number | null;
  rya_class_id: number | null;
  logo: ImageRef | null;
}

export type BoatRole = "owner" | "admin" | "visitor";

export interface BoatMember {
  user_id: UUID;
  role: BoatRole;
  default_sailing_role: string | null;
  user?: UserSummary | null;
}

export interface Boat {
  id: UUID;
  name: string;
  boat_class_id: UUID | null;
  sail_number: string | null;
  loa_m: number | null;
  notes: string | null;
  club_id: UUID | null;
  members?: BoatMember[];
  photos: Array<ImageRef | null>;
  cert?: FileRef | null;
  mbsa?: FileRef | null;
}

// --- clubs / groups ---------------------------------------------------------------

export interface Club {
  id: UUID;
  name: string;
  description: string | null;
  city: string | null;
  country: string | null;
  website: string | null;
  contact_email: string | null;
  founded_year: number | null;
  is_active: boolean;
  logo: ImageRef | null;
  // Embedded unconditionally by the backend (`ClubORM.__wire_children__`) —
  // raw membership rows (no joined `user`), enough to compute a member count
  // without a separate request to the permission-gated `/members` endpoint.
  members?: ClubMember[];
}

export interface ClubMember {
  user_id: UUID;
  status: MembershipStatus | "deleted";
  created_at: string;
  user?: UserSummary | null;
}

export type GroupRole = "owner" | "admin" | "member";

export interface GroupMember {
  user_id: UUID;
  role: GroupRole;
  status: MembershipStatus;
  created_at: string;
  user?: UserSummary | null;
}

export interface Group {
  id: UUID;
  name: string;
  description: string | null;
  visibility: "public" | "private";
  created_by: UUID | null;
  members?: GroupMember[];
  profile_image: ImageRef | null;
}

export type PostOwnerType = "club" | "group";

export interface Post {
  id: UUID;
  owner_type: PostOwnerType;
  owner_id: UUID;
  author_id: UUID | null;
  author: UserSummary | null;
  body: string;
  images: ImageRef[];
  created_at: string;
}

// --- devices -----------------------------------------------------------------------

export interface DeviceType {
  id: UUID;
  name: string;
  category: string;
  parser_key: string;
  default_sensors: string[] | null;
}

export type DeviceStatus = "unclaimed" | "claimed" | "revoked";

export interface Device {
  id: UUID;
  device_type_id: UUID;
  external_id: string | null;
  owner_user_id: UUID | null;
  owner_boat_id: UUID | null;
  owner_club_id: UUID | null;
  nickname: string | null;
  status: DeviceStatus;
  claim_code_expires_at: string | null;
  claimed_at: string | null;
  registered_at: string;
}

export interface ClaimTicket {
  device_id: UUID;
  claim_code: string;
  expires_at: string;
}

/** Health snapshot the device pushes (free-form; common fields typed). */
export interface DeviceHealth {
  battery_pct?: number;
  battery_v?: number;
  firmware_version?: string;
  uptime_s?: number;
  reported_at?: string;
  [k: string]: unknown;
}

// --- activities / sessions -----------------------------------------------------------

export type ActivityType = "race" | "training" | "solo";
export type Visibility = "public" | "club" | "group" | "private";

export type ActivityStatus = "planned" | "completed";

export interface Activity {
  id: UUID;
  name: string | null;
  type: ActivityType;
  status: ActivityStatus;
  description: string | null;
  visibility: Visibility;
  club_id: UUID | null;
  group_id: UUID | null;
  race_id: UUID | null;
  created_by: UUID | null;
  started_at: string | null;
  ended_at: string | null;
  thumbnail: ImageRef | null;
}

// Fixed set enforced by a DB check constraint (backend/db/models/activity.py
// MARK_ROLES) — mirrored in frontend/src/utils/markRoles.ts for the dropdown.
export type MarkRole =
  | "pin"
  | "rc"
  | "windward"
  | "leeward"
  | "gate_port"
  | "gate_stbd"
  | "offset"
  | "drill";

export interface Mark {
  id: UUID;
  activity_id: UUID;
  mark_role: MarkRole;
  lat: number;
  lng: number;
  set_at: string | null;
}

export type SessionStatus = "pending" | "processing" | "processed" | "failed";

export interface Session {
  id: UUID;
  activity_id: UUID;
  boat_id: UUID;
  started_at: string | null;
  ended_at: string | null;
  status: SessionStatus;
  thumbnail: ImageRef | null;
  // Reversible track-trim bounds (unix-epoch seconds) — null means no trim,
  // the full track is analyzed. See sessionsService.setTrim.
  trim_start_time: number | null;
  trim_end_time: number | null;
}

export interface SessionStream {
  sensor_type: string; // gps | imu | wind | pressure…
  sample_rate_hz: number | null;
  row_count: number | null;
  download_url: string | null;
}

export interface SessionStats {
  distance_m: number | null;
  avg_speed_kts: number | null;
  max_speed_kts: number | null;
  duration_s: number | null;
  avg_polar_pct: number | null;
  max_polar_pct: number | null;
  computed_at: string | null;
}

export type SailingRole = "skipper" | "crew" | "guest";

export interface SessionCrew {
  user_id: UUID;
  sailing_role: SailingRole;
  user?: UserSummary | null;
}

// --- session analysis ------------------------------------------------------------------

/** One detected tack/gybe. `*_time` are unix-epoch seconds (worker native). */
export interface SessionManeuver {
  id: UUID;
  maneuver_type: "tack" | "gybe" | "course_change";
  // Frozen at whatever the pipeline first assigned; unaffected by a user
  // correction (unlike maneuver_type). See PATCH .../maneuvers/{id}.
  original_maneuver_type: "tack" | "gybe" | "course_change";
  corrected_by_user: boolean;
  // 'detected' = pipeline output (the default). 'manual' = user-added via
  // POST .../maneuvers. See PATCH .../maneuvers/{id}/reject and
  // DELETE .../maneuvers/{id}.
  source: "detected" | "manual";
  // User said "not a real maneuver" — kept, not deleted, so it survives a
  // reanalysis without reappearing as a fresh row. Only ever true for
  // source === "detected".
  rejected: boolean;
  // True between a manual maneuver's creation and the worker's async stat
  // computation landing — stat fields below are 0.0 sentinels until then.
  pending: boolean;
  start_time: number;
  end_time: number;
  duration_sec: number;
  speed_loss_kts: number;
  speed_before_kts: number;
  speed_min_kts: number;
  speed_after_kts: number;
  recovery_time_sec: number;
  heading_change_deg: number;
  distance_lost_m: number | null;
  start_lat: number | null;
  start_lon: number | null;
  // Statistical feature vector computed at detection (e.g. max_heel_deg) —
  // see workers/process_upload/processing/maneuver_features.py.
  features: Record<string, unknown> | null;
}

/** One straight-line leg between maneuvers. */
export interface SessionLeg {
  id: UUID;
  leg_type: "upwind" | "downwind" | "reach";
  start_time: number;
  end_time: number;
  duration_sec: number;
  distance_nm: number;
  avg_speed_kts: number;
  max_speed_kts: number;
  avg_vmg_kts: number;
  avg_heel_deg: number | null;
  avg_twa_deg: number | null;
  tack: "port" | "starboard" | null;
  std_heading_deg: number;
  num_points: number;
  start_lat: number | null;
  start_lon: number | null;
  end_lat: number | null;
  end_lon: number | null;
}

export interface VmgPoint {
  timestamp: number;
  vmg_kts: number;
  twa_deg: number;
  boat_speed_kts: number;
  tws_kts: number | null;
}

/** One point of the true wind this session's own analysis settled on (see
 * workers/process_upload/processing/wind_estimation.py) — preferred over
 * the ephemeral WindCard/map live snapshot when present, since it's what
 * VMG/polar/legs were actually computed against. */
export interface TrueWindPoint {
  timestamp: number;
  twd_deg: number | null;
  tws_kts: number | null;
  twa_deg?: number | null;
  boat_speed_kts?: number;
  heading_deg?: number;
  source?: string;
}

/** Per-variable {mean,max,std,…} distributions (speed/apparent wind/heel/pitch). */
export type SensorStats = Record<string, Record<string, number>>;

export interface CorrelationMatrix {
  variables: string[];
  matrix: Record<string, Record<string, number>>;
}

/** `GET /sessions/{id}/analysis` — the DB-assembled analysis. Polar and scalar
 * stats come from their own endpoints (`/polar-points`, `/stats`). */
export interface SessionAnalysis {
  maneuvers: SessionManeuver[];
  legs: SessionLeg[];
  maneuver_summary: Record<string, unknown> | null;
  leg_comparison: Record<string, unknown> | null;
  correlations: CorrelationMatrix | null;
  violin: Record<string, Record<string, ViolinMetric>> | null;
  sensor_stats: SensorStats | null;
  vmg_series: VmgPoint[] | null;
  /** Max-speed-per-bucket "target" polar (vs. `points` from `/polar-points`,
   * which is the average/actual-performance polar). */
  polar_target: PolarPoint[] | null;
  true_wind: TrueWindPoint[] | null;
  computed_at: string | null;
}

export interface ViolinMetric {
  values: number[];
  mean: number;
  median: number;
  std: number;
  min: number;
  max: number;
  q25: number;
  q75: number;
}

/** Empirical per-session polar point (`GET /polar-points?session_id=`). */
export interface PolarPoint {
  twa_deg: number;
  tws_kts: number;
  speed_kts: number;
  vmg_kts: number | null;
  sample_count: number | null;
}

/** Canonical processed GPS point (worker output / GPX parse). */
export interface GpsPoint {
  t: string; // ISO timestamp
  lat: number;
  lon: number;
  speed_kn?: number | null;
  course?: number | null;
}

// --- imports --------------------------------------------------------------------------

export type ImportStatus = "pending" | "processing" | "processed" | "failed";

export interface ImportRow {
  id: UUID;
  original_filename: string;
  status: ImportStatus;
  error: string | null;
  session_id?: UUID | null;
  created_at: string;
}

export interface ImportTicket {
  import_id: UUID;
  upload_url: string;
}

// --- regattas / races ------------------------------------------------------------------

export interface Regatta {
  id: UUID;
  name: string;
  description: string | null;
  club_id: UUID;
  class_id: UUID | null;
  scoring_system: string;
  start_date: string | null;
  end_date: string | null;
  status: string;
  race_days?: RaceDay[];
}

export interface RaceDay {
  id: UUID;
  regatta_id: UUID | null;
  date: string;
  notes: string | null;
  races?: Race[];
}

export interface Race {
  id: UUID;
  race_day_id: UUID;
  race_number: number;
  status: string;
  start_time: string | null;
  activity_id?: UUID | null;
  results?: RaceResult[];
}

export interface RaceResult {
  boat_id: UUID;
  session_id: UUID | null;
  finish_time: string | null;
  elapsed_time: number | null;
  corrected_time: number | null;
  position: number | null;
  score: number | null;
  status: string; // finished | dnf | dns | dsq…
}

export type ActivitySessionData = Record<
  UUID,
  {
    session_id: UUID;
    boat: { id: UUID; name: string; sail_number: string | null } | null;
    sensors: Record<string, GpsPoint[]>;
  }
>;

/** `GET /races/{id}/data` — per-session windowed sensor data. */
export interface RaceData {
  race_id: UUID;
  activity_id: UUID | null;
  sessions: ActivitySessionData;
}

/** `GET /activities/{id}/data` — same shape as `RaceData` minus `race_id`. */
export interface ActivityData {
  activity_id: UUID;
  sessions: ActivitySessionData;
}

// --- wind ----------------------------------------------------------------------------

export interface WindStation {
  id: UUID;
  provider: string;
  external_station_id: string;
  name: string | null;
  station_type: string;
  lat: number | null;
  lng: number | null;
  keeps_local_history: boolean;
  /** Polled URL — only set for URL-based providers (cumulus_realtime,
   * cumulus_gauges_json); null for API-keyed providers (noaa_ndbc/metar). */
  source_url: string | null;
}

export interface WindObservation {
  observed_at: string;
  twd_deg: number | null;
  tws_kts: number | null;
  gust_kts: number | null;
}

/** Quick live value for WindCard/map display — NOT the per-session
 * determined wind estimate (see MapView's `sessionWind` prop for that).
 * Nothing behind this is persisted; `provider` is either a real station's
 * (with `station_name`) or `"open_meteo"` (with `model`). */
export interface WindSnapshot {
  provider: string;
  station_name?: string | null;
  model?: string;
  lat: number;
  lng: number;
  observed_at: string;
  twd_deg: number | null;
  tws_kts: number | null;
  gust_kts: number | null;
}

// --- rbac ------------------------------------------------------------------------------

export interface Role {
  id: UUID;
  name: string;
  description: string | null;
}

export interface UserRole {
  id: UUID;
  role_id: UUID;
  role?: string;
  scope_club_id: UUID | null;
}

// --- app config --------------------------------------------------------------------------

/** Singleton settings row — see backend/db/models/app_config.py.
 * `min_native_version_*` gates the native app per platform
 * (NativeVersionGate); null means no gate enforced for that platform. */
export interface AppConfig {
  min_native_version_android: string | null;
  min_native_version_ios: string | null;
}
