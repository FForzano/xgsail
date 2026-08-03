import { useMemo, useState } from "react";
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

  // First touch/click of an interaction: in trim mode, pick whichever handle
  // is nearer and jump it there immediately; otherwise the normal seek. Also
  // seeks playback to the handle's position either way, so the map's boat
  // marker follows the dragged handle — showing where the boat actually was
  // at that instant is the whole point of picking a trim bound by dragging.
  const startInteraction = (label: unknown) => {
    if (typeof label !== "number") return;
    if (trimMode && trimStartMs != null && trimEndMs != null) {
      const handle = Math.abs(label - trimStartMs) <= Math.abs(label - trimEndMs) ? "start" : "end";
      setDraggingHandle(handle);
      if (handle === "start") onTrimStartChange?.(Math.min(label, trimEndMs));
      else onTrimEndChange?.(Math.max(label, trimStartMs));
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
    <div className="sf-chartpanel">
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
      <div className="sf-bleed">
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
          <ReferenceLine yAxisId="sog" x={cursor} stroke="#fff" strokeWidth={1} />
          {trimMode && trimStartMs != null && trimEndMs != null && (
            <ReferenceArea yAxisId="sog" x1={trimStartMs} x2={trimEndMs}
                          fill="#4fd0e0" fillOpacity={0.12} />
          )}
          {trimMode && trimStartMs != null && (
            <ReferenceLine yAxisId="sog" x={trimStartMs} stroke="#4fd0e0" strokeWidth={2} />
          )}
          {trimMode && trimEndMs != null && (
            <ReferenceLine yAxisId="sog" x={trimEndMs} stroke="#4fd0e0" strokeWidth={2} />
          )}
        </AreaChart>
      </ResponsiveContainer>
      </div>
    </div>
  );
}
