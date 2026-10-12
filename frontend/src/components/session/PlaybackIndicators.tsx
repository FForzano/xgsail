import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useTimeState } from "@/stores/timeController";
import { buildCumulativeDistances, indexAt, pointAt, type Track } from "@/components/race/raceModel";
import { vmgAt } from "@/utils/vmgSeries";
import { fmtDistance, fmtKnots } from "@/utils/format";
import type { VmgPoint } from "@/types";
import styles from "./PlaybackIndicators.module.css";

// Live readout of speed/VMG/TWA/distance-so-far at the current playback
// cursor: one tight ruled row under the speed strip, so it rides with the
// replay even where that is pinned to the top of a phone.
export function PlaybackIndicators({ track, vmg }: { track: Track; vmg?: VmgPoint[] | null }) {
  const { t } = useTranslation();
  const { cursor } = useTimeState();
  const cumDist = useMemo(() => buildCumulativeDistances(track), [track]);

  const speed = pointAt(track, cursor)?.sog ?? null;
  const at = vmgAt(vmg, cursor);
  const idx = indexAt(track, cursor);
  const distanceM = idx >= 0 ? cumDist[idx] : 0;

  const cells: Array<[string, string]> = [
    // SOG, not "speed (kn)": the value already carries its unit.
    ["SOG", fmtKnots(speed)],
    [t("sessions.vmg"), fmtKnots(at?.vmg_kts)],
    ["TWA", at?.twa_deg != null ? `${Math.abs(at.twa_deg).toFixed(0)}°` : "—"],
    // "—" before the cursor has moved: a zero distance reads as a fault.
    [t("sessions.distance"), distanceM > 0 ? fmtDistance(distanceM) : "—"],
  ];
  return (
    <dl className={styles.row}>
      {cells.map(([label, value]) => (
        <div key={label} className={styles.cell}>
          <dt className={styles.label}>{label}</dt>
          <dd className={styles.value}>{value}</dd>
        </div>
      ))}
    </dl>
  );
}
