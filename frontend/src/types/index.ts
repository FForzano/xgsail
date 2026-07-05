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
  created_at?: string;
}

export interface UserSummary {
  id: UUID;
  first_name: string | null;
  last_name: string | null;
  email: string;
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

export interface BoatClass {
  id: UUID;
  name: string;
  description: string | null;
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

export interface Activity {
  id: UUID;
  name: string | null;
  type: ActivityType;
  visibility: Visibility;
  club_id: UUID | null;
  group_id: UUID | null;
  race_id: UUID | null;
  created_by: UUID | null;
  started_at: string | null;
  ended_at: string | null;
}

export interface Mark {
  id: UUID;
  activity_id: UUID;
  mark_role: string; // start_pin | start_rc | windward | leeward | gate | finish…
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

export interface SessionCrew {
  user_id: UUID;
  sailing_role: string;
  user?: UserSummary | null;
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

/** `GET /races/{id}/data` — per-session windowed sensor data. */
export interface RaceData {
  race_id: UUID;
  activity_id: UUID | null;
  sessions: Record<
    UUID,
    {
      session_id: UUID;
      boat: { id: UUID; name: string; sail_number: string | null } | null;
      sensors: Record<string, GpsPoint[]>;
    }
  >;
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
}

export interface WindObservation {
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
