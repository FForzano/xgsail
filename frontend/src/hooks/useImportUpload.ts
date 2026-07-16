import { useEffect, useState } from "react";
import { importsService } from "@/services/imports";
import { putToUploadUrl } from "@/api/media";
import { ApiError } from "@/api/client";
import type { ImportRow, UUID } from "@/types";

export type ImportUploadPhase = "idle" | "uploading" | "processing" | "done" | "failed";

interface StartOptions {
  boatId: UUID;
  activityId?: UUID;
  subjectType?: "boat" | "crew_member";
  subjectUserId?: UUID;
}

/** Shared create → PUT → complete → poll sequence for the manual-import
 * pipeline (`/api/imports`) — used by both the file-picker wizard
 * (`ImportPage`) and the native GPS recorder (`RegistraPage`) so the upload
 * flow lives in exactly one place (CLAUDE.md "no duplicated logic"). Omitting
 * `activityId` lets the backend's `find_or_create_session` auto-create a
 * private "solo" activity — the standalone-recording default. */
export function useImportUpload() {
  const [phase, setPhase] = useState<ImportUploadPhase>("idle");
  const [row, setRow] = useState<ImportRow | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);

  const start = async (file: File, options: StartOptions) => {
    setError(null);
    setUploadProgress(0);
    setRow(null);
    try {
      setPhase("uploading");
      const ticket = await importsService.create(file.name);
      // Must match the content_type `upload_ref` signed the URL with, see
      // ImportPage's original note — a mismatch fails as a 403 rather than
      // an upload error when a public S3/MinIO endpoint is configured.
      await putToUploadUrl(ticket.upload_url, file, "application/octet-stream", setUploadProgress);
      setPhase("processing");
      const completed = await importsService.complete(ticket.import_id, {
        boat_id: options.boatId,
        activity_id: options.activityId,
        subject_type: options.subjectType,
        subject_user_id: options.subjectUserId,
      });
      setRow(completed);
      if (completed.status === "processed") setPhase("done");
      else if (completed.status === "failed") setPhase("failed");
      return completed;
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : e instanceof Error ? e.message : String(e));
      setPhase("failed");
      throw e;
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

  const reset = () => {
    setPhase("idle");
    setRow(null);
    setError(null);
    setUploadProgress(0);
  };

  return { phase, row, error, uploadProgress, start, reset };
}
