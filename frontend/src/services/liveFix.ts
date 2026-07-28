import { useSyncExternalStore } from "react";
import { bearingDegrees, haversineMeters } from "@/utils/geo";
import { msToKnots } from "@/utils/format";

// Live instrument state for navigation mode (components/registra/): the most
// recent GPS fix plus the running session aggregates, published straight from
// the recording watcher.
//
// Deliberately NOT its own GPS watcher. nativeRecording.ts already holds one
// open for the whole recording; a second `addWatcher` would be a second GPS
// session and more battery drain — the opposite of what navigation mode is
// for. nativeRecording calls `pushFix()` from inside its existing callback,
// after its own 1 Hz sample throttle, so there is exactly one throttle in the
// system and what the display shows is exactly what lands in the GPX.
//
// Dependency direction is one-way: nativeRecording → liveFix. Nothing here
// touches the filesystem, the recording index, or upload state.

/** The plugin's location payload, as far as this module needs it. Mirrors
 * @capacitor-community/background-geolocation's `Location` type — `speed` and
 * `bearing` really are nullable there (no fix quality, or a device that just
 * doesn't report them), hence the fallbacks below. */
export interface PluginLocation {
  latitude: number;
  longitude: number;
  time: number;
  accuracy?: number | null;
  speed?: number | null;
  bearing?: number | null;
}

export interface LiveFix {
  lat: number;
  lon: number;
  at: number; // epoch ms, from the fix itself — not Date.now()
  sogKts: number | null;
  cogDeg: number | null;
  accuracyM: number | null;
}

export interface LiveState {
  fix: LiveFix | null;
  distanceM: number;
  maxSogKts: number;
  avgSogKts: number;
  fixCount: number;
}

// A phone's raw SOG jitters by a few tenths of a knot even at a steady speed,
// and an undamped number that large is unreadable. This is the weight given
// to each new sample in the exponential moving average — ~2-3s of smoothing at
// 1 Hz, slow enough to settle and fast enough to show an acceleration.
const SOG_SMOOTHING = 0.4;

// A fix pair further apart than this (app backgrounded, GPS gap) says nothing
// useful about current speed; closer than this is a duplicate timestamp, which
// would divide by ~0.
const MIN_DT_S = 0.5;
const MAX_DT_S = 10;

// Below this step distance the movement is indistinguishable from GPS noise:
// COG is held at its last value and the step isn't added to the distance run.
// Without this a boat sitting head-to-wind shows a spinning compass and
// "sails" a couple of miles at anchor overnight. Scaled by the reported
// accuracy so a poor fix has to move further to be believed.
const noiseFloorM = (accuracyM: number | null) => Math.max(3, (accuracyM ?? 0) / 2);

const EMPTY: LiveState = Object.freeze({
  fix: null,
  distanceM: 0,
  maxSogKts: 0,
  avgSogKts: 0,
  fixCount: 0,
});

// The snapshot is built here, on write, and handed out by reference —
// getSnapshot must never construct a value, or useSyncExternalStore's
// Object.is check fails every render and loops forever. Same discipline as
// nativeRecording.saveIndex()'s `index = [...index]`.
let state: LiveState = EMPTY;
let sogSum = 0;
const listeners = new Set<() => void>();

function publish(next: LiveState) {
  state = next;
  listeners.forEach((l) => l());
}

/** Feeds one GPS fix into the live display. Called by nativeRecording's
 * watcher callback; no-op-safe to call with fixes arriving out of order. */
export function pushFix(loc: PluginLocation): void {
  const prev = state.fix;
  const at = loc.time || Date.now();
  const accuracyM = loc.accuracy ?? null;

  const stepM = prev ? haversineMeters(prev.lat, prev.lon, loc.latitude, loc.longitude) : 0;
  const dtS = prev ? (at - prev.at) / 1000 : 0;
  const usableStep = prev != null && dtS >= MIN_DT_S && dtS <= MAX_DT_S;
  const moved = usableStep && stepM > noiseFloorM(accuracyM);

  // Prefer what the OS reports; derive from the last fix only when it doesn't.
  let sogKts: number | null = loc.speed != null ? msToKnots(loc.speed) : null;
  if (sogKts == null && usableStep) sogKts = msToKnots(stepM / dtS);
  if (sogKts != null && prev?.sogKts != null) {
    sogKts = prev.sogKts + SOG_SMOOTHING * (sogKts - prev.sogKts);
  }

  let cogDeg = loc.bearing ?? null;
  if (cogDeg == null && moved) {
    cogDeg = bearingDegrees(prev!.lat, prev!.lon, loc.latitude, loc.longitude);
  }
  // Hold rather than spin: a stationary boat has no meaningful course.
  if (cogDeg == null) cogDeg = prev?.cogDeg ?? null;

  const fixCount = state.fixCount + 1;
  // Aggregates use the SMOOTHED speed on purpose — off a raw value, one GPS
  // glitch would pin a bogus max for the rest of the session.
  const smoothed = sogKts ?? 0;
  sogSum += smoothed;

  publish({
    fix: { lat: loc.latitude, lon: loc.longitude, at, sogKts, cogDeg, accuracyM },
    distanceM: state.distanceM + (moved ? stepM : 0),
    maxSogKts: Math.max(state.maxSogKts, smoothed),
    avgSogKts: sogSum / fixCount,
    fixCount,
  });
}

/** Clears the fix and the session aggregates. Called when a recording starts
 * and stops — NOT on pause/resume, since a paused-then-resumed recording is
 * still one session and its totals should carry across the gap. */
export function reset(): void {
  sogSum = 0;
  publish(EMPTY);
}

function subscribe(onChange: () => void) {
  listeners.add(onChange);
  return () => listeners.delete(onChange);
}

/** Live GPS readout, re-rendering at the watcher's 1 Hz sample rate.
 *
 * Call this ONLY inside the navigation-mode overlay subtree. Calling it from
 * RegistraPage (or anywhere above it) would re-render that whole page — the
 * recordings list and its queries included — once a second, for nothing. */
export function useLiveState(): LiveState {
  return useSyncExternalStore(subscribe, () => state);
}
