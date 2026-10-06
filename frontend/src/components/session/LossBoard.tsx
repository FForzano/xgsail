import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { timeController, useTimeState } from "@/stores/timeController";
import { fmtKnots, fmtSeconds, fmtTime } from "@/utils/format";
import { legSequence } from "@/utils/legSequence";
import { sessionLosses, type SessionLoss } from "@/utils/sessionLosses";
import { legLabel } from "./AnalysisLegs";
import type { SessionLeg, SessionManeuver } from "@/types";
import styles from "./LossBoard.module.css";

const COLLAPSED_ROWS = 5;

/** "Where you lost": the session's maneuvers and legs ranked by metres lost,
 * worst first, set as the results sheet the club pins up after a race. A row
 * is the way into the replay — selecting it moves the shared playback cursor
 * to that moment, and the row under the cursor stays marked. */
export function LossBoard({ legs, maneuvers }: { legs: SessionLeg[]; maneuvers: SessionManeuver[] }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const losses = useMemo(() => sessionLosses(legs, maneuvers), [legs, maneuvers]);
  const seq = useMemo(() => legSequence(legs), [legs]);
  const { cursor } = useTimeState();

  const worst = losses[0]?.lostM ?? 0;
  const total = losses.reduce((sum, l) => sum + l.lostM, 0);
  const rows = expanded ? losses : losses.slice(0, COLLAPSED_ROWS);

  const jump = (loss: SessionLoss) => {
    timeController.pause();
    timeController.seek(loss.atSec * 1000);
    const map = document.querySelector<HTMLElement>("[data-tour='activity-map']");
    if (map && map.getBoundingClientRect().top > window.innerHeight * 0.5) {
      map.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  };

  return (
    <section className={styles.board} aria-labelledby="loss-board-title">
      <div className={styles.head}>
        <h2 id="loss-board-title" className={styles.title}>
          {t("sessions.losses.title")}
        </h2>
        {losses.length > 0 && (
          <p className={styles.total}>
            <span className={styles.totalValue}>{Math.round(total)} m</span>{" "}
            {t("sessions.losses.total", { count: losses.length })}
          </p>
        )}
      </div>

      {losses.length === 0 ? (
        <p className={styles.empty}>{t("sessions.losses.empty")}</p>
      ) : (
        <>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col" className={styles.rank}>#</th>
                <th scope="col">{t("sessions.losses.colEvent")}</th>
                <th scope="col" className={styles.time}>{t("sessions.losses.colTime")}</th>
                <th scope="col" className={styles.lost}>{t("sessions.losses.colLost")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((loss, i) => {
                const endSec = loss.kind === "leg" ? loss.leg.end_time : loss.maneuver.end_time;
                const current = cursor >= loss.atSec * 1000 && cursor <= endSec * 1000;
                return (
                  <tr
                    key={loss.id}
                    className={current ? styles.current : undefined}
                    tabIndex={0}
                    title={t("sessions.losses.jump", { time: fmtTime(loss.atSec * 1000) })}
                    aria-current={current || undefined}
                    onClick={() => jump(loss)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        jump(loss);
                      }
                    }}
                  >
                    <td className={styles.rank}>{i + 1}</td>
                    <td className={styles.event}>
                      <span className={styles.eventLine}>
                        <span className={styles.code} data-kind={codeKind(loss)}>
                          {t(`sessions.losses.codes.${codeKind(loss)}`)}
                        </span>
                        <span className={styles.what}>{eventLabel(t, loss, seq)}</span>
                      </span>
                      <span className={styles.detail}>{eventDetail(t, loss)}</span>
                      <span className={styles.bar} aria-hidden="true">
                        <span style={{ width: `${(loss.lostM / worst) * 100}%` }} />
                      </span>
                    </td>
                    <td className={styles.time}>{fmtTime(loss.atSec * 1000)}</td>
                    <td className={styles.lost}>
                      {loss.kind === "maneuver" && loss.estimated && (
                        <abbr className={styles.approx} title={t("sessions.losses.estimated")}>≈</abbr>
                      )}
                      {Math.round(loss.lostM)}
                      <span className={styles.unit}> m</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className={styles.note}>{t("sessions.losses.note")}</p>
          {losses.length > COLLAPSED_ROWS && (
            <button
              type="button"
              className={styles.more}
              aria-expanded={expanded}
              onClick={() => setExpanded((v) => !v)}
            >
              {expanded ? t("sessions.losses.showLess") : t("sessions.losses.showAll", { count: losses.length })}
            </button>
          )}
        </>
      )}
    </section>
  );
}

function codeKind(loss: SessionLoss): string {
  return loss.kind === "leg" ? loss.leg.leg_type : loss.maneuver.maneuver_type;
}

function eventLabel(t: ReturnType<typeof useTranslation>["t"], loss: SessionLoss, seq: Map<string, number>): string {
  if (loss.kind === "leg") {
    return t("sessions.losses.legEvent", { type: legLabel(t, loss.leg), n: seq.get(loss.leg.id) });
  }
  return t(`sessions.${loss.maneuver.maneuver_type}`);
}

function eventDetail(t: ReturnType<typeof useTranslation>["t"], loss: SessionLoss): string {
  if (loss.kind === "leg") {
    return t("sessions.losses.legDetail", {
      vmg: fmtKnots(loss.leg.avg_vmg_kts),
      best: fmtKnots(loss.bestVmgKts),
    });
  }
  const m = loss.maneuver;
  return t("sessions.losses.maneuverDetail", {
    before: fmtKnots(m.speed_before_kts),
    min: fmtKnots(m.speed_min_kts),
    recovery: fmtSeconds(m.recovery_time_sec),
  });
}
