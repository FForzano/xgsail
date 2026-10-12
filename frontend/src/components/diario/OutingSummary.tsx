import { useTranslation } from "react-i18next";
import { Avatar } from "@/components/ui/Avatar";
import { fmtDistance, fmtDuration, fmtKnots } from "@/utils/format";
import type { ActivityOutingSummary } from "@/types";
import styles from "./OutingSummary.module.css";

const CREW_FACES = 3;

/** How the outing went, on the diary card itself: distance, time on the water
 * and top speed as one instrument row, then who was aboard. These are the
 * numbers a sailor would otherwise open the session to learn, so the card
 * answers "how was Sunday" without the tap. `featured` is the latest outing at
 * the top of the feed, read at a larger size. */
export function OutingSummary({
  summary,
  featured = false,
}: {
  summary: ActivityOutingSummary;
  featured?: boolean;
}) {
  const { t } = useTranslation();
  const readouts = [
    { key: "distance", label: t("sessions.distance"), value: summary.distance_m, fmt: fmtDistance },
    { key: "duration", label: t("sessions.duration"), value: summary.duration_s, fmt: fmtDuration },
    { key: "maxSpeed", label: t("sessions.maxSpeed"), value: summary.max_speed_kts, fmt: fmtKnots },
  ].filter((r) => r.value != null);

  const crew = summary.crew;
  const names = crew.slice(0, CREW_FACES).map((c) => c.first_name || c.last_name).filter(Boolean) as string[];
  const extra = crew.length - names.length;
  const parts = extra > 0 ? [...names, t("diario.othersCount", { count: extra })] : names;
  // Not Intl.ListFormat: the native shells still support iOS 14, which lacks it.
  const list =
    parts.length > 1 ? `${parts.slice(0, -1).join(", ")} ${t("diario.and")} ${parts[parts.length - 1]}` : parts[0];
  const crewText = list ? t("diario.sailedWith", { names: list }) : null;

  if (!readouts.length && !crewText) return null;

  return (
    <div className={styles.summary} data-featured={featured || undefined}>
      {readouts.length > 0 && (
        <dl className={styles.readouts}>
          {readouts.map((r) => (
            <div key={r.key} className={styles.readout}>
              <dt className={styles.label}>{r.label}</dt>
              <dd className={styles.value}>{r.fmt(r.value)}</dd>
            </div>
          ))}
        </dl>
      )}
      {crewText && (
        <div className={styles.crew}>
          <span className={styles.faces} aria-hidden>
            {crew.slice(0, CREW_FACES).map((c) => (
              <Avatar
                key={c.id}
                profileImage={c.profile_image}
                firstName={c.first_name}
                lastName={c.last_name}
                size="sm"
                className={styles.face}
              />
            ))}
          </span>
          <span className={styles.crewText}>{crewText}</span>
        </div>
      )}
    </div>
  );
}
