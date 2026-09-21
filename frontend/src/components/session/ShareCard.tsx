import { forwardRef, type CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import { Avatar } from "@/components/ui/Avatar";
import { fmtDate, fmtDistance, fmtKnots, userLabel } from "@/utils/format";
import type { Track } from "@/components/race/raceModel";
import type { SessionCrew, SessionStats } from "@/types";
import { TrackSvg } from "./TrackSvg";
import styles from "./ShareCard.module.css";

export interface ShareCardData {
  boatName: string;
  boatPhotoUrl: string | null;
  track: Track | null;
  startedAt: string | null;
  stats: SessionStats | null;
  crew: SessionCrew[];
}

const CARD_WIDTH = 1080;
// The track occupies the card's upper region; the text overlay owns the rest,
// so the two never fight for the same pixels regardless of how much text
// the user enabled.
const TRACK_HEIGHT = 1280;

/** Fixed 1080x1920 (9:16) card rasterized by html-to-image for the
 * "share as image" flow (see ShareImageModal) — real DOM/CSS rather than
 * canvas draw calls, so it can reuse the app's own design language instead of
 * re-implementing text/gradient layout by hand. Fixed px, not rem, since this
 * is an exported image asset at one exact resolution, not a responsive UI
 * element.
 *
 * Full-bleed by design: the photo (or a tinted gradient) fills the whole
 * frame and everything else sits on top of it over a scrim, rather than the
 * photo taking a band and the text living underneath. */
export const ShareCard = forwardRef<
  HTMLDivElement,
  {
    data: ShareCardData;
    includeBoatPhoto: boolean;
    includeTrack: boolean;
    includeStats: boolean;
    includeTitle: boolean;
    includeCrew: boolean;
    textColor: string;
    trackColor: string;
  }
>(function ShareCard(
  {
    data,
    includeBoatPhoto,
    includeTrack,
    includeStats,
    includeTitle,
    includeCrew,
    textColor,
    trackColor,
  },
  ref,
) {
  const { t } = useTranslation();
  const photoUrl = includeBoatPhoto ? data.boatPhotoUrl : null;
  const track = includeTrack ? data.track : null;

  return (
    <div
      ref={ref}
      className={styles.card}
      style={{ "--share-text": textColor, "--share-track": trackColor } as CSSProperties}
    >
      {photoUrl ? (
        // No crossOrigin: html-to-image inlines images by fetching them, it
        // never taints a canvas — the attribute only makes the load fail
        // against a bucket that doesn't send CORS headers.
        <img className={styles.photo} src={photoUrl} alt="" />
      ) : (
        <div className={styles.gradient}>
          <div className={styles.gradientTint} />
        </div>
      )}
      {track && (
        <TrackSvg
          className={styles.track}
          track={track}
          color={trackColor}
          width={CARD_WIDTH}
          height={TRACK_HEIGHT}
          padding={120}
          strokeWidth={12}
        />
      )}
      <div className={styles.scrim} />
      <div className={styles.brand}>XGSail</div>
      <div className={styles.overlay}>
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
    </div>
  );
});
