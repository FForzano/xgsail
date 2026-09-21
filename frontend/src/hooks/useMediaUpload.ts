import { useCallback, useState } from "react";
import { putToUploadUrl } from "@/api/media";
import type { UUID } from "@/types";

export type UploadPhase = "idle" | "presigning" | "uploading" | "confirming" | "done" | "error";

/** The uniform presign → PUT → confirm media flow (profile images, boat
 * photos/documents, club/group logos, session photos/videos). The parent
 * endpoint mints the ticket, the confirm endpoint flips it processed. */
export function useMediaUpload({
  create,
  confirm,
  onDone,
}: {
  create: () => Promise<{ upload_url: string } & ({ image_id: UUID } | { file_id: UUID })>;
  confirm: (id: UUID) => Promise<unknown>;
  onDone?: () => void | Promise<void>;
}) {
  const [phase, setPhase] = useState<UploadPhase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);

  const uploadOne = useCallback(
    async (file: File) => {
      const ticket = await create();
      const id = "image_id" in ticket ? ticket.image_id : ticket.file_id;
      setPhase("uploading");
      await putToUploadUrl(ticket.upload_url, file, file.type || undefined);
      setPhase("confirming");
      await confirm(id);
    },
    [create, confirm],
  );

  const upload = useCallback(
    async (file: File) => {
      setError(null);
      try {
        setPhase("presigning");
        await uploadOne(file);
        setPhase("done");
        await onDone?.();
      } catch (e) {
        setPhase("error");
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [uploadOne, onDone],
  );

  // Sequential, not parallel: these are phone photos over a boat-club wifi,
  // and N concurrent presigned PUTs is how you get a stalled upload queue.
  // One failure must not abandon the rest of the batch.
  const uploadMany = useCallback(
    async (files: File[]) => {
      setError(null);
      setProgress({ done: 0, total: files.length });
      let failures = 0;
      // Kept so the caller can tell *why* a batch fell short — a per-session
      // photo cap reads very differently from a flaky connection, and the
      // failure count alone can't say which happened.
      let firstError: unknown = null;
      for (const file of files) {
        try {
          setPhase("presigning");
          await uploadOne(file);
        } catch (e) {
          failures += 1;
          firstError ??= e;
        }
        setProgress((p) => (p ? { done: p.done + 1, total: p.total } : p));
      }
      // Per-file failures are reported via the returned count, not `error` —
      // `error` is what the single-file `upload` callers toast generically on,
      // and a batch's partial-failure message (sessions.photoUploadPartial)
      // is more specific than that.
      setPhase("done");
      setProgress(null);
      await onDone?.();
      return { total: files.length, failed: failures, firstError };
    },
    [uploadOne, onDone],
  );

  return {
    upload,
    uploadMany,
    phase,
    error,
    progress,
    busy: phase !== "idle" && phase !== "done" && phase !== "error",
  };
}
