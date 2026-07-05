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

  const upload = useCallback(
    async (file: File) => {
      setError(null);
      try {
        setPhase("presigning");
        const ticket = await create();
        const id = "image_id" in ticket ? ticket.image_id : ticket.file_id;
        setPhase("uploading");
        await putToUploadUrl(ticket.upload_url, file, file.type || undefined);
        setPhase("confirming");
        await confirm(id);
        setPhase("done");
        await onDone?.();
      } catch (e) {
        setPhase("error");
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [create, confirm, onDone],
  );

  return { upload, phase, error, busy: phase !== "idle" && phase !== "done" && phase !== "error" };
}
