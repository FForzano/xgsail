import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { fmtKnots, fmtSeconds } from "@/utils/format";
import { lossHabits, sessionLosses, type LossHabit } from "@/utils/sessionLosses";
import type { SessionLeg, SessionManeuver } from "@/types";
import styles from "./NextOuting.module.css";

const mean = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length;

/** The page's last word: the one habit worth practising next time, said in a
 * sentence with the session's own numbers behind it — what a sailor carries
 * back to the water, rather than closing the analysis on a chart. */
export function NextOuting({ legs, maneuvers }: { legs: SessionLeg[]; maneuvers: SessionManeuver[] }) {
  const { t } = useTranslation();
  const top = useMemo(() => lossHabits(sessionLosses(legs, maneuvers))[0], [legs, maneuvers]);

  return (
    <section className={styles.next} aria-labelledby="next-outing-title">
      <h2 id="next-outing-title" className={styles.title}>
        {t("sessions.nextOuting.title")}
      </h2>
      {top ? (
        <>
          <p className={styles.focus} data-kind={top.kind}>
            <span className={styles.code}>{t(`sessions.losses.codes.${top.kind}`)}</span>
            {t(`sessions.nextOuting.advice.${adviceKey(top)}`, { kind: t(`sessions.losses.habitNames.${top.kind}`) })}
          </p>
          <p className={styles.why}>{why(t, top)}</p>
        </>
      ) : (
        <p className={styles.focus}>{t("sessions.nextOuting.clean")}</p>
      )}
    </section>
  );
}

function adviceKey(h: LossHabit): "maneuver" | "leg" {
  return h.kind === "upwind" || h.kind === "downwind" ? "leg" : "maneuver";
}

/** The numbers behind the advice, averaged over the habit's own incidents. */
function why(t: ReturnType<typeof useTranslation>["t"], h: LossHabit): string {
  const maneuvers = h.losses.flatMap((l) => (l.kind === "maneuver" ? [l.maneuver] : []));
  if (maneuvers.length) {
    return t("sessions.nextOuting.whyManeuver", {
      count: maneuvers.length,
      before: fmtKnots(mean(maneuvers.map((m) => m.speed_before_kts))),
      min: fmtKnots(mean(maneuvers.map((m) => m.speed_min_kts))),
      recovery: fmtSeconds(mean(maneuvers.map((m) => m.recovery_time_sec))),
    });
  }
  const legs = h.losses.flatMap((l) => (l.kind === "leg" ? [l] : []));
  return t("sessions.nextOuting.whyLeg", {
    count: legs.length,
    best: fmtKnots(legs[0].bestVmgKts),
    avg: fmtKnots(mean(legs.map((l) => l.leg.avg_vmg_kts))),
  });
}
