import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useTimeState } from "@/stores/timeController";
import { buildCumulativeDistances, indexAt, pointAt, type Track } from "@/components/race/raceModel";
import { vmgAt } from "@/utils/vmgSeries";
import { fmtDistance, fmtKnots } from "@/utils/format";
import type { VmgPoint } from "@/types";
import { StatTile, StatTiles } from "./StatTile";

// Live readout of speed/VMG/TWA/distance-so-far at the current playback
// cursor — 4 tiles in a row on desktop, 2×2 on mobile (see statTiles.module.css).
export function PlaybackIndicators({ track, vmg }: { track: Track; vmg?: VmgPoint[] | null }) {
  const { t } = useTranslation();
  const { cursor } = useTimeState();
  const cumDist = useMemo(() => buildCumulativeDistances(track), [track]);

  const speed = pointAt(track, cursor)?.sog ?? null;
  const at = vmgAt(vmg, cursor);
  const idx = indexAt(track, cursor);
  const distanceM = idx >= 0 ? cumDist[idx] : 0;

  return (
    <StatTiles>
      <StatTile label={t("race.speed")} value={fmtKnots(speed)} />
      <StatTile label={t("sessions.vmg")} value={fmtKnots(at?.vmg_kts)} />
      <StatTile
        label="TWA"
        value={at?.twa_deg != null ? `${Math.abs(at.twa_deg).toFixed(0)}°` : "—"}
      />
      <StatTile label={t("sessions.distance")} value={fmtDistance(distanceM)} />
    </StatTiles>
  );
}
