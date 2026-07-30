import { useMemo, useRef, useState, type CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import type { PolarPoint } from "@/types";
import {
  BASE_RGB,
  RAMP_DARK,
  RAMP_LIGHT,
  lightenRgb,
  rampRgb,
  rgbCss,
} from "@/utils/colorRamp";
import styles from "./PolarChart.module.css";

// Hand-rolled SVG polar diagram: boat speed (radius) vs true wind angle
// (0° = head to wind, at top). Only one TWS bucket is drawn at a time —
// a slider picks which one — as an average curve plus, when available, a
// "target" (max-speed) curve from `targetPoints` in a lighter tint.
// Overlaying every bucket at once was tried and proved unreadable (too many
// overlapping lobes/legend entries), hence the single-bucket + selector
// design. Recharts has no true radius-by-value polar, so this stays
// bespoke — the analysis signature chart.
const R = 140;
// Room around the ring for the angle labels so they never sit on the ring
// itself or clip against the SVG edge.
const LABEL_GAP = 16;
const CHART_PAD = 20;
const SIZE = (R + LABEL_GAP) * 2 + CHART_PAD;
const C = SIZE / 2;
const RINGS = [0.25, 0.5, 0.75, 1];
const SPOKES = [0, 45, 90, 135, 180];
// Buckets more than this far apart (backend TWA_BUCKET_SIZE=5°) are treated
// as a real gap (dead zone / no data) rather than connected with a straight
// chord — otherwise the no-go zone near 0° looks like smooth coverage.
const GAP_THRESHOLD_DEG = 9;

// Ordinal ramp (one hue, light→dark by bucket position — see dataviz skill's
// "ordinal" job) anchored on --sf-primary, so the slider position and the drawn
// curve's color always agree. Shared with the health card's heart-rate zones,
// which encode the same kind of ordered intensity — see utils/colorRamp.
const TWS_TRACK_GRADIENT = `linear-gradient(to right, ${rgbCss(RAMP_LIGHT)}, ${rgbCss(RAMP_DARK)})`;

function polar(twaDeg: number, radius: number, side: 1 | -1): [number, number] {
  const th = (twaDeg * Math.PI) / 180;
  return [C + side * radius * Math.sin(th), C - radius * Math.cos(th)];
}

/** Label anchor/offset for a spoke angle, derived from its position on the
 * ring rather than hardcoded per angle — works for any SPOKES set. Labels
 * sit just outside the ring (`R + LABEL_GAP`), centered for the top/bottom
 * spokes and left-aligned for the side ones (all on the `side=1` half). */
function labelProps(twaDeg: number): { anchor: "start" | "middle"; dx: number; dy: number } {
  const th = (twaDeg * Math.PI) / 180;
  const sin = Math.sin(th);
  const cos = Math.cos(th);
  if (Math.abs(sin) < 0.15) return { anchor: "middle", dx: 0, dy: cos > 0 ? -6 : 12 };
  return { anchor: "start", dx: 4, dy: 4 };
}

/** Builds one side's path, broken into separate `M`-started segments at gaps
 * larger than `GAP_THRESHOLD_DEG` so the dead zone shows as a real break. */
function segmentedPath(pts: PolarPoint[], maxSpeed: number, side: 1 | -1): string {
  let d = "";
  pts.forEach((p, j) => {
    const [x, y] = polar(p.twa_deg, (p.speed_kts / maxSpeed) * R, side);
    const gap = j > 0 && p.twa_deg - pts[j - 1].twa_deg > GAP_THRESHOLD_DEG;
    d += `${j === 0 || gap ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)} `;
  });
  return d.trim();
}

/** Closed lobe (mirrored side, forward then reversed) for the translucent
 * fill — only meaningful where there's no gap, so it reuses the same
 * break points as the stroke to avoid filling across the dead zone. */
function fillPath(pts: PolarPoint[], maxSpeed: number): string {
  const groups: PolarPoint[][] = [];
  for (const p of pts) {
    const g = groups[groups.length - 1];
    if (g && p.twa_deg - g[g.length - 1].twa_deg <= GAP_THRESHOLD_DEG) g.push(p);
    else groups.push([p]);
  }
  return groups
    .filter((g) => g.length > 1)
    .map((g) => {
      const fwd = g.map((p) => polar(p.twa_deg, (p.speed_kts / maxSpeed) * R, 1));
      const rev = g
        .slice()
        .reverse()
        .map((p) => polar(p.twa_deg, (p.speed_kts / maxSpeed) * R, -1));
      const pts2 = [...fwd, ...rev];
      return pts2.map(([x, y], j) => `${j === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ") + " Z";
    })
    .join(" ");
}

function nearestPoint(pts: PolarPoint[], twaDeg: number): PolarPoint | null {
  let best: PolarPoint | null = null;
  let bestDist = Infinity;
  for (const p of pts) {
    const d = Math.abs(p.twa_deg - twaDeg);
    if (d < bestDist) {
      bestDist = d;
      best = p;
    }
  }
  return best;
}

export function PolarChart({
  points,
  targetPoints,
}: {
  points: PolarPoint[];
  targetPoints?: PolarPoint[] | null;
}) {
  const { t } = useTranslation();
  const svgRef = useRef<SVGSVGElement>(null);
  const [selected, setSelected] = useState<{
    twa: number;
    side: 1 | -1;
    avg: PolarPoint | null;
    max: PolarPoint | null;
  } | null>(null);
  const [twsIndex, setTwsIndex] = useState(0);

  const { groups, maxSpeed } = useMemo(() => {
    // Average-curve buckets come only from `points` — mixing in `targetPoints`
    // here (keyed only by tws_kts, sorted only by twa_deg) used to interleave
    // an average row and a max row at the same angle, drawing a sawtooth
    // between the two radii instead of a single average curve.
    const byTws = new Map<number, PolarPoint[]>();
    let mx = 1;
    for (const p of points) {
      if (p.speed_kts > mx) mx = p.speed_kts;
      const g = byTws.get(p.tws_kts) ?? [];
      g.push(p);
      byTws.set(p.tws_kts, g);
    }
    for (const p of targetPoints ?? []) {
      if (p.speed_kts > mx) mx = p.speed_kts;
    }
    const gs = [...byTws.entries()]
      .sort((a, b) => a[0] - b[0])
      .map(([tws, pts]) => ({ tws, pts: pts.slice().sort((a, b) => a.twa_deg - b.twa_deg) }));
    return { groups: gs, maxSpeed: mx };
  }, [points, targetPoints]);

  const targetByTws = useMemo(() => {
    const m = new Map<number, PolarPoint[]>();
    for (const p of targetPoints ?? []) {
      const g = m.get(p.tws_kts) ?? [];
      g.push(p);
      m.set(p.tws_kts, g);
    }
    return m;
  }, [targetPoints]);

  if (!points.length) return null;

  // Clamp in case a re-fetch shrinks the bucket count while a later index
  // was still selected (e.g. switching to a shorter session).
  const activeIndex = Math.min(twsIndex, groups.length - 1);
  const active = groups[activeIndex];
  const activeTarget = targetByTws.get(active.tws)?.slice().sort((a, b) => a.twa_deg - b.twa_deg) ?? [];
  // Curve color is fixed (not tied to the selected wind bin) — only the TWS
  // slider's track/thumb use the light→dark ramp, purely as a visual cue for
  // where the current bucket sits in the range.
  const rampT = groups.length > 1 ? activeIndex / (groups.length - 1) : 0.5;
  const activeColor = rgbCss(BASE_RGB);
  const activeTargetColor = rgbCss(lightenRgb(BASE_RGB, 0.5));
  const thumbColor = rgbCss(rampRgb(rampT));

  const handlePick = (clientX: number, clientY: number) => {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const x = ((clientX - rect.left) / rect.width) * SIZE - C;
    const y = ((clientY - rect.top) / rect.height) * SIZE - C;
    const twa = Math.min(180, Math.max(0, (Math.atan2(Math.abs(x), -y) * 180) / Math.PI));
    const side: 1 | -1 = x >= 0 ? 1 : -1;
    const avg = nearestPoint(active.pts, twa);
    const max = nearestPoint(activeTarget, twa);
    setSelected({ twa: avg?.twa_deg ?? twa, side, avg, max });
  };

  return (
    <div className={styles.polar}>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        style={{ width: "100%", maxWidth: 380, overflow: "visible" }}
        onClick={(e) => handlePick(e.clientX, e.clientY)}
        onTouchStart={(e) => {
          const t = e.touches[0];
          if (t) handlePick(t.clientX, t.clientY);
        }}
      >
        {RINGS.map((f) => (
          <circle key={f} cx={C} cy={C} r={R * f} fill="none" stroke="var(--sf-border)" />
        ))}
        {SPOKES.map((a) => {
          const [x1, y1] = polar(a, R, 1);
          const [x2, y2] = polar(a, R, -1);
          const [lx, ly] = polar(a, R + LABEL_GAP, 1);
          const { anchor, dx, dy } = labelProps(a);
          return (
            <g key={a}>
              <line x1={C} y1={C} x2={x1} y2={y1} stroke="var(--sf-border)" strokeDasharray="2 3" />
              <line x1={C} y1={C} x2={x2} y2={y2} stroke="var(--sf-border)" strokeDasharray="2 3" />
              <text x={lx} y={ly} className={styles.lbl} textAnchor={anchor} dx={dx} dy={dy}>
                {a}°
              </text>
            </g>
          );
        })}
        <g>
          <path d={fillPath(active.pts, maxSpeed)} fill={activeColor} fillOpacity={0.15} stroke="none" />
          <path d={segmentedPath(active.pts, maxSpeed, 1)} fill="none" stroke={activeColor} strokeWidth={2} />
          <path
            d={segmentedPath(active.pts, maxSpeed, -1)}
            fill="none"
            stroke={activeColor}
            strokeWidth={2}
            opacity={0.5}
          />
          {activeTarget.length > 1 && (
            <>
              <path
                d={fillPath(activeTarget, maxSpeed)}
                fill={activeTargetColor}
                fillOpacity={0.15}
                stroke="none"
              />
              <path
                d={segmentedPath(activeTarget, maxSpeed, 1)}
                fill="none"
                stroke={activeTargetColor}
                strokeWidth={2}
              />
              <path
                d={segmentedPath(activeTarget, maxSpeed, -1)}
                fill="none"
                stroke={activeTargetColor}
                strokeWidth={2}
                opacity={0.5}
              />
            </>
          )}
        </g>
        {selected &&
          (() => {
            const [ex, ey] = polar(selected.twa, R, selected.side);
            const avgPt = selected.avg
              ? polar(selected.twa, (selected.avg.speed_kts / maxSpeed) * R, selected.side)
              : null;
            const maxPt = selected.max
              ? polar(selected.twa, (selected.max.speed_kts / maxSpeed) * R, selected.side)
              : null;
            return (
              <g>
                <line x1={C} y1={C} x2={ex} y2={ey} stroke="#fff" strokeWidth={2} opacity={0.85} />
                {avgPt && <circle cx={avgPt[0]} cy={avgPt[1]} r={4} fill="#fff" />}
                {maxPt && (
                  <circle cx={maxPt[0]} cy={maxPt[1]} r={4} fill="none" stroke="#fff" strokeWidth={2} />
                )}
              </g>
            );
          })()}
      </svg>
      {selected && (
        <div className={styles.pick}>
          <strong>{selected.twa.toFixed(0)}°</strong>
          <span>avg {selected.avg ? `${selected.avg.speed_kts.toFixed(1)} kn` : "—"}</span>
          <span>max {selected.max ? `${selected.max.speed_kts.toFixed(1)} kn` : "—"}</span>
        </div>
      )}
      {groups.length > 1 && (
        <div className={styles.twsPicker}>
          <span className={styles.twsValue}>{active.tws.toFixed(0)} kn TWS</span>
          <input
            type="range"
            className={styles.twsSlider}
            min={0}
            max={groups.length - 1}
            step={1}
            value={activeIndex}
            onChange={(e) => {
              setTwsIndex(Number(e.target.value));
              setSelected(null);
            }}
            style={
              {
                "--sf-polar-track": TWS_TRACK_GRADIENT,
                "--sf-polar-thumb": thumbColor,
              } as CSSProperties
            }
            aria-label={t("sessions.polarTwsPicker")}
          />
          <div className={styles.twsTicks}>
            <span>{groups[0].tws.toFixed(0)} kn</span>
            <span>{groups[groups.length - 1].tws.toFixed(0)} kn</span>
          </div>
        </div>
      )}
      <div className={styles.legend}>
        {groups.length <= 1 && <span>{active.tws.toFixed(0)} kn TWS</span>}
        <span className="sf-muted">0–{maxSpeed.toFixed(1)} kn</span>
      </div>
      {!!targetPoints?.length && (
        <p className={`sf-muted ${styles.hint}`}>
          <i className={styles.swatch} />
          {t("sessions.polarAvg")}
          {" · "}
          <i className={`${styles.swatch} ${styles.swatchLight}`} />
          {t("sessions.polarMax")}
          {" — "}
          {t("sessions.polarLegendHint")}
        </p>
      )}
    </div>
  );
}
