import { useTranslation } from "react-i18next";
import { Avatar } from "@/components/ui/Avatar";
import { fmtDistance, fmtKnots, userLabel } from "@/utils/format";
import type { SessionCrew, SessionStats } from "@/types";
import styles from "./BoatSessionCarousel.module.css";

export interface BoatSessionCarouselItem {
  sessionId: string;
  boatName: string;
  boatPhotoUrl: string | null;
  trackThumbUrl: string | null;
  crew: SessionCrew[];
  stats?: SessionStats | null;
  /** True unless the viewer has boat-level access to this session without
   * having crewed it themselves — see the `was_aboard` contract. */
  wasAboard: boolean;
}

/** Mobile-only alternative to the boats table (see ActivityDetailPage):
 * one boat/session per card, horizontally paged — a drag always settles on
 * exactly one neighbor, never a free scroll, via `scroll-snap-stop: always`
 * (see .carousel in BoatSessionCarousel.module.css). Tapping a card opens its session,
 * same destination the table's row click goes to. */
export function BoatSessionCarousel({
  items,
  onOpen,
}: {
  items: BoatSessionCarouselItem[];
  onOpen: (sessionId: string) => void;
}) {
  const { t } = useTranslation();

  return (
    <div className={`${styles.carousel} sf-mobile-only`}>
      {items.map((item) => (
        <button
          key={item.sessionId}
          type="button"
          className={styles.card}
          onClick={() => onOpen(item.sessionId)}
        >
          <div className={styles.photo}>
            {item.boatPhotoUrl ? (
              <img src={item.boatPhotoUrl} alt="" />
            ) : item.trackThumbUrl ? (
              <img src={item.trackThumbUrl} alt="" />
            ) : (
              <span className={styles.photoEmpty} aria-hidden />
            )}
            {/* Track thumbnail as a small corner badge, only when there's
                also a boat photo as the main image — otherwise the track
                thumbnail above already is the main image. */}
            {item.boatPhotoUrl && item.trackThumbUrl && (
              <img className={styles.trackBadge} src={item.trackThumbUrl} alt="" />
            )}
            {/* Otherwise-plain photo gives no hint the whole card opens the
                session — same "this is tappable" affordance as the boats
                table's trailing chevron. */}
            <span className={styles.openBadge} aria-hidden>
              <svg viewBox="0 0 16 16" width="14" height="14">
                <path
                  d="M5 2.5 11.5 8 5 13.5"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </span>
          </div>
          <div className={styles.body}>
            <h3 className={styles.name}>
              {item.boatName}
              {!item.wasAboard && (
                <span className="sf-badge sf-badge--sm">{t("sessions.notAboard")}</span>
              )}
            </h3>
            {item.stats && (
              <div className={styles.stats}>
                <div className={styles.stat}>
                  <span className={styles.statValue}>
                    {fmtDistance(item.stats.distance_m)}
                  </span>
                  <span className={styles.statLabel}>{t("sessions.distance")}</span>
                </div>
                <div className={styles.stat}>
                  <span className={styles.statValue}>
                    {fmtKnots(item.stats.avg_speed_kts)}
                  </span>
                  <span className={styles.statLabel}>{t("sessions.avgSpeed")}</span>
                </div>
                <div className={styles.stat}>
                  <span className={styles.statValue}>
                    {fmtKnots(item.stats.max_speed_kts)}
                  </span>
                  <span className={styles.statLabel}>{t("sessions.maxSpeed")}</span>
                </div>
              </div>
            )}
            {item.crew.length > 0 && (
              <ul className={styles.crew}>
                {item.crew.map((c) => (
                  <li key={c.user_id} className="sf-crew-row">
                    <Avatar
                      profileImage={c.user?.profile_image}
                      firstName={c.user?.first_name}
                      lastName={c.user?.last_name}
                      size="sm"
                    />
                    <span>
                      <strong>{userLabel(c.user)}</strong>{" "}
                      <span className="sf-muted">
                        {t(`sessions.sailingRoles.${c.sailing_role}`)}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </button>
      ))}
    </div>
  );
}
