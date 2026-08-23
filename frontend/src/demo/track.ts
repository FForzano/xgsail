import type {
  GpsPoint,
  PolarPoint,
  ScalarSample,
  SessionLeg,
  SessionManeuver,
  SessionStats,
  TrueWindPoint,
  VmgPoint,
} from "@/types";
import { nextDemoId } from "./ids";

// The demo outing: an afternoon training session off Campione del Garda in
// the Ora, the lake's reliable summer southerly. The track is generated and
// everything else (legs, maneuvers, VMG, wind, stats, heart rate) is derived
// from it, so the map, the speed chart and every analysis table describe the
// same sail instead of three unrelated sets of numbers.

// Mid-lake off Campione, so the whole generated track stays on the water.
const ORIGIN_LAT = 45.827;
const ORIGIN_LNG = 10.748;
const TWD_DEG = 190;
const TWS_KTS = 12;
const UPWIND_TWA_DEG = 45;
const DOWNWIND_TWA_DEG = 140;
const UPWIND_KTS = 5.9;
const DOWNWIND_KTS = 8.6;
const SAMPLE_S = 3;
const MANEUVER_S = 15;
/** How long the boat takes to build back up to target speed after a
 * maneuver — the dip itself ends with the turn, the recovery bleeds into the
 * leg that follows. */
const RECOVERY_S = 24;
/** Fraction of boat speed left at the exit of each maneuver. */
const MANEUVER_DIP: Record<SessionManeuver["maneuver_type"], number> = {
  tack: 0.42,
  gybe: 0.74,
  course_change: 0.88,
};

type PointOfSail = "upwind" | "downwind";
interface LegSpec {
  point: PointOfSail;
  tack: "port" | "starboard";
  durationS: number;
}

const LEG_PLAN: LegSpec[] = [
  { point: "upwind", tack: "starboard", durationS: 420 },
  { point: "upwind", tack: "port", durationS: 330 },
  { point: "upwind", tack: "starboard", durationS: 390 },
  { point: "upwind", tack: "port", durationS: 300 },
  // Bearing away onto port keeps the transition a ~95° course change rather
  // than a physically odd 175° swing across the wind.
  { point: "downwind", tack: "port", durationS: 360 },
  { point: "downwind", tack: "starboard", durationS: 330 },
  { point: "downwind", tack: "port", durationS: 345 },
  { point: "upwind", tack: "port", durationS: 285 },
];

const RAD = Math.PI / 180;
const norm360 = (deg: number): number => ((deg % 360) + 360) % 360;
/** Signed shortest turn from `a` to `b`, so a tack through north interpolates
 * the short way round instead of spinning 300°. */
const turn = (a: number, b: number): number => ((b - a + 540) % 360) - 180;
const round = (v: number, digits: number): number => Number(v.toFixed(digits));

/** Deterministic jitter — a random speed trace would make the demo's numbers
 * different on every reload. */
function lcg(seed: number): () => number {
  let s = seed;
  return () => {
    s = (s * 1664525 + 1013904223) % 4294967296;
    return s / 4294967296;
  };
}

function advance(lat: number, lon: number, headingDeg: number, meters: number) {
  return {
    lat: lat + (meters * Math.cos(headingDeg * RAD)) / 111_320,
    lon: lon + (meters * Math.sin(headingDeg * RAD)) / (111_320 * Math.cos(lat * RAD)),
  };
}

const twaOf = (point: PointOfSail): number =>
  point === "upwind" ? UPWIND_TWA_DEG : DOWNWIND_TWA_DEG;
const speedOf = (point: PointOfSail): number => (point === "upwind" ? UPWIND_KTS : DOWNWIND_KTS);
const headingOf = (spec: LegSpec): number =>
  norm360(spec.tack === "starboard" ? TWD_DEG - twaOf(spec.point) : TWD_DEG + twaOf(spec.point));
const maneuverBetween = (a: LegSpec, b: LegSpec): SessionManeuver["maneuver_type"] =>
  a.point !== b.point ? "course_change" : a.point === "upwind" ? "tack" : "gybe";

/** The outing starts a few days back so the demo never reads as stale. */
function demoStartMs(): number {
  const d = new Date();
  d.setDate(d.getDate() - 6);
  d.setHours(15, 10, 0, 0);
  return d.getTime();
}

interface Step {
  ms: number;
  lat: number;
  lon: number;
  heading: number;
  sog: number;
  twa: number;
}

interface Span {
  from: number;
  to: number;
}

const steps: Step[] = [];
const legSpans: Array<Span & { spec: LegSpec }> = [];
const maneuverSpans: Array<Span & { type: SessionManeuver["maneuver_type"]; turnDeg: number }> = [];

