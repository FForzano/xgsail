import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { boatsService, boatKeys } from "@/services/boats";
import { importsService } from "@/services/imports";
import { putToUploadUrl } from "@/api/media";
import { ApiError } from "@/api/client";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { Spinner } from "@/components/ui/Spinner";
import type { ImportRow, UUID } from "@/types";

type Phase = "form" | "uploading" | "processing" | "done" | "failed";

/** Manual GPX/CSV import wizard: register → PUT bytes → complete → poll. */
export function ImportPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const fileRef = useRef<HTMLInputElement>(null);
  const [boatId, setBoatId] = useState("");
  const [phase, setPhase] = useState<Phase>("form");
  const [row, setRow] = useState<ImportRow | null>(null);
  const [error, setError] = useState<string | null>(null);

  const boats = useQuery({ queryKey: boatKeys.mine, queryFn: () => boatsService.list(true) });

  const start = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file || !boatId) return;
    setError(null);
    try {
      setPhase("uploading");
      const ticket = await importsService.create(file.name);
      await putToUploadUrl(ticket.upload_url, file);
      setPhase("processing");
      const completed = await importsService.complete(ticket.import_id, {
        boat_id: boatId as UUID,
      });
      setRow(completed);
      if (completed.status === "processed") setPhase("done");
      else if (completed.status === "failed") setPhase("failed");
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : e instanceof Error ? e.message : String(e));
      setPhase("failed");
    }
  };

  // CSV imports finish asynchronously (worker pipeline) — poll until final.
  useEffect(() => {
    if (phase !== "processing" || !row) return;
    if (row.status === "processed") {
      setPhase("done");
      return;
    }
    if (row.status === "failed") {
      setPhase("failed");
      return;
    }
    const id = window.setInterval(async () => {
      const fresh = await importsService.get(row.id);
      setRow(fresh);
      if (fresh.status === "processed") setPhase("done");
      if (fresh.status === "failed") setPhase("failed");
    }, 3000);
    return () => window.clearInterval(id);
  }, [phase, row]);

  return (
    <Card title={t("sessions.importTitle")}>
      {phase === "form" && (
        <>
          <label className="sf-field">
            <span className="sf-field__label">{t("sessions.importFile")}</span>
            <input ref={fileRef} type="file" accept=".gpx,.csv" className="sf-field__input" />
          </label>
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
            <Button onClick={() => void start()} disabled={!boatId}>
              {t("sessions.importStart")}
            </Button>
          </div>
        </>
      )}
      {(phase === "uploading" || phase === "processing") && (
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
              onClick={() =>
                navigate(row?.session_id ? `/diario/sessioni/${row.session_id}` : "/diario/sessioni")
              }
            >
              {t("diario.sessions")}
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
            <Button variant="ghost" onClick={() => setPhase("form")}>
              {t("common.cancel")}
            </Button>
          </div>
        </>
      )}
    </Card>
  );
}
