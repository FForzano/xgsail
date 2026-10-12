import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { fmtDuration, fmtKnots, fmtTime, splitKnots } from "@/utils/format";
import { legSequence } from "@/utils/legSequence";
import { sessionHighlights, type SessionHighlight } from "@/utils/sessionHighlights";
import { legLabel } from "./AnalysisLegs";
import { seekReplay } from "./LossBoard";
import type { SessionLeg, SessionManeuver } from "@/types";
import lossStyles from "./LossBoard.module.css";
import styles from "./SessionHighlights.module.css";

/** "Best of the day": the good part of the outing, set on the same sheet as
 * the losses so the page doesn't only grade. Each row seeks the replay to
 * that moment, like a loss row does. Renders nothing when the data has
 * nothing to show. */
export function SessionHighlights({
  legs,
  maneuvers,
  maxSpeedKts,
  points,
}: {
  legs: SessionLeg[];
  maneuvers: SessionManeuver[];
  maxSpeedKts: number | null | undefined;
  points: { ms: number; sog: number }[];
}) {
  const { t } = useTranslation();
  const items = useMemo(
    () => sessionHighlights(legs, maneuvers, maxSpeedKts, points),
    [legs, maneuvers, maxSpeedKts, points],
  );
  const seq = useMemo(() => legSequence(legs), [legs]);
  if (!items.length) return null;

  return (
    <section className={lossStyles.board} aria-labelledby="highlights-title">
      <div className="sf-block__head">
        <h2 id="highlights-title" className="sf-block__title">
          {t("sessions.highlights.title")}
        </h2>
      </div>
      <ul className={styles.list}>
        {items.map((h) => {
          const { code, what, detail, value, unit, approx } = describe(t, h, seq);
          return (
            <li key={h.kind === "leg" ? h.leg.id : h.kind} className={styles.row} onClick={() => seekReplay(h.atMs)}>
              <span className={styles.event}>
                <span className={lossStyles.eventLine}>
                  <span className={lossStyles.code} data-kind={code}>
                    {code === "speed" ? t("sessions.highlights.speedCode") : t(`sessions.losses.codes.${code}`)}
                  </span>
                  <button
                    type="button"
                    className={lossStyles.what}
                    title={t("sessions.losses.jump", { time: fmtTime(h.atMs) })}
                    onClick={(e) => {
                      e.stopPropagation();
                      seekReplay(h.atMs);
                    }}
                  >
                    {what}
                  </button>
                </span>
                {detail && <span className={lossStyles.detail}>{detail}</span>}
              </span>
              <span className={styles.time}>{fmtTime(h.atMs)}</span>
              <span className={styles.figure}>
                {approx && (
                  <abbr className={lossStyles.approx} title={t("sessions.losses.estimated")}>≈</abbr>
                )}
                {value}
                <span className={lossStyles.unit}> {unit}</span>
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function describe(
  t: ReturnType<typeof useTranslation>["t"],
  h: SessionHighlight,
  seq: Map<string, number>,
): { code: string; what: string; detail: string | null; value: string; unit: string; approx: boolean } {
  if (h.kind === "speed") {
    const { value, unit } = splitKnots(h.speedKts);
    return { code: "speed", what: t("sessions.highlights.topSpeed"), detail: null, value, unit, approx: false };
  }
  if (h.kind === "leg") {
    const { value, unit } = splitKnots(h.leg.avg_vmg_kts);
    return {
      code: h.leg.leg_type,
      what: t("sessions.losses.legEvent", { type: legLabel(t, h.leg), n: seq.get(h.leg.id) }),
      detail: t("sessions.highlights.legDetail", { count: h.of, duration: fmtDuration(h.leg.duration_sec) }),
      value,
      unit: `${unit} VMG`,
      approx: false,
    };
  }
  const m = h.maneuver;
  return {
    code: m.maneuver_type,
    what: t(`sessions.${m.maneuver_type}`),
    detail: t("sessions.highlights.maneuverDetail", {
      count: h.of,
      before: fmtKnots(m.speed_before_kts),
      min: fmtKnots(m.speed_min_kts),
    }),
    value: String(Math.round(h.lostM)),
    unit: "m",
    approx: h.estimated,
  };
}
