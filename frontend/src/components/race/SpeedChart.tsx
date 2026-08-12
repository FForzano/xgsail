import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Settings } from "lucide-react";
import {
  Area,
  AreaChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { timeController, useTimeState } from "@/stores/timeController";
import { fmtKnots, fmtTime } from "@/utils/format";
import type { VmgPoint } from "@/types";
import type { Track } from "./raceModel";
import { Popover } from "@/components/ui/Popover";
import styles from "./SpeedChart.module.css";

// Speed-over-ground chart, one line per track, with a cursor line synced to
// the shared time controller. Click/drag anywhere seeks — it doubles as the
// playback scrubber. Optionally overlays the VMG series (toggle via the
// options popover) and shows a tap/hover tooltip with the values at that time.
const H = 160;
// How close (in CSS pixels) a press must land to a trim handle to grab it.
// Converted to ms against the live chart width so it stays the same physical
// distance on a phone and on a wide desktop chart.
const GRAB_PX = 24;
// Trim palette, mirroring global.css tokens: --sf-success (start),
// --sf-gybe (end), --sf-bg (the mask over the discarded parts). Recharts
// takes plain SVG paint attributes, which don't resolve CSS custom
// properties, hence the literals.
const TRIM_START_COLOR = "#3fbf7f";
const TRIM_END_COLOR = "#e0654f";
const TRIM_MASK_COLOR = "#0b1f33";

type TrimLabelProps = { viewBox?: { x?: number; y?: number } };

/** Bracket-shaped grip on a trim handle: drawn on the kept side of the line
 * (start opens right, end opens left) so the two are told apart by shape as
 * well as by colour, and big enough to aim a thumb at. */
function trimGrip(x: number, y: number, color: string, side: "start" | "end") {
  const w = 15;
  const h = 26;
  const left = side === "start" ? x : x - w;
  return (
    <g pointerEvents="none">
      <rect x={left} y={y} width={w} height={h} rx={3} fill={color} />
      <line x1={left + 5} y1={y + 8} x2={left + 5} y2={y + h - 8} stroke={TRIM_MASK_COLOR} strokeWidth={1.5} />
      <line x1={left + 10} y1={y + 8} x2={left + 10} y2={y + h - 8} stroke={TRIM_MASK_COLOR} strokeWidth={1.5} />
    </g>
  );
}

export function SpeedChart({
  tracks,
  vmg,
  trimMode = false,
  trimStartMs = null,
  trimEndMs = null,
  onTrimStartChange,
  onTrimEndChange,
}: {
  tracks: Track[];
  vmg?: VmgPoint[] | null;
  /** When true, dragging moves the nearer of the two trim handles instead of
   * seeking playback — the session detail page's trim mode uses this so the
   * user picks the kept track window by dragging directly on this chart. */
  trimMode?: boolean;
  trimStartMs?: number | null;
  trimEndMs?: number | null;
  onTrimStartChange?: (ms: number) => void;
  onTrimEndChange?: (ms: number) => void;
}) {
  const { t } = useTranslation();
  const { tMin, tMax, cursor } = useTimeState();
  const [dragging, setDragging] = useState(false);
  // Which trim handle a drag/touch is currently moving — persists across the
  // move events of one drag, cleared on release (mouse) or a fresh touch
  // start (touch has no separate "end" cleanup, matching the plain-seek
  // touch handling below, which never resets `dragging` either).
  const [draggingHandle, setDraggingHandle] = useState<"start" | "end" | null>(null);
  const [showVmg, setShowVmg] = useState(true);

  // Merge every track's points (and the VMG series) onto a shared time axis;
  // gaps are connected so tracks with different clocks still render one line.
  const { data, maxSog, maxVmg } = useMemo(() => {
    const byMs = new Map<number, Record<string, number>>();
    let mxSog = 1;
    let mxVmg = 1;
    for (const tr of tracks) {
      for (const p of tr.pts) {
        if (p.sog > mxSog) mxSog = p.sog;
        const row = byMs.get(p.ms) ?? { ms: p.ms };
        row[tr.id] = p.sog;
        byMs.set(p.ms, row);
      }
    }
    for (const v of vmg ?? []) {
      if (v.vmg_kts > mxVmg) mxVmg = v.vmg_kts;
      const ms = v.timestamp * 1000;
      const row = byMs.get(ms) ?? { ms };
      row.vmg = v.vmg_kts;
      byMs.set(ms, row);
    }
    const rows = [...byMs.values()].sort((a, b) => a.ms - b.ms);
    return { data: rows, maxSog: mxSog, maxVmg: mxVmg };
  }, [tracks, vmg]);

  const seekTo = (label: unknown) => {
    if (typeof label === "number") timeController.seek(label);
  };

  // Chart width, so the grab tolerance can be expressed in pixels instead of
  // a hardcoded duration that would be huge on a short track and unusable on
  // a long one.
  const wrapRef = useRef<HTMLDivElement>(null);
  const [wrapWidth, setWrapWidth] = useState(0);
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setWrapWidth(entry.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const grabMs = wrapWidth > 0 ? ((tMax - tMin) * GRAB_PX) / wrapWidth : 0;

  // First touch/click of an interaction: in trim mode, grab a handle only if
  // the press landed within the tolerance of it; otherwise the press just
  // seeks. Seeking is also what a handle drag does, so the map's boat marker
  // follows the dragged bound — showing where the boat actually was at that
  // instant is the whole point of picking a trim bound by dragging.
  const startInteraction = (label: unknown) => {
    if (typeof label !== "number") return;
    if (trimMode && trimStartMs != null && trimEndMs != null) {
      const dStart = Math.abs(label - trimStartMs);
      const dEnd = Math.abs(label - trimEndMs);
      // A press away from both handles moves neither: teleporting a bound on
      // any stray tap was the bug. Moving a bound a long way is done by
      // seeking there and using the trim bar's "start/end here" buttons.
      const grabbed = Math.min(dStart, dEnd) <= grabMs;
      setDraggingHandle(grabbed ? (dStart <= dEnd ? "start" : "end") : null);
      seekTo(label);
      return;
    }
    seekTo(label);
  };

  // Subsequent move events of the same interaction: keep moving whichever
  // handle `startInteraction` picked (and the boat marker with it via seek),
  // clamped so start never passes end.
  const continueInteraction = (label: unknown) => {
    if (typeof label !== "number") return;
    if (draggingHandle === "start") {
      onTrimStartChange?.(Math.min(label, trimEndMs ?? tMax));
      seekTo(label);
      return;
    }
    if (draggingHandle === "end") {
      onTrimEndChange?.(Math.max(label, trimStartMs ?? tMin));
      seekTo(label);
      return;
    }
    seekTo(label);
  };

  return (
    <div className="sf-chartpanel" ref={wrapRef}>
      <div className={styles.head}>
        <span className="sf-muted" style={{ fontSize: "0.8rem" }}>
          {t("race.speedRange")} 0–{fmtKnots(maxSog)}
        </span>
        {!!vmg?.length && (
          <Popover
            trigger={({ toggle }) => (
              <button className="sf-btn sf-btn--ghost sf-btn--sm" aria-label="Chart options" onClick={toggle}>
                <Settings size={16} />
              </button>
            )}
          >
            {() => (
              <label className="sf-check">
                <input type="checkbox" checked={showVmg} onChange={(e) => setShowVmg(e.target.checked)} />
                <span>{t("sessions.vmg")}</span>
              </label>
            )}
          </Popover>
        )}
      </div>
      <ResponsiveContainer width="100%" height={H}>
        <AreaChart
          data={data}
          margin={{ top: 4, right: 4, bottom: 0, left: 0 }}
          onMouseDown={(s) => {
            setDragging(true);
            startInteraction(s?.activeLabel);
          }}
          onMouseMove={(s) => dragging && continueInteraction(s?.activeLabel)}
          onMouseUp={() => {
            setDragging(false);
            setDraggingHandle(null);
          }}
          onMouseLeave={() => {
            setDragging(false);
            setDraggingHandle(null);
          }}
          // Touch needs its own handlers — Recharts' touch support only
          // drives the tooltip, not these mouse callbacks, which otherwise
          // made mobile scrubbing need a first "activating" tap before drag.
          onTouchStart={(s) => startInteraction(s?.activeLabel)}
          onTouchMove={(s) => continueInteraction(s?.activeLabel)}
        >
          <XAxis dataKey="ms" type="number" domain={[tMin, tMax]} hide />
          <YAxis yAxisId="sog" domain={[0, maxSog]} hide />
          {showVmg && <YAxis yAxisId="vmg" orientation="right" domain={[0, maxVmg]} hide />}
          <Tooltip
            labelFormatter={(ms) => (typeof ms === "number" ? fmtTime(ms) : "")}
            formatter={(v, name) => [
              fmtKnots(Number(v)),
              name === "vmg" ? t("sessions.vmg") : t("race.speed"),
            ]}
          />
          {tracks.map((tr) => (
            <Area
              key={tr.id}
              yAxisId="sog"
              type="monotone"
              dataKey={tr.id}
              stroke={tr.color}
              strokeWidth={1.5}
              fill={tr.color}
              fillOpacity={0.15}
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
          ))}
          {showVmg && (
            <Area
              yAxisId="vmg"
              type="monotone"
              dataKey="vmg"
              stroke="#e0b24a"
              strokeWidth={1.5}
              fill="#e0b24a"
              fillOpacity={0.15}
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
          )}
          {/* Mask what the trim throws away rather than tinting what it keeps:
              the kept part stays at full contrast, so "this is what's left"
              reads without a legend. Drawn before the cursor so the white
              playback line stays visible over it. */}
          {trimMode && trimStartMs != null && trimEndMs != null && (
            <>
              <ReferenceArea yAxisId="sog" x1={tMin} x2={trimStartMs}
                            fill={TRIM_MASK_COLOR} fillOpacity={0.72} />
              <ReferenceArea yAxisId="sog" x1={trimEndMs} x2={tMax}
                            fill={TRIM_MASK_COLOR} fillOpacity={0.72} />
            </>
          )}
          <ReferenceLine yAxisId="sog" x={cursor} stroke="#fff" strokeWidth={1} />
          {trimMode && trimStartMs != null && (
            <ReferenceLine
              yAxisId="sog"
              x={trimStartMs}
              stroke={TRIM_START_COLOR}
              strokeWidth={draggingHandle === "start" ? 3 : 2}
              label={({ viewBox }: TrimLabelProps) =>
                trimGrip(viewBox?.x ?? 0, viewBox?.y ?? 0, TRIM_START_COLOR, "start")
              }
            />
          )}
          {trimMode && trimEndMs != null && (
            <ReferenceLine
              yAxisId="sog"
              x={trimEndMs}
              stroke={TRIM_END_COLOR}
              strokeWidth={draggingHandle === "end" ? 3 : 2}
              label={({ viewBox }: TrimLabelProps) =>
                trimGrip(viewBox?.x ?? 0, viewBox?.y ?? 0, TRIM_END_COLOR, "end")
              }
            />
          )}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
