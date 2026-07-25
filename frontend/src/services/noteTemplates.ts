import { api } from "@/api/client";
import type { NoteTemplate, UUID } from "@/types";

export const noteTemplateKeys = {
  mine: ["note-templates", "mine"] as const,
};

export const noteTemplatesService = {
  listMine: () => api.get<NoteTemplate[]>("/note-templates"),
  create: (body: { name: string; body: string }) =>
    api.post<NoteTemplate>("/note-templates", body),
  update: (id: UUID, body: { name?: string; body?: string }) =>
    api.patch<NoteTemplate>(`/note-templates/${id}`, body),
  remove: (id: UUID) => api.del(`/note-templates/${id}`),
};
