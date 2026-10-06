import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { Pagination, usePagination } from "@/components/ui/Pagination";
import styles from "./SessionAnalysis.module.css";
import { fmtKnots, fmtSeconds } from "@/utils/format";
import type { SessionManeuver, UUID, ViolinMetric } from "@/types";

const MANEUVER_TYPES = ["tack", "gybe", "course_change"] as const;

/** Tacks and gybes reuse the map-pin tokens for the same two things, so a bar
 * and its markers on the track above are the same colour. Both are design
 * tokens rather than literals, so they follow the theme instead of pinning a
 * hex that only works against today's background. `summaryKey` is the plural
 * the analyzer's `maneuver_summary` uses for the same type. */
const MANEUVER_SERIES = [
  { key: "tack", summaryKey: "tacks", i18nKey: "sessions.tacks", color: "var(--sf-tack)" },
  { key: "gybe", summaryKey: "gybes", i18nKey: "sessions.gybes", color: "var(--sf-gybe)" },
  {
    key: "course_change",
    summaryKey: "course_changes",
    i18nKey: "sessions.course_changes",
    color: "var(--sf-course-change)",
  },
] as const;

type Violin = Record<string, Record<string, ViolinMetric>>;

/** One ruled row per maneuver kind: how many, and what each cost on average —
 * speed lost, seconds to recover, seconds in the turn. Read as the results
 * sheet reads a class: kind down the left, figures right-aligned. This
 * replaced a chip row plus two bar charts that drew these same nine numbers;
 * a table says them at a glance and keeps them comparable without an axis.
 *
 * Counts come from the analyzer's summary, falling back to the rows on screen
 * when a session predates it; averages from its per-kind distributions. */
export function ManeuverSummary({
  summary,
  violin,
  maneuvers,
}: {
  summary: Record<string, unknown> | null;
  violin: Violin | null;
  maneuvers: SessionManeuver[];
}) {
  const { t } = useTranslation();
  const rows = MANEUVER_SERIES.map((s) => {
    const group = (summary?.[s.summaryKey] ?? null) as Record<string, number> | null;
    const count =
      typeof group?.count === "number" ? group.count : maneuvers.filter((m) => m.maneuver_type === s.key).length;
    const mean = (metric: string) => violin?.[s.key]?.[metric]?.mean ?? null;
    return { s, count, loss: mean("speed_loss_kts"), recovery: mean("recovery_time_sec"), duration: mean("duration_sec") };
  }).filter((r) => r.count > 0);
  if (!rows.length) return null;

  return (
    <div className="sf-tablewrap">
      <table className={`sf-table ${styles.sheet}`}>
        <thead>
          <tr>
            <th>{t("sessions.type")}</th>
            <th className={styles.num}>{t("sessions.losses.count")}</th>
            <th className={styles.num}>{t("sessions.speedLoss")}</th>
            <th className={styles.num}>{t("sessions.recovery")}</th>
            <th className={`${styles.num} ${styles.optional}`}>{t("sessions.duration")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ s, count, loss, recovery, duration }) => (
            <tr key={s.key}>
              <td>
                <span className={styles.kindCell}>
                  <span className={styles.swatch} style={{ background: s.color }} />
                  {t(s.i18nKey)}
                </span>
              </td>
              <td className={styles.num}>
                {count}
              </td>
              <td className={styles.num}>
                {fmtKnots(loss)}
              </td>
              <td className={styles.num}>
                {fmtSeconds(recovery)}
              </td>
              <td className={`${styles.num} ${styles.optional}`}>
                {fmtSeconds(duration)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// --- maneuver list ----------------------------------------------------------------------

/** `styles.rows` restyles the same markup as label/value rows below 700px —
 * see `LegsTable`. In edit mode the type cell (which holds a `Select`) and the
 * action cell each take a full row of their own. */
export function ManeuversTable({
  maneuvers,
  editMode = false,
  onCorrect,
  onReject,
  onDelete,
}: {
  maneuvers: SessionManeuver[];
  editMode?: boolean;
  onCorrect?: (maneuverId: UUID, type: SessionManeuver["maneuver_type"]) => void;
  onReject?: (maneuverId: UUID, rejected: boolean) => void;
  onDelete?: (maneuverId: UUID) => void;
}) {
  const { t } = useTranslation();
  const { page, setPage, pageCount, pageItems } = usePagination(maneuvers);

  return (
    <>
      <div className={`sf-tablewrap ${styles.rows}`}>
        <table className="sf-table">
          <thead>
            <tr>
              <th>{t("sessions.type")}</th>
              <th>{t("sessions.speedLoss")}</th>
              <th>{t("sessions.recovery")}</th>
              <th>{t("sessions.duration")}</th>
              <th>Δ°</th>
              {editMode && <th />}
            </tr>
          </thead>
          <tbody>
            {pageItems.map((m) => (
              <tr key={m.id} className={m.rejected ? "sf-row--muted" : undefined}>
                <td data-head data-span>
                  {editMode ? (
                    <span className="sf-maneuver-type-select">
                      <Select
                        label={t("sessions.correctManeuver")}
                        id={`maneuver-type-${m.id}`}
                        value={m.maneuver_type}
                        disabled={m.pending}
                        onChange={(e) => onCorrect?.(m.id, e.target.value as SessionManeuver["maneuver_type"])}
                      >
                        {MANEUVER_TYPES.map((type) => (
                          <option key={type} value={type}>
                            {t(`sessions.${type}`)}
                          </option>
                        ))}
                      </Select>
                    </span>
                  ) : (
                    t(`sessions.${m.maneuver_type}`)
                  )}
                  {m.pending && <span className="sf-badge sf-badge--pending"> {t("sessions.computing")}</span>}
                  {m.rejected && <span className="sf-badge"> {t("sessions.rejected")}</span>}
                </td>
                <td>
                  <span className={styles.cellLabel}>{t("sessions.speedLoss")}</span>{fmtKnots(m.speed_loss_kts)}</td>
                <td>
                  <span className={styles.cellLabel}>{t("sessions.recovery")}</span>{fmtSeconds(m.recovery_time_sec)}</td>
                <td>
                  <span className={styles.cellLabel}>{t("sessions.duration")}</span>{fmtSeconds(m.duration_sec)}</td>
                <td>
                  <span className={styles.cellLabel}>Δ°</span>{Math.abs(m.heading_change_deg).toFixed(0)}°</td>
                {editMode && (
                  <td data-span>
                    {m.source === "manual" ? (
                      <Button variant="danger" className="sf-btn--sm" onClick={() => onDelete?.(m.id)}>
                        {t("common.delete")}
                      </Button>
                    ) : (
                      <Button
                        variant="ghost"
                        className="sf-btn--sm"
                        onClick={() => onReject?.(m.id, !m.rejected)}
                      >
                        {m.rejected ? t("sessions.restoreManeuver") : t("sessions.rejectManeuver")}
                      </Button>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Pagination page={page} pageCount={pageCount} onPageChange={setPage} label={t("sessions.maneuversList")} />
    </>
  );
}
