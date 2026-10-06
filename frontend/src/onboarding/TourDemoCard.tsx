import { useTranslation } from "react-i18next";
import { Sailboat } from "lucide-react";
import styles from "@/components/diario/EventRow.module.css";

/** A non-clickable stand-in for a diario logbook entry, shown only during a
 * guided tour when the real feed is empty (see MyDiaryPage). It mirrors an
 * `EventRow`'s layout by reusing its CSS module, so the "your sessions land
 * here" step has a realistic entry to frame instead of an empty state — no
 * fabricated `Activity`/broken detail link, purely visual. The `dataTour` prop
 * carries the same anchor the tour step targets. */
export function TourDemoCard({ dataTour }: { dataTour?: string }) {
  const { t } = useTranslation();
  return (
    <article className={styles.entry} data-opens-day data-tour={dataTour}>
      <div className={styles.margin} />
      <div className={styles.main}>
        <header className={styles.head}>
          <span className={styles.title}>{t("onboarding.demo.session.title")}</span>
          <span className={styles.codes}>
            <span className="sf-badge sf-badge--activity">{t("gruppi.eventKind.activity")}</span>
            <span className="sf-badge">{t("onboarding.demo.badge")}</span>
          </span>
        </header>
        <div className={styles.mediaBox}>
          <div className={styles.demoMedia} aria-hidden>
            <Sailboat size={32} />
          </div>
        </div>
        <p className="sf-muted">{t("onboarding.demo.session.meta")}</p>
        <p className={styles.description}>{t("onboarding.demo.session.description")}</p>
      </div>
    </article>
  );
}
