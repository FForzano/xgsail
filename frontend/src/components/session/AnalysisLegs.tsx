import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { Trophy } from "lucide-react";
import { Pagination, usePagination } from "@/components/ui/Pagination";
import styles from "./SessionAnalysis.module.css";
import { fmtDuration, fmtDistanceNm, fmtKnots, splitKnots } from "@/utils/format";
import { legSequence } from "@/utils/legSequence";
import type { SessionLeg } from "@/types";

export function legLabel(t: TFunction, leg: Pick<SessionLeg, "leg_type" | "in_beat" | "in_run">): string {
  if (leg.leg_type === "reach" && leg.in_beat) return t("sessions.reachInBeat");
  if (leg.leg_type === "reach" && leg.in_run) return t("sessions.reachInRun");
  return t(`sessions.${leg.leg_type}`);
}

/** The raw leg list, ranked by VMG. The `#` column is the *chronological*
 * sequence number (`legSequence`), shared with the map's leg markers, so it
 * deliberately doesn't follow the ranking order.
 *
 * Seven columns cannot fit a phone: there the table drops to the four that
 * say where the leg went wrong (#, kind, VMG, time) and stays a ruled table,
 * rather than turning every row into a block of label/value tiles. */
export function LegsTable({ legs }: { legs: SessionLeg[] }) {
  const { t } = useTranslation();
  const seq = legSequence(legs);
  const ranked = useMemo(() => legs.slice().sort((x, y) => y.avg_vmg_kts - x.avg_vmg_kts), [legs]);
  const { page, setPage, pageCount, pageItems } = usePagination(ranked);

  return (
    <>
      <div className="sf-tablewrap">
        <table className={`sf-table ${styles.sheet}`}>
          <thead>
            <tr>
              <th>#</th>
              <th>{t("sessions.type")}</th>
              <th className={styles.num}>VMG</th>
              <th className={`${styles.num} ${styles.optional}`}>{t("sessions.avgSpeed")}</th>
              <th className={`${styles.num} ${styles.optional}`}>{t("sessions.maxSpeed")}</th>
              <th className={`${styles.num} ${styles.optional}`}>{t("sessions.distance")}</th>
              <th className={styles.num}>{t("sessions.duration")}</th>
            </tr>
          </thead>
          <tbody>
            {pageItems.map((l) => (
              <tr key={l.id}>
                <td>{seq.get(l.id)}</td>
                <td>{legLabel(t, l)}</td>
                <td className={styles.num}>{fmtKnots(l.avg_vmg_kts)}</td>
                <td className={`${styles.num} ${styles.optional}`}>{fmtKnots(l.avg_speed_kts)}</td>
                <td className={`${styles.num} ${styles.optional}`}>{fmtKnots(l.max_speed_kts)}</td>
                <td className={`${styles.num} ${styles.optional}`}>{fmtDistanceNm(l.distance_nm)}</td>
                <td className={styles.num}>{fmtDuration(l.duration_sec)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Pagination page={page} pageCount={pageCount} onPageChange={setPage} label={t("sessions.legs")} />
    </>
  );
}

// --- tack breakdown (per point-of-sail: headline legs, then port vs starboard) -----------

/** Same tokens as the map's leg markers, so "Bolina" here and an upwind leg on
 * the track above carry the same colour. */
const LEG_TYPE_COLOR: Record<string, string> = {
  upwind: "var(--sf-leg-upwind)",
  downwind: "var(--sf-leg-downwind)",
};

/* Port red / starboard green: the boat's own navigation lights, which is the
   one colour pairing a sailor reads without a legend. Both are existing
   tokens, so the comparison follows the theme like everything else. */
// Below this the two tacks are the same within the data's resolution — a
// trophy on a 0.0 kn difference names a winner that doesn't exist.
const MIN_TACK_DELTA_KTS = 0.1;
const PORT_COLOR = "var(--sf-danger)";
const STARBOARD_COLOR = "var(--sf-success)";

function tackAvg(legs: SessionLeg[], tack: "port" | "starboard",
                 key: "avg_vmg_kts" | "avg_speed_kts"): number | null {
  const vals = legs.filter((l) => l.tack === tack).map((l) => l[key]);
  return vals.length ? vals.reduce((sum, v) => sum + v, 0) / vals.length : null;
}

type CompareRow = { key: string; label: string; port: number | null; starboard: number | null };

/** Port vs starboard as one diverging bar per metric, both halves growing from
 * a shared centre line so the asymmetry is the shape rather than a subtraction
 * the reader has to do. `bestTack` is the conclusion of this comparison, so it
 * closes the element instead of sitting as a peer tile next to its own inputs.
 *
 * Every bar shares one full scale, the session's max speed, so the upwind and
 * downwind blocks are comparable with each other too, not just side to side. */
function TackCompare({ rows, scaleMax }: { rows: CompareRow[]; scaleMax: number }) {
  const { t } = useTranslation();
  const unit = splitKnots(0).unit;
  const vmg = rows[0];
  const best =
    vmg.port == null || vmg.starboard == null
      ? null
      : vmg.starboard >= vmg.port
        ? "starboard"
        : "port";
  const delta = vmg.port != null && vmg.starboard != null ? Math.abs(vmg.starboard - vmg.port) : null;

  return (
    <div className={styles.compare}>
      <div className={styles.compareHead}>
        <span className={styles.compareSide}>
          <span className={styles.swatch} style={{ background: PORT_COLOR }} />
          {t("sessions.tackSide.port")}
        </span>
        <span>{t("sessions.barScale", { value: fmtKnots(scaleMax) })}</span>
        <span className={styles.compareSide}>
          {t("sessions.tackSide.starboard")}
          <span className={styles.swatch} style={{ background: STARBOARD_COLOR }} />
        </span>
      </div>
      {rows.map((row) => {
        const width = (v: number | null) => (v == null || scaleMax <= 0 ? 0 : Math.min(v / scaleMax, 1) * 100);
        const win =
          row.port == null || row.starboard == null || row.port === row.starboard
            ? null
            : row.port > row.starboard
              ? "port"
              : "starboard";
        const value = (v: number | null) => (v == null ? "—" : splitKnots(v).value);
        return (
          <div key={row.key} className={styles.compareRow}>
            <span className={styles.compareMetric}>
              {row.label} ({unit})
            </span>
            <span className={`${styles.compareValue} ${win === "port" ? styles.compareValueWin : ""}`}>
              {value(row.port)}
            </span>
            <span className={`${styles.compareTrack} ${styles.compareTrackPort}`}>
              <span className={styles.compareFill} style={{ width: `${width(row.port)}%`, background: PORT_COLOR }} />
            </span>
            <span className={styles.compareTrack}>
              <span
                className={styles.compareFill}
                style={{ width: `${width(row.starboard)}%`, background: STARBOARD_COLOR }}
              />
            </span>
            <span className={`${styles.compareValue} ${win === "starboard" ? styles.compareValueWin : ""}`}>
              {value(row.starboard)}
            </span>
          </div>
        );
      })}
      {best && delta != null && delta >= MIN_TACK_DELTA_KTS && (
        <p className={styles.compareVerdict}>
          <Trophy size={14} />
          <span>
            {t("sessions.bestTack")}: <strong>{t(`sessions.tackSide.${best}`)}</strong>
          </span>
          <span className="sf-muted">+{fmtKnots(delta)} VMG</span>
        </p>
      )}
    </div>
  );
}

/** Per-point-of-sail synthesis, the part a casual reader is meant to stop at:
 * the raw leg list below it is opt-in. Reaches are skipped, except those sailed
 * in a beat (counted as upwind) or in a run (counted as downwind) — a
 * port/starboard comparison is only meaningful upwind and downwind. */
const breakdownType = (l: SessionLeg) => {
  if (l.leg_type === "reach" && l.in_beat) return "upwind";
  if (l.leg_type === "reach" && l.in_run) return "downwind";
  return l.leg_type;
};

export function TackBreakdown({ legs, maxSpeedKts }: { legs: SessionLeg[]; maxSpeedKts?: number | null }) {
  const { t } = useTranslation();
  // Session stats may not be computed yet; the fastest leg is the next best ceiling.
  const scaleMax = Math.max(maxSpeedKts ?? 0, ...legs.map((l) => l.max_speed_kts));
  // Fixed order rather than first-seen order, so the two groups don't swap
  // places between sessions depending on which leg was sailed first.
  const groups = (["upwind", "downwind"] as const)
    .map((legType) => ({ legType, group: legs.filter((l) => breakdownType(l) === legType) }))
    .filter(({ group }) => group.length > 0);
  if (!groups.length) return null;

  return (
    <>
      {groups.map(({ legType, group }) => {
        const compare: CompareRow[] = [
          {
            key: "vmg",
            label: t("sessions.avgVmg"),
            port: tackAvg(group, "port", "avg_vmg_kts"),
            starboard: tackAvg(group, "starboard", "avg_vmg_kts"),
          },
          {
            key: "speed",
            label: t("sessions.avgSpeed"),
            port: tackAvg(group, "port", "avg_speed_kts"),
            starboard: tackAvg(group, "starboard", "avg_speed_kts"),
          },
        ];
        const hasTacks = compare.some((r) => r.port != null || r.starboard != null);

        return (
          <div key={legType} className={styles.tackblock}>
            <h5 className={styles.subheading}>
              <span className={styles.legDot} style={{ background: LEG_TYPE_COLOR[legType] }} />
              {t(`sessions.${legType}`)}
              <span className={styles.countPill}>{group.length}</span>
            </h5>
            {hasTacks && <TackCompare rows={compare} scaleMax={scaleMax} />}
          </div>
        );
      })}
    </>
  );
}
