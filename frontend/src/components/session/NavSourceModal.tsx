import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Watch, Navigation, Check } from "lucide-react";
import { sessionKeys, sessionsService } from "@/services/sessions";
import { useToast } from "@/hooks/useToast";
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
  onClose,
}: {
  sessionId: UUID;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [picked, setPicked] = useState<UUID | null>(null);

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

  const current = candidates.data?.find((c) => c.is_resolved);
  const selected = picked ?? current?.session_upload_id ?? null;

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

      <p className={`sf-muted ${styles.note}`}>{t("sessions.navSource.reanalyzeNote")}</p>

      <div className={styles.footer}>
        <Button variant="ghost" onClick={onClose} disabled={apply.isPending}>
          {t("common.cancel")}
        </Button>
        <Button
          onClick={() => selected && apply.mutate(selected)}
          disabled={
            apply.isPending || !selected || selected === current?.session_upload_id
          }
        >
          {t("sessions.navSource.applyAndReanalyze")}
        </Button>
      </div>
    </Modal>
  );
}

function candidateLabel(c: NavSourceCandidate, t: (k: string) => string): string {
  const device = c.device?.nickname || c.device?.type_name || t("sessions.navSource.manualImport");
  // A wearable's track belongs to a person; name them, since that's what tells
  // two watches on the same boat apart.
  return c.user ? `${device} — ${userLabel(c.user)}` : device;
}
