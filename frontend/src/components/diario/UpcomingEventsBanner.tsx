import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { activitiesService, activityKeys } from "@/services/activities";
import { clubsService, clubKeys } from "@/services/clubs";
import { groupsService, groupKeys } from "@/services/groups";
import { fmtDateTime } from "@/utils/format";
import { useOnboarding } from "@/onboarding/OnboardingContext";
import type { Activity } from "@/types";
import styles from "./UpcomingEventsBanner.module.css";

function relativeDayLabel(date: string, t: (key: string) => string): string {
  const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const diffDays = Math.round((startOfDay(new Date(date)) - startOfDay(new Date())) / 86_400_000);
  if (diffDays === 0) return t("activities.today");
  if (diffDays === 1) return t("activities.tomorrow");
  return fmtDateTime(date);
}

/** Eye-catching "your club/group organized this" banner for planned events
 * in the personal diary — surfaces activities announced by any club/group
 * the user actively belongs to (see `GET /activities/upcoming`), regardless
 * of who created them or whether a session has been attached yet. */
export function UpcomingEventsBanner() {
  const { t } = useTranslation();
  const { isDemoTarget } = useOnboarding();

  const upcoming = useQuery({
    queryKey: activityKeys.upcoming(),
    queryFn: () => activitiesService.upcoming(),
  });
  const clubs = useQuery({ queryKey: clubKeys.all, queryFn: () => clubsService.list() });
  const groups = useQuery({
    queryKey: [...groupKeys.all, "mine"] as const,
    queryFn: () => groupsService.list(true),
  });

  const events = upcoming.data ?? [];
  if (events.length === 0) {
    // No real upcoming events: normally the strip is hidden entirely, but
    // while its guided-tour step is on screen show one demo card so the step
    // has something to point at (it vanishes as soon as the tour advances).
    if (isDemoTarget("diario-upcoming-banner")) {
      return (
        <div className={styles.strip} data-tour="diario-upcoming-banner">
          <div className={styles.card}>
            <span className="sf-badge sf-badge--success">{t("activities.tomorrow")}</span>
            <div className={styles.text}>
              <span className={styles.title}>{t("onboarding.demo.event.title")}</span>
              <p className={`sf-muted ${styles.organizer}`}>{t("onboarding.demo.event.organizer")}</p>
            </div>
            <span className={styles.cta}>{t("activities.viewDetails")}</span>
          </div>
        </div>
      );
    }
    return null;
  }

  const organizerName = (a: Activity) =>
    (a.club_id && clubs.data?.find((c) => c.id === a.club_id)?.name) ||
    (a.group_id && groups.data?.find((g) => g.id === a.group_id)?.name) ||
    null;

  return (
    <div className={styles.strip} data-tour="diario-upcoming-banner">
      {events.map((a) => {
        const org = organizerName(a);
        return (
          <Link key={a.id} to={`/diario/activities/${a.id}`} className={styles.card}>
            {a.started_at && (
              <span className="sf-badge sf-badge--success">{relativeDayLabel(a.started_at, t)}</span>
            )}
            <div className={styles.text}>
              <span className={styles.title}>{a.name ?? t(`activities.types.${a.type}`)}</span>
              {org && (
                <p className={`sf-muted ${styles.organizer}`}>
                  {t("activities.organizedBy", { name: org })}
                </p>
              )}
            </div>
            <span className={styles.cta}>{t("activities.viewDetails")}</span>
          </Link>
        );
      })}
    </div>
  );
}
