import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ChevronRight } from "lucide-react";
import { useProgress } from "@/hooks/useProgress";
import { fmtDistance, fmtDuration } from "@/utils/format";
import styles from "./ProgressStrip.module.css";

/** Twelve monthly bars, with the previous year drawn behind as a subdued
 * ghost. Deliberately not a GitHub-style day heatmap: a sailor goes out
 * ~30-40 times a year, nearly all of them between April and September, so a
 * 52x7 grid would be over 90% empty and would read as "you do nothing".
 * Lives here rather than in the page because the strip is the smaller,
 * more constrained consumer — the page imports it. */
export function MonthBars({
  values,
  ghost,
  variant = "full",
  label,
}: {
  values: number[];
  ghost?: number[];
  variant?: "full" | "spark";
  label: string;
}) {
  const { i18n } = useTranslation();
  const narrow = useMemo(() => {
    const fmt = new Intl.DateTimeFormat(i18n.language, { month: "narrow" });
    return values.map((_, m) => fmt.format(new Date(2021, m, 1)));
  }, [i18n.language, values]);

  const peak = Math.max(1, ...values, ...(ghost ?? []));
  const height = (n: number) => `${Math.max(n > 0 ? 6 : 0, (n / peak) * 100)}%`;

  return (
    <div
      className={`${styles.bars} ${variant === "spark" ? styles.barsSpark : styles.barsFull}`}
      role="img"
      aria-label={label}
    >
      {values.map((v, m) => (
        <div key={m} className={styles.col}>
          {variant === "full" && <span className={styles.count}>{v > 0 ? v : ""}</span>}
          <div className={styles.track}>
            {ghost && <span className={styles.ghost} style={{ height: height(ghost[m] ?? 0) }} />}
            <span className={styles.bar} style={{ height: height(v) }} />
          </div>
          {variant === "full" && (
            <span className={styles.month} aria-hidden="true">
              {narrow[m]}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

/** Text alternative for the chart: the bars are data, not decoration. */
export function monthBarsLabel(values: number[], year: number, language: string, title: string): string {
  const fmt = new Intl.DateTimeFormat(language, { month: "long" });
  const parts = values.map((v, m) => `${fmt.format(new Date(2021, m, 1))} ${v}`);
  return `${title} ${year}: ${parts.join(", ")}`;
}

/** Compact progress hook on the personal diary feed. Kept to a single block
 * on purpose: the feed below is the reason that page exists, so this must
 * never push the first activity card below the fold. Renders nothing until
 * the shared `useProgress` query (same key as the page's) has data —
 * `MyDiaryPage` decides whether it shows at all. */
export function ProgressStrip() {
  const { t, i18n } = useTranslation();
  const { data } = useProgress();

  if (!data || data.totals.sessions === 0) return null;

  const { totals, by_month, year } = data;
  const showSpark = totals.sessions >= 3;

  return (
    <Link to="/diario/progressi" className={styles.strip}>
      <div className={styles.stripMain}>
        <div className={styles.stripHead}>
          <span className={styles.stripTitle}>{t("progress.title")}</span>
          <span className={styles.stripYear}>{year}</span>
        </div>
        <div className={styles.stripStats}>
          <span className={styles.stripStat}>
            <b>{totals.sessions}</b>
            {t("progress.totals.sessions")}
          </span>
          <span className={styles.stripStat}>
            <b>{fmtDistance(totals.distance_m)}</b>
            {t("progress.totals.distance")}
          </span>
          <span className={styles.stripStat}>
            <b>{fmtDuration(totals.duration_s)}</b>
            {t("progress.totals.duration")}
          </span>
        </div>
      </div>
      {showSpark && (
        <div className={styles.stripSpark}>
          <MonthBars
            values={by_month}
            variant="spark"
            label={monthBarsLabel(by_month, year, i18n.language, t("progress.monthsTitle"))}
          />
        </div>
      )}
      <span className={styles.stripCta}>
        <span className={styles.stripCtaText}>{t("progress.seeAll")}</span>
        <ChevronRight size={16} aria-hidden="true" />
      </span>
    </Link>
  );
}
