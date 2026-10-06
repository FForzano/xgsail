import { useMemo, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { timeController, useTimeState } from "@/stores/timeController";
import { fmtKnots, fmtSeconds, fmtTime } from "@/utils/format";
import { legSequence } from "@/utils/legSequence";
import { lossHabits, lossKind, sessionLosses, type SessionLoss } from "@/utils/sessionLosses";
import { legLabel } from "./AnalysisLegs";
import type { LossHabit } from "@/utils/sessionLosses";
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

  const habits = useMemo(() => lossHabits(losses), [losses]);
  const worst = losses[0]?.lostM ?? 0;
  const total = losses.reduce((sum, l) => sum + l.lostM, 0);
  const rows = expanded ? losses : losses.slice(0, COLLAPSED_ROWS);

  const jump = (loss: SessionLoss) => {
    timeController.pause();
    timeController.seek(loss.atSec * 1000);
    const map = document.querySelector<HTMLElement>("[data-tour='activity-map']");
    const r = map?.getBoundingClientRect();
    if (map && r && (r.top < 0 || r.top > window.innerHeight * 0.5)) {
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

      {habits.length > 0 && <HabitStrip habits={habits} />}

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
                  // The whole row is the mouse target; the event name is the
                  // keyboard and screen-reader one, a real button rather than a
                  // focusable <tr>, which has no button semantics to announce.
                  <tr
                    key={loss.id}
                    className={current ? styles.current : undefined}
                    aria-current={current || undefined}
                    onClick={() => jump(loss)}
                  >
                    <td className={styles.rank}>{i + 1}</td>
                    <td className={styles.event}>
                      <span className={styles.eventLine}>
                        <span className={styles.code} data-kind={lossKind(loss)}>
                          {t(`sessions.losses.codes.${lossKind(loss)}`)}
                        </span>
                        <button
                          type="button"
                          className={styles.what}
                          title={t("sessions.losses.jump", { time: fmtTime(loss.atSec * 1000) })}
                          onClick={(e) => {
                            e.stopPropagation();
                            jump(loss);
                          }}
                        >
                          {eventLabel(t, loss, seq)}
                        </button>
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

/** Where the metres went, by habit: one bar split by kind in the same colours
 * as the codes and the map pins, and the habit that cost most said in words.
 * The ranking below lists incidents; this line says what to practise. */
function HabitStrip({ habits }: { habits: LossHabit[] }) {
  const { t } = useTranslation();
  const top = habits[0];
  return (
    <div className={styles.habits}>
      <p className={styles.habitLead}>
        {t("sessions.losses.habitLead", {
          kind: t(`sessions.losses.habitIn.${top.kind}`),
          count: top.count,
          metres: Math.round(top.lostM),
          share: Math.round(top.share * 100),
        })}
      </p>
      <div className={styles.habitBar} role="img" aria-label={habits
        .map((h) => `${t(`sessions.losses.habitNames.${h.kind}`)} ${Math.round(h.share * 100)}%`)
        .join(", ")}>
        {habits.map((h) => (
          <span key={h.kind} className={styles.habitSeg} data-kind={h.kind} style={{ flexGrow: h.lostM }} />
        ))}
      </div>
      <ul className={styles.habitKey}>
        {habits.map((h) => (
          <li key={h.kind} className={styles.code} data-kind={h.kind}>
            {t(`sessions.losses.codes.${h.kind}`)} {Math.round(h.share * 100)}%
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Walks the ranking from the replay itself: ‹ 2/11 › on the transport bar
 * seeks to each loss in turn, so on a phone the sailor can go through them on
 * the map instead of scrolling back up to the table for every one. */
export function LossStepper({ legs, maneuvers }: { legs: SessionLeg[]; maneuvers: SessionManeuver[] }) {
  const { t } = useTranslation();
  const losses = useMemo(() => sessionLosses(legs, maneuvers), [legs, maneuvers]);
  const [index, setIndex] = useState<number | null>(null);
  if (!losses.length) return null;

  const go = (next: number) => {
    const i = (next + losses.length) % losses.length;
    setIndex(i);
    timeController.pause();
    timeController.seek(losses[i].atSec * 1000);
  };

  return (
    <span className={styles.stepper} role="group" aria-label={t("sessions.losses.title")}>
      <button
        type="button"
        className="sf-btn sf-btn--ghost sf-btn--sm"
        onClick={() => go((index ?? 0) - 1)}
        aria-label={t("sessions.losses.previous")}
      >
        <ChevronLeft size={16} />
      </button>
      <span className={styles.stepperCount} aria-live="polite">
        {index == null
          ? t("sessions.losses.stepperRest", { count: losses.length })
          : `${index + 1}/${losses.length}`}
      </span>
      <button
        type="button"
        className="sf-btn sf-btn--ghost sf-btn--sm"
        onClick={() => go(index == null ? 0 : index + 1)}
        aria-label={t("sessions.losses.next")}
      >
        <ChevronRight size={16} />
      </button>
    </span>
  );
}
