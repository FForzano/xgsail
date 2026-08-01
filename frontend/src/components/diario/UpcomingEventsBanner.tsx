import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { activitiesService, activityKeys } from "@/services/activities";
import { regattasService, raceKeys } from "@/services/races";
import { clubsService, clubKeys } from "@/services/clubs";
import { groupsService, groupKeys } from "@/services/groups";
import { fmtDateTime } from "@/utils/format";
import { activityDisplayName } from "@/utils/activityName";
import { useOnboarding } from "@/onboarding/OnboardingContext";
import type { EventItem } from "@/components/diario/EventRow";
import styles from "./UpcomingEventsBanner.module.css";

const LIMIT = 5;

function relativeDayLabel(date: string, t: (key: string) => string): string {
  const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const diffDays = Math.round((startOfDay(new Date(date)) - startOfDay(new Date())) / 86_400_000);
  if (diffDays === 0) return t("activities.today");
  if (diffDays === 1) return t("activities.tomorrow");
  return fmtDateTime(date);
}

function eventHref(item: EventItem): string {
  return item.kind === "activity" ? `/diario/activities/${item.id}` : `/diario/regate/regatta/${item.id}`;
}

function eventClubId(item: EventItem): string | null {
  return item.kind === "activity" ? (item.activity.club_id ?? null) : item.regatta.club_id;
}

/** Eye-catching "your club/group organized this" banner for planned events in
 * the personal diary — merges `GET /activities/upcoming` and
 * `GET /regattas/upcoming` client-side (same merge `useDiaryFeed` does for
 * the full feeds), sorted soonest-first and capped at `LIMIT`.
 *
 * Regattas, not their per-race tracking activities, are what surface here: a
 * scheduled race auto-creates a `type=="race"` activity for its own GPS data
 * (`routers/races.py::_create_race_activity`), which `/activities/upcoming`
 * excludes for the same reason `useDiaryFeed`/`ClubEvents` do — it would just
 * duplicate the regatta as an unrelated card pointing at raw track
 * bookkeeping instead of the event itself. */
export function UpcomingEventsBanner() {
  const { t } = useTranslation();
  const { isDemoTarget } = useOnboarding();

  const upcomingActivities = useQuery({
    queryKey: activityKeys.upcoming(),
    queryFn: () => activitiesService.upcoming(LIMIT),
  });
  const upcomingRegattas = useQuery({
    queryKey: raceKeys.upcoming,
    queryFn: () => regattasService.upcoming(LIMIT),
  });
  const clubs = useQuery({ queryKey: clubKeys.all, queryFn: () => clubsService.list() });
  const groups = useQuery({
    queryKey: [...groupKeys.all, "mine"] as const,
    queryFn: () => groupsService.list(true),
  });
  const clubName = (id: string) => clubs.data?.find((c) => c.id === id)?.name;
  const groupName = (id: string) => groups.data?.find((g) => g.id === id)?.name;

  const activityItems: EventItem[] = (upcomingActivities.data ?? []).map((a) => ({
    kind: "activity",
    id: a.id,
    title: activityDisplayName(a, t),
    date: a.started_at,
    endDate: null,
    activity: a,
  }));
  const regattaItems: EventItem[] = (upcomingRegattas.data ?? []).map((r) => ({
    kind: "regatta",
    id: r.id,
    title: r.name,
    date: r.start_date,
    endDate: r.end_date,
    regatta: r,
  }));
  const events = [...activityItems, ...regattaItems]
    .sort((a, b) => new Date(a.date ?? 0).getTime() - new Date(b.date ?? 0).getTime())
    .slice(0, LIMIT);

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

  const organizerName = (item: EventItem) => {
    const clubId = eventClubId(item);
    if (clubId) return clubName(clubId) ?? null;
    if (item.kind === "activity" && item.activity.group_id) return groupName(item.activity.group_id) ?? null;
    return null;
  };

  return (
    <div className={styles.strip} data-tour="diario-upcoming-banner">
      {events.map((item) => {
        const org = organizerName(item);
        return (
          <Link key={`${item.kind}-${item.id}`} to={eventHref(item)} className={styles.card}>
            {item.date && <span className="sf-badge sf-badge--success">{relativeDayLabel(item.date, t)}</span>}
            <div className={styles.text}>
              <span className={styles.title}>{item.title}</span>
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
