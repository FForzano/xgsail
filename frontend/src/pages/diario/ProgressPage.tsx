import { useState } from "react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  CalendarDays,
  Gauge,
  Percent,
  Route,
  Sailboat,
  Timer,
  Trophy,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import type { ProgressBest } from "@/types";
import { useProgress } from "@/hooks/useProgress";
import { Section } from "@/components/ui/Section";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { MonthBars, monthBarsLabel } from "@/components/diario/ProgressStrip";
import { fmtDate, fmtDistance, fmtDuration, fmtKnots } from "@/utils/format";
import styles from "./ProgressPage.module.css";

/** Volume only, on purpose: outings, days, miles, hours, personal records.
 * A raw performance metric isn't comparable between outings — a fast day is
 * usually just a windy day — so speed/VMG trends stay out until they can be
 * condition-normalised. */

const BEST_ICONS = {
  max_speed_kts: Gauge,
  distance_m: Route,
  duration_s: Timer,
  avg_polar_pct: Percent,
} as const;

function bestValue(best: ProgressBest): string {
  switch (best.metric) {
    case "max_speed_kts":
      return fmtKnots(best.value);
    case "distance_m":
      return fmtDistance(best.value);
    case "duration_s":
      return fmtDuration(best.value);
    case "avg_polar_pct":
      return `${Math.round(best.value)}%`;
  }
}

function Delta({
  current,
  previous,
  previousYear,
  format,
}: {
  current: number;
  previous: number;
  previousYear: number;
  format: (n: number) => string;
}) {
  const { t } = useTranslation();
  const diff = current - previous;
  const suffix = t("progress.vsPrevious", { year: previousYear });
  if (diff === 0) return <span className={styles.deltaFlat}>{suffix}</span>;
  const up = diff > 0;
  const Icon = up ? TrendingUp : TrendingDown;
  return (
    <span className={`${styles.delta} ${up ? styles.deltaUp : styles.deltaDown}`}>
      <Icon size={13} aria-hidden="true" />
      {`${up ? "+" : "−"}${format(Math.abs(diff))} ${suffix}`}
    </span>
  );
}

function HeroStat({
  icon: Icon,
  value,
  label,
  delta,
}: {
  icon: typeof Sailboat;
  value: string;
  label: string;
  delta?: ReactNode;
}) {
  return (
    <div className={styles.heroStat}>
      <Icon size={16} className={styles.heroIcon} aria-hidden="true" />
      <span className={styles.heroValue}>{value}</span>
      <span className={styles.heroLabel}>{label}</span>
      {delta ? <span className={styles.heroDelta}>{delta}</span> : null}
    </div>
  );
}

