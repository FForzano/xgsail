import { forwardRef } from "react";
import { useTranslation } from "react-i18next";
import { Avatar } from "@/components/ui/Avatar";
import { fmtDate, fmtDistance, fmtKnots, userLabel } from "@/utils/format";
import type { SessionCrew, SessionStats } from "@/types";
import styles from "./ShareCard.module.css";

export interface ShareCardData {
  boatName: string;
  boatPhotoUrl: string | null;
  trackThumbUrl: string | null;
  startedAt: string | null;
  stats: SessionStats | null;
  crew: SessionCrew[];
}

/** Fixed 1080x1920 (9:16) card rasterized by html-to-image for the
 * "share as image" flow (see ShareImageModal) — real DOM/CSS rather than
 * canvas draw calls, so it can reuse the app's own design language
 * (colors, radii, the BoatSessionCarousel photo+track-badge layout)
 * instead of re-implementing text/gradient layout by hand. Fixed px, not
 * rem, since this is an exported image asset at one exact resolution, not
 * a responsive UI element. */
export const ShareCard = forwardRef<
  HTMLDivElement,
  {
    data: ShareCardData;
    includeBoatPhoto: boolean;
    includeTrack: boolean;
    includeStats: boolean;
    includeTitle: boolean;
    includeCrew: boolean;
  }
>(function ShareCard({ data, includeBoatPhoto, includeTrack, includeStats, includeTitle, includeCrew }, ref) {
  const { t } = useTranslation();

  // Independent toggles, same fallback as BoatSessionCarousel: the boat
  // photo is the main image with the track as a small corner badge when
  // both are on; either one alone becomes the main image by itself.
  const mainPhotoUrl = includeBoatPhoto ? data.boatPhotoUrl : null;
  const mainTrackUrl = includeTrack ? data.trackThumbUrl : null;
  const mainImageUrl = mainPhotoUrl ?? mainTrackUrl;
  const trackBadgeUrl = mainPhotoUrl && mainTrackUrl ? mainTrackUrl : null;

  return (
    <div ref={ref} className={styles.card}>
      {mainImageUrl && (
        <div className={styles.photo}>
          <img src={mainImageUrl} alt="" crossOrigin="anonymous" />
          {trackBadgeUrl && (
            <img className={styles.trackBadge} src={trackBadgeUrl} alt="" crossOrigin="anonymous" />
          )}
        </div>
      )}
      <div className={styles.body}>
        {includeTitle && (
          <div className={styles.title}>
            <h2 className={styles.boatName}>{data.boatName}</h2>
            <span className={styles.date}>{fmtDate(data.startedAt)}</span>
          </div>
        )}
        {includeStats && data.stats && (
          <div className={styles.stats}>
            <div className={styles.stat}>
              <span className={styles.statValue}>{fmtDistance(data.stats.distance_m)}</span>
              <span className={styles.statLabel}>{t("sessions.distance")}</span>
            </div>
            <div className={styles.stat}>
              <span className={styles.statValue}>{fmtKnots(data.stats.avg_speed_kts)}</span>
              <span className={styles.statLabel}>{t("sessions.avgSpeed")}</span>
            </div>
            <div className={styles.stat}>
              <span className={styles.statValue}>{fmtKnots(data.stats.max_speed_kts)}</span>
              <span className={styles.statLabel}>{t("sessions.maxSpeed")}</span>
            </div>
          </div>
        )}
        {includeCrew && data.crew.length > 0 && (
          <ul className={styles.crew}>
            {data.crew.map((c) => (
              <li key={c.user_id} className={styles.crewRow}>
                <Avatar
                  profileImage={c.user?.profile_image}
                  firstName={c.user?.first_name}
                  lastName={c.user?.last_name}
                  size="md"
                />
                <span>
                  <strong>{userLabel(c.user)}</strong>{" "}
                  <span className={styles.crewRole}>{t(`sessions.sailingRoles.${c.sailing_role}`)}</span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className={styles.brand}>XGSail</div>
    </div>
  );
});