{
  const rnd = lcg(20260816);
  let lat = ORIGIN_LAT;
  let lon = ORIGIN_LNG;
  let ms = demoStartMs();

  const push = (heading: number, sog: number, twa: number) => {
    steps.push({ ms, lat, lon, heading: norm360(heading), sog, twa });
    ({ lat, lon } = advance(lat, lon, heading, sog * 0.514444 * SAMPLE_S));
    ms += SAMPLE_S * 1000;
  };

  LEG_PLAN.forEach((spec, i) => {
    const previous = LEG_PLAN[i - 1];
    if (previous) {
      const type = maneuverBetween(previous, spec);
      const fromHeading = headingOf(previous);
      const turnDeg = turn(fromHeading, headingOf(spec));
      const from = steps.length;
      const n = Math.round(MANEUVER_S / SAMPLE_S);
      for (let k = 0; k < n; k++) {
        const f = (k + 1) / (n + 1);
        const base = speedOf(previous.point) + (speedOf(spec.point) - speedOf(previous.point)) * f;
        // Speed falls away through the turn and is still down at its exit —
        // what climbs back is the following leg, below.
        const dip = 1 - (1 - MANEUVER_DIP[type]) * Math.min(1, f / 0.6);
        const twa = twaOf(previous.point) + (twaOf(spec.point) - twaOf(previous.point)) * f;
        push(fromHeading + turnDeg * f, base * dip, twa);
      }
      maneuverSpans.push({ type, turnDeg, from, to: steps.length - 1 });
    }

    const from = steps.length;
    const heading = headingOf(spec);
    const base = speedOf(spec.point);
    const exitFactor = previous ? MANEUVER_DIP[maneuverBetween(previous, spec)] : 1;
    for (let k = 0; k < Math.round(spec.durationS / SAMPLE_S); k++) {
      const gust = 1 + 0.06 * Math.sin(k / 7) + 0.05 * (rnd() - 0.5);
      const recovery = exitFactor + (1 - exitFactor) * Math.min(1, (k * SAMPLE_S) / RECOVERY_S);
      push(heading + 2.5 * Math.sin(k / 5) + (rnd() - 0.5), base * gust * recovery, twaOf(spec.point));
    }
    legSpans.push({ spec, from, to: steps.length - 1 });
  });
}

const secondsAt = (index: number): number => Math.round(steps[index].ms / 1000);
const slice = (span: Span): Step[] => steps.slice(span.from, span.to + 1);
const mean = (values: number[]): number => values.reduce((a, b) => a + b, 0) / values.length;
const stdDev = (values: number[]): number => {
  const avg = mean(values);
  return Math.sqrt(mean(values.map((v) => (v - avg) ** 2)));
};
/** Distance in nautical miles covered by a run of fixes, at SAMPLE_S each. */
const distanceNm = (run: Step[]): number => mean(run.map((s) => s.sog)) * ((run.length * SAMPLE_S) / 3600);

export const demoStartIso = new Date(steps[0].ms).toISOString();
export const demoEndIso = new Date(steps[steps.length - 1].ms).toISOString();

export const demoGps: GpsPoint[] = steps.map((s) => ({
  t: new Date(s.ms).toISOString(),
  lat: round(s.lat, 6),
  lon: round(s.lon, 6),
  speed_kn: round(s.sog, 2),
  course: round(s.heading, 1),
}));

export const demoLegs: SessionLeg[] = legSpans.map(({ spec, from, to }) => {
  const run = slice({ from, to });
  const speeds = run.map((s) => s.sog);
  const avgSpeed = mean(speeds);
  return {
    id: nextDemoId(),
    leg_type: spec.point,
    start_time: secondsAt(from),
    end_time: secondsAt(to),
    duration_sec: run.length * SAMPLE_S,
    distance_nm: round(distanceNm(run), 3),
    avg_speed_kts: round(avgSpeed, 2),
    max_speed_kts: round(Math.max(...speeds), 2),
    avg_vmg_kts: round(avgSpeed * Math.abs(Math.cos(twaOf(spec.point) * RAD)), 2),
    avg_heel_deg: round(spec.point === "upwind" ? 12.5 : 6.5, 1),
    avg_twa_deg: twaOf(spec.point),
    tack: spec.tack,
    std_heading_deg: round(stdDev(run.map((s) => s.heading)), 1),
    num_points: run.length,
    start_lat: round(run[0].lat, 6),
    start_lon: round(run[0].lon, 6),
    end_lat: round(run[run.length - 1].lat, 6),
    end_lon: round(run[run.length - 1].lon, 6),
  };
});

