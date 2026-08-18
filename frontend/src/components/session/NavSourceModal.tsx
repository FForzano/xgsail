import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Watch, Navigation, Check, Unlink } from "lucide-react";
import { sessionKeys, sessionsService } from "@/services/sessions";
import { activityKeys } from "@/services/activities";
import { useToast } from "@/hooks/useToast";
import { useAuth } from "@/hooks/useAuth";
import { ApiError } from "@/api/client";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { fmtDuration, userLabel } from "@/utils/format";
import type { NavSourceCandidate, UUID } from "@/types";
import styles from "./NavSourceModal.module.css";

// Which recorded track is *the* track of this session.
//
// A session can collect several: the boat's tracker plus a watch per crew
// member. Everything downstream (map, GPX, replay, the whole analysis) reads
// one, so when there's more than one candidate someone has to say which — and
// they need the numbers to decide, hence points/span/rate/gaps per option.
export function NavSourceModal({
  sessionId,
  canEdit,
  onClose,
}: {
  sessionId: UUID;
  /** Whether the viewer may change the session's track. Detaching their own
   * upload is always allowed and gated separately. */
  canEdit: boolean;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { notify } = useToast();
  const { user } = useAuth();
  const [picked, setPicked] = useState<UUID | null>(null);
  const [detaching, setDetaching] = useState<UUID | null>(null);

  // With quality metrics — the picker is exactly the place worth reading the
  // candidate series to measure their span and gaps.
  const candidates = useQuery({
    queryKey: sessionKeys.navSources(sessionId, true),
    queryFn: () => sessionsService.navSources(sessionId, true),
  });

  const apply = useMutation({
    mutationFn: (uploadId: UUID) => sessionsService.setNavSource(sessionId, uploadId),
    onSuccess: async () => {
      notify(t("sessions.navSource.applied"), "success");
      // The track changed, so the streams list and everything derived from it
      // are stale; the reanalysis poll on the page picks up the rest.
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: sessionKeys.streams(sessionId) }),
        // Prefix match: invalidates both the cheap and the with-quality variant.
        queryClient.invalidateQueries({ queryKey: ["sessions", sessionId, "nav-sources"] }),
        queryClient.invalidateQueries({ queryKey: sessionKeys.analysis(sessionId) }),
        queryClient.invalidateQueries({ queryKey: sessionKeys.stats(sessionId) }),
        queryClient.invalidateQueries({ queryKey: sessionKeys.reanalysisStatus(sessionId) }),
      ]);
      onClose();
    },
    onError: (err) =>
      notify(err instanceof ApiError ? err.detail : t("errors.generic"), "error"),
  });

  // Undoing the automatic merge. Separate mutation from `apply` because it is
  // the opposite decision — these tracks are not the same outing at all — and
  // it is open to the contributor even when they may not choose the track.
  const detach = useMutation({
    mutationFn: (uploadId: UUID) => sessionsService.detachUpload(sessionId, uploadId),
    onSuccess: async (result) => {
      notify(t("sessions.navSource.detached"), "success");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: sessionKeys.detail(sessionId) }),
        queryClient.invalidateQueries({ queryKey: sessionKeys.streams(sessionId) }),
        queryClient.invalidateQueries({ queryKey: sessionKeys.crew(sessionId) }),
        queryClient.invalidateQueries({ queryKey: sessionKeys.analysis(sessionId) }),
        queryClient.invalidateQueries({ queryKey: sessionKeys.stats(sessionId) }),
        queryClient.invalidateQueries({ queryKey: sessionKeys.reanalysisStatus(sessionId) }),
        // Prefix match: both the cheap and the with-quality variant.
        queryClient.invalidateQueries({ queryKey: ["sessions", sessionId, "nav-sources"] }),
        queryClient.invalidateQueries({ queryKey: activityKeys.all }),
      ]);
      onClose();
      // The detached track now lives on its own session, under whichever
      // activity it landed in (a fresh private one, or the shared event it
      // was already part of) — the session route is nested under the activity.
      navigate(`/diario/activities/${result.activity_id}/barche/${result.session_id}`);
    },
    onError: (err) =>
      notify(err instanceof ApiError ? err.detail : t("errors.generic"), "error"),
  });

  const current = candidates.data?.find((c) => c.is_resolved);
  const selected = picked ?? current?.session_upload_id ?? null;
  // Mirrors the backend: crew/managers may separate any contributed track,
  // and everyone may always withdraw their own.
  const canDetach = (c: NavSourceCandidate) =>
    canEdit || (!!user && c.subject_user_id === user.id);

  return (
    <Modal title={t("sessions.navSource.title")} onClose={onClose}>
      <p className={`sf-muted ${styles.intro}`}>{t("sessions.navSource.intro")}</p>

      {candidates.isLoading && <Spinner />}

      <div className={styles.list}>
        {candidates.data?.map((c) => (
          <button
            key={c.session_upload_id}
            type="button"
            className={`${styles.option} ${
              selected === c.session_upload_id ? styles.optionSelected : ""
            }`}
            onClick={() => setPicked(c.session_upload_id)}
          >
            {c.device?.category === "wearable" ? <Watch size={18} /> : <Navigation size={18} />}
            <span className={styles.body}>
              <span className={styles.name}>
                {candidateLabel(c, t)}
                {c.is_resolved && <span className="sf-badge">{t("sessions.navSource.current")}</span>}
                {selected === c.session_upload_id && !c.is_resolved && <Check size={14} />}
              </span>
              <span className={styles.meta}>
                <span>{t("sessions.navSource.points", { n: c.row_count ?? 0 })}</span>
                {c.duration_s != null && <span>{fmtDuration(c.duration_s)}</span>}
                {c.sample_rate_hz != null && (
                  <span>{t("sessions.navSource.rate", { hz: c.sample_rate_hz })}</span>
                )}
                {coveragePct(c) != null && (
                  <span className={coveragePct(c)! < 90 ? styles.warn : undefined}>
                    {t("sessions.navSource.coverage", { pct: coveragePct(c) })}
                  </span>
                )}
                {!!c.gap_count && (
                  <span className={styles.warn}>
                    {t("sessions.navSource.gaps", { n: c.gap_count })}
                  </span>
                )}
              </span>
            </span>
          </button>
        ))}
      </div>

      {/* Undoing the merge, not choosing between tracks — separate action,
          and open to whoever contributed the track even if they may not pick
          which one the session uses. */}
      {(candidates.data ?? []).some((c) => canDetach(c)) && (
        <div className={styles.detachBlock}>
          <p className={`sf-muted ${styles.note}`}>{t("sessions.navSource.detachIntro")}</p>
          {(candidates.data ?? []).filter(canDetach).map((c) => (
            <div key={`detach-${c.session_upload_id}`} className={styles.detachRow}>
              <span className={styles.detachName}>{candidateLabel(c, t)}</span>
              {detaching === c.session_upload_id ? (
                <span className={styles.detachActions}>
                  <Button
                    variant="ghost"
                    onClick={() => setDetaching(null)}
                    disabled={detach.isPending}
                  >
                    {t("common.cancel")}
                  </Button>
                  <Button
                    variant="danger"
                    onClick={() => detach.mutate(c.session_upload_id)}
                    disabled={detach.isPending}
                  >
                    {t("sessions.navSource.detachConfirm")}
                  </Button>
                </span>
              ) : (
                <Button variant="ghost" onClick={() => setDetaching(c.session_upload_id)}>
                  <Unlink size={16} strokeWidth={1.75} /> {t("sessions.navSource.detach")}
                </Button>
              )}
            </div>
          ))}
        </div>
      )}

      <p className={`sf-muted ${styles.note}`}>{t("sessions.navSource.reanalyzeNote")}</p>

      <div className={styles.footer}>
        <Button variant="ghost" onClick={onClose} disabled={apply.isPending}>
          {t("common.cancel")}
        </Button>
        {canEdit && (
          <Button
            onClick={() => selected && apply.mutate(selected)}
            disabled={
              apply.isPending || !selected || selected === current?.session_upload_id
            }
          >
            {t("sessions.navSource.applyAndReanalyze")}
          </Button>
        )}
      </div>
    </Modal>
  );
}

/** How much of the outing this track covers, as a whole percentage — the
 * number the default choice now turns on, so it has to be on screen or the
 * default looks arbitrary. Null for tracks recorded before the backend
 * measured spans, and for a session with no window of its own. */
function coveragePct(c: NavSourceCandidate): number | null {
  if (c.coverage_s == null || !c.session_started_at || !c.session_ended_at) return null;
  const window =
    (Date.parse(c.session_ended_at) - Date.parse(c.session_started_at)) / 1000;
  if (window <= 0) return null;
  return Math.min(100, Math.round((c.coverage_s / window) * 100));
}

function candidateLabel(c: NavSourceCandidate, t: (k: string) => string): string {
  const device = c.device?.nickname || c.device?.type_name || t("sessions.navSource.manualImport");
  // A wearable's track belongs to a person; name them, since that's what tells
  // two watches on the same boat apart.
  return c.user ? `${device} — ${userLabel(c.user)}` : device;
}
