import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Trophy } from "lucide-react";
import { Pagination, usePagination } from "@/components/ui/Pagination";
import { StatTile, StatTiles } from "./StatTile";
import styles from "./SessionAnalysis.module.css";
import { fmtDuration, fmtDistanceNm, fmtKnots, splitKnots } from "@/utils/format";
import { legSequence } from "@/utils/legSequence";
import type { SessionLeg } from "@/types";

/** The raw leg list, ranked by VMG. The `#` column is the *chronological*
 * sequence number (`legSequence`), shared with the map's leg markers, so it
 * deliberately doesn't follow the ranking order.
 *
 * `styles.rows` restyles the same markup as label/value rows below 700px —
 * seven columns cannot fit a phone, and `sf-tablewrap`'s horizontal scroll
 * inside a vertically scrolling page is the worst of both. */
export function LegsTable({ legs }: { legs: SessionLeg[] }) {
  const { t } = useTranslation();
  const seq = legSequence(legs);
  const ranked = useMemo(() => legs.slice().sort((x, y) => y.avg_vmg_kts - x.avg_vmg_kts), [legs]);
  const { page, setPage, pageCount, pageItems } = usePagination(ranked);

  return (
    <>
      <div className={`sf-tablewrap ${styles.rows}`}>
        <table className="sf-table">
          <thead>
            <tr>
              <th>#</th>
              <th>{t("sessions.type")}</th>
              <th>VMG</th>
              <th>{t("sessions.avgSpeed")}</th>
              <th>{t("sessions.maxSpeed")}</th>
              <th>{t("sessions.distance")}</th>
              <th>{t("sessions.duration")}</th>
            </tr>
          </thead>
          <tbody>
            {pageItems.map((l) => (
              <tr key={l.id}>
                <td data-head>#{seq.get(l.id)}</td>
                <td data-head>{t(`sessions.${l.leg_type}`)}</td>
                <td>
                  <span className={styles.cellLabel}>VMG</span>{fmtKnots(l.avg_vmg_kts)}</td>
                <td>
                  <span className={styles.cellLabel}>{t("sessions.avgSpeed")}</span>{fmtKnots(l.avg_speed_kts)}</td>
                <td>
                  <span className={styles.cellLabel}>{t("sessions.maxSpeed")}</span>{fmtKnots(l.max_speed_kts)}</td>
                <td>
                  <span className={styles.cellLabel}>{t("sessions.distance")}</span>{fmtDistanceNm(l.distance_nm)}</td>
                <td>
                  <span className={styles.cellLabel}>{t("sessions.duration")}</span>{fmtDuration(l.duration_sec)}</td>
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
 * closes the element instead of sitting as a peer tile next to its own inputs. */
function TackCompare({ rows }: { rows: CompareRow[] }) {
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
        <span className={styles.compareSide}>
          {t("sessions.tackSide.starboard")}
          <span className={styles.swatch} style={{ background: STARBOARD_COLOR }} />
        </span>
      </div>
      {rows.map((row) => {
        const max = Math.max(row.port ?? 0, row.starboard ?? 0);
        const width = (v: number | null) => (v == null || max <= 0 ? 0 : (v / max) * 100);
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
      {best && (
        <p className={styles.compareVerdict}>
          <Trophy size={14} />
          <span>
            {t("sessions.bestTack")}: <strong>{t(`sessions.tackSide.${best}`)}</strong>
          </span>
          {delta != null && delta > 0 && (
            <span className="sf-muted">+{fmtKnots(delta)} VMG</span>
          )}
        </p>
      )}
    </div>
  );
}

/** Per-point-of-sail synthesis, the part a casual reader is meant to stop at:
 * the raw leg list below it is opt-in. Reaches are skipped — a port/starboard
 * comparison is only meaningful upwind and downwind. */
export function TackBreakdown({ legs }: { legs: SessionLeg[] }) {
  const { t } = useTranslation();
  const seq = legSequence(legs);
  // Fixed order rather than first-seen order, so the two groups don't swap
  // places between sessions depending on which leg was sailed first.
  const groups = (["upwind", "downwind"] as const)
    .map((legType) => ({ legType, group: legs.filter((l) => l.leg_type === legType) }))
    .filter(({ group }) => group.length > 0);
  if (!groups.length) return null;

  return (
    <>
      {groups.map(({ legType, group }) => {
        const bestVmgLeg = group.reduce((a, b) => (b.avg_vmg_kts > a.avg_vmg_kts ? b : a));
        const fastest = group.reduce((a, b) => (b.max_speed_kts > a.max_speed_kts ? b : a));
        const longest = group.reduce((a, b) => (b.distance_nm > a.distance_nm ? b : a));
        const avgDistance = group.reduce((sum, l) => sum + l.distance_nm, 0) / group.length;
        const avgDuration = group.reduce((sum, l) => sum + l.duration_sec, 0) / group.length;
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
        const legNo = (id: string) => t("sessions.legNumber", { n: seq.get(id) });

        return (
          <div key={legType} className={styles.tackblock}>
            <h5 className={styles.subheading}>
              <span className={styles.legDot} style={{ background: LEG_TYPE_COLOR[legType] }} />
              {t(`sessions.${legType}`)}
              <span className={styles.countPill}>{group.length}</span>
            </h5>
            {/* Four tiles, each with a second line, so the grid always closes on
                a full row instead of leaving a ragged remainder. */}
            <StatTiles>
              <StatTile
                label={t("sessions.bestVmg")}
                value={
                  <>
                    {fmtKnots(bestVmgLeg.avg_vmg_kts)}
                    <span className={styles.tileSub}>{legNo(bestVmgLeg.id)}</span>
                  </>
                }
              />
              <StatTile
                label={t("sessions.maxSpeed")}
                value={
                  <>
                    {fmtKnots(fastest.max_speed_kts)}
                    <span className={styles.tileSub}>{legNo(fastest.id)}</span>
                  </>
                }
              />
              <StatTile
                label={t("sessions.longestLeg")}
                value={
                  <>
                    {fmtDistanceNm(longest.distance_nm)}
                    <span className={styles.tileSub}>{legNo(longest.id)}</span>
                  </>
                }
              />
              <StatTile
                label={t("sessions.avgPerLeg")}
                value={
                  <>
                    {fmtDistanceNm(avgDistance)}
                    <span className={styles.tileSub}>{fmtDuration(avgDuration)}</span>
                  </>
                }
              />
            </StatTiles>
            {hasTacks && <TackCompare rows={compare} />}
          </div>
        );
      })}
    </>
  );
}
