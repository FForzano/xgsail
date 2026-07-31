import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Card } from "@/components/ui/Card";
import { MediaPlaceholder } from "@/components/common/MediaPlaceholder";
import { regattaStatusBadge, raceStatusBadge } from "@/utils/badges";
import { fmtDate, fmtDateRange, fmtTime } from "@/utils/format";
import type { Regatta } from "@/types";
import styles from "./RegattaHero.module.css";

/** The race this hero is standing in for, when used as a race dashboard's
 * header: the regatta then becomes breadcrumb context rather than the
 * subject of the page. Passing this switches the hero to its compact form. */
export interface RegattaHeroRace {
  raceNumber: number;
  status: string;
  /** Race day, `YYYY-MM-DD`. */
  date: string | null;
  /** Full timestamp; only its time of day is shown (the day is in the crumb). */
  startTime: string | null;
}

export interface RegattaHeroProps {
  regatta: Regatta;
  /** Organizing club's name. Resolved by the caller — the hero fetches
   * nothing, so it works the same on a page that already has the club and on
   * the public join landing that doesn't. */
  clubName?: string | null;
  /** Boat-class name, likewise caller-resolved. */
  boatClassName?: string | null;
  raceCount?: number;
  /** Manage controls (image uploader, edit), rendered over the poster's top
   * right. Omit for read-only viewers. */
  actions?: ReactNode;
  /** Makes the poster clickable; the caller owns the lightbox. */
  onOpenImage?: () => void;
  /** Compact breadcrumb form for a race dashboard — no poster, no actions. */
  race?: RegattaHeroRace;
}

/** Header for everything regatta-facing: the regatta page, the join landing,
 * and (compact) a race dashboard. Full form is a full-bleed poster with the
 * name, status and meta line laid over a scrim; with no poster uploaded it
 * falls back to the same tinted placeholder the diario feed uses, so the
 * block never becomes an empty grey band. */
export function RegattaHero({
  regatta,
  clubName,
  boatClassName,
  raceCount,
  actions,
  onOpenImage,
  race,
}: RegattaHeroProps) {
  const { t } = useTranslation();

  if (race) {
    return (
      <Card className={styles.compact}>
        <div>
          <div className={styles.crumbs}>
            <Link to={`/diario/regate/regatta/${regatta.id}`} className={styles.crumbLink}>
              {regatta.name}
            </Link>
            <span className={styles.separator} aria-hidden>
              ›
            </span>
            <span>{fmtDate(race.date)}</span>
          </div>
          <h1 className={styles.raceTitle}>
            {t("regate.raceNumber")} {race.raceNumber}
          </h1>
        </div>
        <div className={styles.compactMeta}>
          <span className={raceStatusBadge(race.status)}>{t(`race.status.${race.status}`)}</span>
          {race.startTime && <span>{fmtTime(new Date(race.startTime).getTime())}</span>}
        </div>
      </Card>
    );
  }

  const meta = [
    clubName,
    fmtDateRange(regatta.start_date, regatta.end_date),
    boatClassName,
    raceCount ? t("regate.raceCount", { count: raceCount }) : null,
  ].filter(Boolean);

  return (
    <Card className={`sf-card--flush sf-card--flush-top ${styles.hero}`}>
      <div className={styles.poster}>
        {regatta.image ? (
          onOpenImage ? (
            <button
              type="button"
              className={styles.imageButton}
              onClick={onOpenImage}
              aria-label={t("regate.viewImage")}
            >
              <img className={styles.image} src={regatta.image.url} alt="" />
            </button>
          ) : (
            <img className={styles.image} src={regatta.image.url} alt="" />
          )
        ) : (
          <MediaPlaceholder kind="regatta" size={56} />
        )}
        <div className={styles.scrim} aria-hidden />
        <div className={styles.overlay}>
          <span className={regattaStatusBadge(regatta.status)}>
            {t(`regate.status.${regatta.status}`)}
          </span>
          <h1 className={styles.name}>{regatta.name}</h1>
          <p className={styles.meta}>{meta.join(" · ")}</p>
        </div>
        {actions && <div className={styles.actions}>{actions}</div>}
      </div>
      {regatta.description && <p className={styles.description}>{regatta.description}</p>}
    </Card>
  );
}
