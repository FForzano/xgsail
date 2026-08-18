import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Disc } from "lucide-react";
import { liveRecordingKeys, liveRecordingsService } from "@/services/liveRecordings";
import { useAuth } from "@/hooks/useAuth";
import { userLabel } from "@/utils/format";
import type { LiveRecording, UUID } from "@/types";
import styles from "./calloutStrip.module.css";

// Ambient information on a page people leave open: a minute is soon enough,
// and a tighter poll is battery the recording itself needs.
const POLL_MS = 60_000;

export interface JoinRecordingState {
  prefillBoatId: UUID;
  prefillActivityId: UUID | null;
}

/** "X is recording on Aria right now — record too."
 *
 * The point at which two people aboard can agree they are on the same outing,
 * instead of finding out after upload that the backend merged their tracks by
 * boat and time window. Tapping through opens the recording sheet with the
 * same boat and activity already chosen, which is what makes the two
 * recordings line up.
 *
 * Purely a hint: it grants nothing, and every write it implies is still
 * checked server-side. The backend leaves the viewer's own recording out, so
 * this only ever shows other people. */
export function LiveRecordingBanner({ boatId }: { boatId?: UUID }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const navigate = useNavigate();

  const live = useQuery({
    queryKey: liveRecordingKeys.all,
    queryFn: liveRecordingsService.list,
    refetchInterval: POLL_MS,
    enabled: !!user,
  });

  const rows = (live.data ?? []).filter((r) => !boatId || r.boat_id === boatId);
  if (rows.length === 0) return null;

  const join = (row: LiveRecording) => {
    const state: JoinRecordingState = {
      prefillBoatId: row.boat_id,
      prefillActivityId: row.activity_id,
    };
    navigate("/registra", { state });
  };

  return (
    <div className={styles.strip}>
      {rows.map((row) => (
        <button
          key={row.id}
          type="button"
          className={`${styles.card} ${styles.accentDanger}`}
          onClick={() => join(row)}
        >
          <Disc size={18} strokeWidth={1.75} aria-hidden />
          <span className={styles.text}>
            <span className={styles.title}>
              {t("live.inProgress", {
                name: userLabel(row.user),
                boat: row.boat_name ?? "",
              })}
            </span>
            {row.activity_name && (
              <span className={`sf-muted ${styles.subtitle}`}>{row.activity_name}</span>
            )}
          </span>
          <span className={styles.cta}>{t("live.joinCta")}</span>
        </button>
      ))}
    </div>
  );
}