export function ProgressPage() {
  const { t, i18n } = useTranslation();
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const { data, isLoading, isError } = useProgress(selectedYear ?? undefined);

  if (isLoading) return <Spinner />;
  if (isError || !data) return <EmptyState>{t("common.loadError")}</EmptyState>;

  const { totals, previous, by_month, previous_by_month, personal_bests, by_boat, year } = data;
  const years = [...data.available_years].sort((a, b) => b - a);
  // Below three outings a chart is a single spike and a year-over-year delta
  // compares nothing to nothing — the records still work from outing one.
  const hasVolume = totals.sessions >= 3;
  const showDeltas = hasVolume && previous.sessions > 0;
  const maxBoatSessions = Math.max(1, ...by_boat.map((b) => b.sessions));

  const yearPicker = years.length > 1 && (
    <div className={styles.years} role="group" aria-label={t("progress.year")}>
      {years.map((y) => (
        <button
          key={y}
          type="button"
          className={`${styles.year} ${y === year ? styles.yearOn : ""}`}
          aria-pressed={y === year}
          onClick={() => setSelectedYear(y)}
        >
          {y}
        </button>
      ))}
    </div>
  );

  if (totals.sessions === 0) {
    return (
      <div className={styles.page}>
        {yearPicker}
        <div className={styles.first}>
          <Sailboat size={40} className={styles.firstIcon} aria-hidden="true" />
          <h2 className={styles.firstTitle}>{t("progress.emptyTitle")}</h2>
          <p className={styles.firstBody}>{t("progress.emptyBody")}</p>
          {years.length === 0 && (
            <Link to="/registra" className="sf-btn sf-btn--primary">
              {t("nav.registra")}
            </Link>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      {yearPicker}

      <div className={styles.hero}>
        <span className={styles.heroYear}>{year}</span>
        <div className={styles.heroGrid}>
          <HeroStat
            icon={Sailboat}
            value={String(totals.sessions)}
            label={t("progress.totals.sessions")}
            delta={
              showDeltas && (
                <Delta
                  current={totals.sessions}
                  previous={previous.sessions}
                  previousYear={year - 1}
                  format={String}
                />
              )
            }
          />
          <HeroStat
            icon={CalendarDays}
            value={String(totals.days)}
            label={t("progress.totals.days")}
            delta={
              showDeltas && (
                <Delta
                  current={totals.days}
                  previous={previous.days}
                  previousYear={year - 1}
                  format={String}
                />
              )
            }
          />
          <HeroStat
            icon={Route}
            value={fmtDistance(totals.distance_m)}
            label={t("progress.totals.distance")}
            delta={
              showDeltas && (
                <Delta
                  current={totals.distance_m}
                  previous={previous.distance_m}
                  previousYear={year - 1}
                  format={fmtDistance}
                />
              )
            }
          />
          <HeroStat
            icon={Timer}
            value={fmtDuration(totals.duration_s)}
            label={t("progress.totals.duration")}
            delta={
              showDeltas && (
                <Delta
                  current={totals.duration_s}
                  previous={previous.duration_s}
                  previousYear={year - 1}
                  format={fmtDuration}
                />
              )
            }
          />
        </div>
      </div>

      {hasVolume && (
        <Section title={t("progress.monthsTitle")}>
          <div className={styles.chart}>
            <MonthBars
              values={by_month}
              ghost={previous.sessions > 0 ? previous_by_month : undefined}
              label={monthBarsLabel(by_month, year, i18n.language, t("progress.monthsTitle"))}
            />
            {previous.sessions > 0 && (
              <p className={styles.legend}>
                <span className={styles.legendSwatch} aria-hidden="true" />
                {year}
                <span className={`${styles.legendSwatch} ${styles.legendGhost}`} aria-hidden="true" />
                {year - 1}
              </p>
            )}
          </div>
        </Section>
      )}

      {personal_bests.length > 0 && (
        <Section
          title={
            <span className={styles.bestsHead}>
              <Trophy size={17} aria-hidden="true" />
              {t("progress.bestsTitle")}
              <span className={styles.allTime}>{t("progress.allTime")}</span>
            </span>
          }
        >
          <ul className={styles.bests}>
            {personal_bests.map((best) => {
              const Icon = BEST_ICONS[best.metric];
              return (
                <li key={best.metric}>
                  <Link
                    to={`/diario/activities/${best.activity_id}/barche/${best.session_id}`}
                    className={styles.best}
                  >
                    <Icon size={18} className={styles.bestIcon} aria-hidden="true" />
                    <span className={styles.bestText}>
                      <span className={styles.bestLabel}>{t(`progress.bests.${best.metric}`)}</span>
                      <span className={styles.bestMeta}>
                        {[best.boat_name, fmtDate(best.occurred_at)].filter(Boolean).join(" · ")}
                      </span>
                    </span>
                    <span className={styles.bestValue}>{bestValue(best)}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </Section>
      )}

      {by_boat.length > 0 && (
        <Section title={t("progress.byBoatTitle")}>
          <ul className={styles.boats}>
            {by_boat.map((boat) => (
              <li key={boat.boat_id} className={styles.boat}>
                <span className={styles.boatName}>{boat.name ?? t("common.none")}</span>
                <span className={styles.boatMeta}>
                  {`${boat.sessions} · ${fmtDistance(boat.distance_m)} · ${fmtDuration(boat.duration_s)}`}
                </span>
                <span className={styles.boatTrack} aria-hidden="true">
                  <span
                    className={styles.boatFill}
                    style={{ width: `${(boat.sessions / maxBoatSessions) * 100}%` }}
                  />
                </span>
              </li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}
