import { api } from "@/api/client";
import type { ImportRow, ImportTicket, UUID } from "@/types";

export const importKeys = {
  all: ["imports"] as const,
  detail: (id: UUID) => ["imports", id] as const,
};

export const importsService = {
  /** Step 1: register the import → PUT the file bytes to `upload_url`. */
  create: (original_filename: string) => api.post<ImportTicket>("/imports", { original_filename }),

  /** Step 2: bind to a boat and start processing. */
  complete: (
    id: UUID,
    body: {
      boat_id: UUID;
      activity_id?: UUID;
      session_id?: UUID;
      subject_type?: "boat" | "crew_member";
      subject_user_id?: UUID;
      started_at?: string;
    },
  ) => api.post<ImportRow>(`/imports/${id}/complete`, body),

  list: () => api.get<ImportRow[]>("/imports"),
  get: (id: UUID) => api.get<ImportRow>(`/imports/${id}`),
};