export const demoManeuvers: SessionManeuver[] = maneuverSpans.map(({ type, turnDeg, from, to }) => {
  const run = slice({ from, to });
  const windowSteps = Math.round(21 / SAMPLE_S);
  const before = mean(steps.slice(Math.max(0, from - windowSteps), from).map((s) => s.sog));
  const after = mean(steps.slice(to + 1, to + 1 + windowSteps).map((s) => s.sog));
  const minSpeed = Math.min(...run.map((s) => s.sog));
  const recovered = steps.findIndex((s, i) => i > to && s.sog >= before * 0.95);
  const straightLineM = before * 0.514444 * run.length * SAMPLE_S;
  const actualM = mean(run.map((s) => s.sog)) * 0.514444 * run.length * SAMPLE_S;
  return {
    id: nextDemoId(),
    maneuver_type: type,
    original_maneuver_type: type,
    corrected_by_user: false,
    source: "detected",
    rejected: false,
    pending: false,
    start_time: secondsAt(from),
    end_time: secondsAt(to),
    duration_sec: run.length * SAMPLE_S,
    speed_loss_kts: round(before - minSpeed, 2),
    speed_before_kts: round(before, 2),
    speed_min_kts: round(minSpeed, 2),
    speed_after_kts: round(after, 2),
    recovery_time_sec: recovered > to ? (recovered - to) * SAMPLE_S : run.length * SAMPLE_S,
    heading_change_deg: round(turnDeg, 1),
    distance_lost_m: round(straightLineM - actualM, 1),
    start_lat: round(run[0].lat, 6),
    start_lon: round(run[0].lon, 6),
    features: { max_heel_deg: round(type === "tack" ? 16.4 : 9.8, 1) },
  };
});

/** Mean of one maneuver metric per type, in the `{type: {metric: …}}` shape
 * the analysis section's summary table and violin chart both read. */
function maneuverGroup(type: SessionManeuver["maneuver_type"]) {
  const group = demoManeuvers.filter((m) => m.maneuver_type === type);
  const stat = (values: number[]) => {
    const sorted = [...values].sort((a, b) => a - b);
    const avg = mean(values);
    return {
      values: sorted,
      mean: round(avg, 2),
      median: round(sorted[Math.floor(sorted.length / 2)], 2),
      std: round(stdDev(values), 2),
      min: round(sorted[0], 2),
      max: round(sorted[sorted.length - 1], 2),
      q25: round(sorted[Math.floor(sorted.length * 0.25)], 2),
      q75: round(sorted[Math.floor(sorted.length * 0.75)], 2),
    };
  };
  return {
    group,
    metrics: {
      speed_loss_kts: stat(group.map((m) => m.speed_loss_kts)),
      recovery_time_sec: stat(group.map((m) => m.recovery_time_sec)),
      duration_sec: stat(group.map((m) => m.duration_sec)),
    },
  };
}

const tacks = maneuverGroup("tack");
const gybes = maneuverGroup("gybe");
const courseChanges = maneuverGroup("course_change");

export const demoManeuverSummary: Record<string, unknown> = {
  tacks: {
    count: tacks.group.length,
    avg_speed_loss_kts: tacks.metrics.speed_loss_kts.mean,
    avg_recovery_sec: tacks.metrics.recovery_time_sec.mean,
    avg_duration_sec: tacks.metrics.duration_sec.mean,
  },
  gybes: {
    count: gybes.group.length,
    avg_speed_loss_kts: gybes.metrics.speed_loss_kts.mean,
    avg_recovery_sec: gybes.metrics.recovery_time_sec.mean,
    avg_duration_sec: gybes.metrics.duration_sec.mean,
  },
  course_changes: {
    count: courseChanges.group.length,
    avg_speed_loss_kts: courseChanges.metrics.speed_loss_kts.mean,
    avg_recovery_sec: courseChanges.metrics.recovery_time_sec.mean,
    avg_duration_sec: courseChanges.metrics.duration_sec.mean,
  },
};

export const demoViolin = { tack: tacks.metrics, gybe: gybes.metrics };

// Every other fix — the series only feeds the playback readout and the chart
// overlay, so the full 3 s cadence would just inflate the payload.
export const demoVmgSeries: VmgPoint[] = steps
  .filter((_, i) => i % 2 === 0)
  .map((s) => ({
    timestamp: Math.round(s.ms / 1000),
    vmg_kts: round(s.sog * Math.abs(Math.cos(s.twa * RAD)), 2),
    twa_deg: round(s.twa, 1),
    boat_speed_kts: round(s.sog, 2),
    tws_kts: TWS_KTS,
  }));

