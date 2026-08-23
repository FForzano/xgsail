import type { UUID } from "@/types";

// Demo data for the guided tours: a fully populated activity / club / boat /
// device so a brand-new, empty account still has something for the tour to
// point at — rendered by the real pages, not a second copy of the UI.
//
// Containment rule: nothing anywhere turns "demo mode" on. A response is
// faked only when the request path itself carries one of the ids below, so
// demo data can never leak into a request about a real record. Every demo id
// (including the ones for nested rows) shares DEMO_UUID_PREFIX, which is the
// single thing `matchDemoRequest` tests for.

export const DEMO_UUID_PREFIX = "00000000-0000-4000-8000-";

const demoId = (suffix: string): UUID => `${DEMO_UUID_PREFIX}${suffix}`;

// The five entry points — what a tour step navigates to.
export const DEMO_ACTIVITY_ID = demoId("00000000d000");
export const DEMO_SESSION_ID = demoId("00000000d001");
export const DEMO_CLUB_ID = demoId("00000000d002");
export const DEMO_BOAT_ID = demoId("00000000d003");
export const DEMO_DEVICE_ID = demoId("00000000d004");

// Entities the fixtures reference but no route points at directly.
export const DEMO_SKIPPER_ID = demoId("00000000d010");
export const DEMO_CREW_ID = demoId("00000000d011");
export const DEMO_REGATTA_ID = demoId("00000000d012");
export const DEMO_BOAT_CLASS_ID = demoId("00000000d013");
export const DEMO_DEVICE_TYPE_ID = demoId("00000000d014");
export const DEMO_SESSION_UPLOAD_ID = demoId("00000000d015");
export const DEMO_CLUB_ACTIVITY_ID = demoId("00000000d016");
export const DEMO_PAST_ACTIVITY_ID = demoId("00000000d017");

// Child rows (legs, maneuvers, marks, posts, notes…) exist only inside their
// parent's payload and are never addressed by id, so they just need to be
// distinct and stable for the render's lifetime.
let childSeq = 0x100;
export const nextDemoId = (): UUID => demoId(`00000000d${(childSeq++).toString(16)}`);

/** A demo record's membership-gated sections (the club's news tab, the boat's
 * notebook and crew, a session's add-photo/note actions) are gated on `caps`,
 * which carries only real memberships — so `useCapabilities` grants them for
 * demo ids instead. Deliberately not injected into `caps.memberships`: those
 * arrays are also read as "does this user own a boat yet", which a demo boat
 * must not answer for. */
export const isDemoId = (id: UUID | null | undefined): boolean =>
  typeof id === "string" && id.startsWith(DEMO_UUID_PREFIX);
