import { DEMO_ACTIVITY_ID, DEMO_BOAT_ID, DEMO_CLUB_ID, DEMO_DEVICE_ID, DEMO_SESSION_ID, DEMO_UUID_PREFIX } from "./ids";
import {
  demoActivity,
  demoActivityData,
  demoAnalysis,
  demoBoat,
  demoBoatMembers,
  demoBoatNotes,
  demoBoatSessionNotes,
  demoClub,
  demoClubActivities,
  demoClubMembers,
  demoClubPosts,
  demoCrew,
  demoDevice,
  demoDeviceHealth,
  demoMarks,
  demoNavSources,
  demoRegatta,
  demoSession,
  demoSessionPhotos,
  demoSessionVideos,
  demoStreams,
  demoPhysio,
} from "./fixtures";
import { demoPolarPoints, demoStats } from "./track";

export * from "./ids";

/** Endpoints addressed by a demo id in the path itself. */
const BY_PATH: Record<string, unknown> = {
  [`/activities/${DEMO_ACTIVITY_ID}`]: demoActivity,
  [`/activities/${DEMO_ACTIVITY_ID}/sessions`]: [demoSession],
  [`/activities/${DEMO_ACTIVITY_ID}/marks`]: demoMarks,
  [`/activities/${DEMO_ACTIVITY_ID}/data`]: demoActivityData,

  [`/sessions/${DEMO_SESSION_ID}`]: demoSession,
  [`/sessions/${DEMO_SESSION_ID}/streams`]: demoStreams,
  [`/sessions/${DEMO_SESSION_ID}/stats`]: demoStats,
  [`/sessions/${DEMO_SESSION_ID}/analysis`]: demoAnalysis,
  [`/sessions/${DEMO_SESSION_ID}/crew`]: demoCrew,
  [`/sessions/${DEMO_SESSION_ID}/photos`]: demoSessionPhotos,
  [`/sessions/${DEMO_SESSION_ID}/videos`]: demoSessionVideos,
  [`/sessions/${DEMO_SESSION_ID}/physio`]: demoPhysio,
  [`/sessions/${DEMO_SESSION_ID}/nav-sources`]: demoNavSources,
  [`/sessions/${DEMO_SESSION_ID}/reanalysis-status`]: { status: null, error: null },

  [`/clubs/${DEMO_CLUB_ID}`]: demoClub,
  [`/clubs/${DEMO_CLUB_ID}/members`]: demoClubMembers,

  [`/boats/${DEMO_BOAT_ID}`]: demoBoat,
  [`/boats/${DEMO_BOAT_ID}/members`]: demoBoatMembers,
  [`/boats/${DEMO_BOAT_ID}/notes`]: demoBoatNotes,
  [`/boats/${DEMO_BOAT_ID}/session-notes`]: demoBoatSessionNotes,

  [`/devices/${DEMO_DEVICE_ID}`]: demoDevice,
  [`/devices/${DEMO_DEVICE_ID}/health`]: demoDeviceHealth,
};

/** Collection endpoints where the demo id arrives as a query parameter
 * instead — `[pathname, parameter, demo id, fixture]`. */
const BY_QUERY: Array<[string, string, string, unknown]> = [
  ["/posts", "owner_id", DEMO_CLUB_ID, demoClubPosts],
  ["/activities", "club_id", DEMO_CLUB_ID, demoClubActivities],
  ["/regattas", "club_id", DEMO_CLUB_ID, [demoRegatta]],
  ["/sessions", "activity_id", DEMO_ACTIVITY_ID, [demoSession]],
  ["/polar-points", "session_id", DEMO_SESSION_ID, demoPolarPoints],
];

function lookup(path: string): unknown {
  const queryAt = path.indexOf("?");
  const pathname = queryAt === -1 ? path : path.slice(0, queryAt);
  if (pathname in BY_PATH) return BY_PATH[pathname];
  const params = new URLSearchParams(queryAt === -1 ? "" : path.slice(queryAt + 1));
  const match = BY_QUERY.find(([p, key, id]) => p === pathname && params.get(key) === id);
  // A demo path with no fixture degrades to an empty section: mid-tour, an
  // error screen is a far worse answer than a missing block.
  return match ? match[3] : null;
}

/** The nearest fixture at or above `path`, so a mutation on a sub-resource
 * (`POST /sessions/{id}/attach-to-activity`) still resolves to the record it
 * is about — callers routinely read a field off what a mutation returns. */
function lookupNearest(path: string): unknown {
  let p = path.split("?")[0];
  while (p.includes("/")) {
    const hit = lookup(p);
    if (hit !== null) return hit;
    p = p.slice(0, p.lastIndexOf("/"));
  }
  return null;
}

/**
 * The response for a request about a demo record, or `null` when the path
 * carries no demo id and the caller should just go to the network.
 */
export function matchDemoRequest(path: string, method: string): { data: unknown } | null {
  if (!path.includes(DEMO_UUID_PREFIX)) return null;
  if (method === "GET" || method === "HEAD") return { data: lookup(path) };
  // A guided demo is read-only, and none of it exists server-side: every
  // mutation is a silent no-op resolving to the unchanged fixture, because a
  // visible failure mid-tour is worse than an action that quietly does
  // nothing.
  return { data: method === "DELETE" ? null : lookupNearest(path) };
}