export const demoTrueWind: TrueWindPoint[] = steps
  .filter((_, i) => i % 20 === 0)
  .map((s, i) => ({
    timestamp: Math.round(s.ms / 1000),
    twd_deg: round(TWD_DEG + 6 * Math.sin(i / 4), 1),
    tws_kts: round(TWS_KTS + 1.6 * Math.sin(i / 3), 1),
    twa_deg: round(s.twa, 1),
    boat_speed_kts: round(s.sog, 2),
    heading_deg: round(s.heading, 1),
    source: "estimated",
  }));

const totalDistanceNm = demoLegs.reduce((sum, l) => sum + l.distance_nm, 0);

export const demoStats: SessionStats = {
  distance_m: Math.round(totalDistanceNm * 1852),
  avg_speed_kts: round(mean(steps.map((s) => s.sog)), 2),
  max_speed_kts: round(Math.max(...steps.map((s) => s.sog)), 2),
  duration_s: steps.length * SAMPLE_S,
  avg_polar_pct: 88.4,
  max_polar_pct: 103.1,
  computed_at: demoEndIso,
};

// A measured polar needs far more angles than a single beat-and-run visits,
// so the curve comes from a shape function instead of the track — same thing
// the pipeline would have accumulated over a season of sailing.
const POLAR_SHAPE: Array<[number, number]> = [
  [30, 0.28], [40, 0.46], [45, 0.52], [50, 0.56], [60, 0.63], [70, 0.68],
  [80, 0.72], [90, 0.75], [100, 0.77], [110, 0.78], [120, 0.74], [130, 0.68],
  [140, 0.61], [150, 0.53], [160, 0.45], [170, 0.38], [180, 0.34],
];
const POLAR_TWS = [8, 12, 16];

function polarCurve(gain: number, samples: number): PolarPoint[] {
  return POLAR_TWS.flatMap((tws) =>
    POLAR_SHAPE.map(([twa, factor]) => {
      const speed = tws * factor * gain;
      return {
        twa_deg: twa,
        tws_kts: tws,
        speed_kts: round(speed, 2),
        vmg_kts: round(Math.abs(speed * Math.cos(twa * RAD)), 2),
        sample_count: samples,
      };
    }),
  );
}

export const demoPolarPoints = polarCurve(1, 42);
export const demoPolarTarget = polarCurve(1.08, 8);

// One crew member's watch: heart rate every 15 s, cumulative kcal alongside
// it, and the two sparse HealthKit series (HRV, respiration).
const hrAt = (index: number): number => {
  const s = steps[index];
  const effort = s.sog / DOWNWIND_KTS;
  return Math.round(112 + 34 * effort + 8 * Math.sin(index / 40));
};

export const demoHeartRate: ScalarSample[] = steps
  .filter((_, i) => i % 5 === 0)
  .map((s, i) => ({ t: new Date(s.ms).toISOString(), bpm: hrAt(i * 5) }));

export const demoEnergy: ScalarSample[] = steps
  .filter((_, i) => i % 5 === 0)
  .map((s, i) => ({ t: new Date(s.ms).toISOString(), kcal: round(i * 1.05, 1) }));

export const demoHrv: ScalarSample[] = steps
  .filter((_, i) => i % 100 === 0)
  .map((s, i) => ({ t: new Date(s.ms).toISOString(), ms: 46 + Math.round(9 * Math.sin(i / 2)) }));

export const demoRespiration: ScalarSample[] = steps
  .filter((_, i) => i % 100 === 0)
  .map((s, i) => ({ t: new Date(s.ms).toISOString(), brpm: 19 + Math.round(4 * Math.sin(i / 3)) }));

export const demoAvgHr = Math.round(mean(demoHeartRate.map((s) => s.bpm ?? 0)));
export const demoMaxHr = Math.max(...demoHeartRate.map((s) => s.bpm ?? 0));
export const demoMinHr = Math.min(...demoHeartRate.map((s) => s.bpm ?? 0));
export const demoTotalKcal = demoEnergy[demoEnergy.length - 1].kcal ?? 0;

// The two ends of the course. The Ora blows from the south, so the beat runs
// down the lake: the windward mark is the southernmost point the track
// reaches, the leeward one is where the session started.
const windwardStep = steps.reduce((a, b) => (b.lat < a.lat ? b : a));
export const demoWindwardPosition = {
  lat: round(windwardStep.lat, 6),
  lng: round(windwardStep.lon, 6),
};
export const demoLeewardPosition = { lat: round(ORIGIN_LAT, 6), lng: round(ORIGIN_LNG, 6) };
