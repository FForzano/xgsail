import { useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { boatsService, boatKeys } from "@/services/boats";
import { sessionsService } from "@/services/sessions";
import { useShareTarget } from "@/hooks/useShareTarget";
import { useImportUpload } from "@/hooks/useImportUpload";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { Spinner } from "@/components/ui/Spinner";
import type { UUID } from "@/types";

/** GPX/CSV import wizard: register → PUT bytes → complete → poll. Handles
 * both a manually-picked file and one arriving from the OS share sheet
 * (native only, see hooks/useShareTarget) through the same code path. */
export function ImportPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const activityId = searchParams.get("activityId") as UUID | null;
  const fileRef = useRef<HTMLInputElement>(null);
  const { pendingFile, clearPendingShare } = useShareTarget();
  const [boatId, setBoatId] = useState("");
  const { phase, row, error, uploadProgress, start, reset } = useImportUpload();

  const boats = useQuery({ queryKey: boatKeys.mine, queryFn: () => boatsService.list(true) });
  // Only the session's own detail route needs the parent activity — fetched
  // just to build that link once the import lands, not shown anywhere else.
  const importedSession = useQuery({
    queryKey: ["sessions", row?.session_id, "for-import-redirect"],
    queryFn: () => sessionsService.get(row!.session_id!),
    enabled: phase === "done" && !!row?.session_id,
  });

  const onStart = async () => {
    const file = pendingFile ?? fileRef.current?.files?.[0];
    if (!file || !boatId) return;
    clearPendingShare();
    try {
      await start(file, { boatId: boatId as UUID, activityId: activityId ?? undefined });
    } catch {
      // surfaced via `error` below
    }
  };

  return (
    <Card title={t("sessions.importTitle")}>
      {phase === "idle" && (
        <>
          {pendingFile ? (
            <p className="sf-field__label">
              {t("sessions.importFile")}: {pendingFile.name}
            </p>
          ) : (
            <label className="sf-field">
              <span className="sf-field__label">{t("sessions.importFile")}</span>
              <input ref={fileRef} type="file" accept=".gpx,.csv" className="sf-field__input" />
            </label>
          )}
          <Select
            label={t("sessions.importBoat")}
            id="import-boat"
            value={boatId}
            onChange={(e) => setBoatId(e.target.value)}
            required
          >
            <option value="" disabled>
              …
            </option>
            {boats.data?.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </Select>
          <div className="sf-form__actions">
            <Button onClick={() => void onStart()} disabled={!boatId}>
              {t("sessions.importStart")}
            </Button>
          </div>
        </>
      )}
      {phase === "uploading" && (
        <>
          <div className="sf-progress" role="progressbar" aria-valuenow={Math.round(uploadProgress * 100)}>
            <div className="sf-progress__bar" style={{ width: `${Math.round(uploadProgress * 100)}%` }} />
          </div>
          <p className="sf-muted" style={{ textAlign: "center" }}>
            {t("sessions.uploading", { percent: Math.round(uploadProgress * 100) })}
          </p>
        </>
      )}
      {phase === "processing" && (
        <>
          <Spinner />
          <p className="sf-muted" style={{ textAlign: "center" }}>
            {t("sessions.processing")}
          </p>
        </>
      )}
      {phase === "done" && (
        <>
          <p className="sf-badge sf-badge--success">{t("sessions.importDone")}</p>
          <div className="sf-form__actions">
            <Button
              disabled={!!row?.session_id && !importedSession.data}
              onClick={() =>
                navigate(
                  importedSession.data
                    ? `/diario/activities/${importedSession.data.activity_id}/barche/${importedSession.data.id}`
                    : "/diario/personale",
                )
              }
            >
              {t("activities.title")}
            </Button>
          </div>
        </>
      )}
      {phase === "failed" && (
        <>
          <p className="sf-form__error">
            {t("sessions.importFailed")}
            {error ? ` — ${error}` : row?.error ? ` — ${row.error}` : ""}
          </p>
          <div className="sf-form__actions">
            <Button variant="ghost" onClick={reset}>
              {t("common.cancel")}
            </Button>
          </div>
        </>
      )}
    </Card>
  );
}
