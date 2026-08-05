import { api } from "@/api/client";
import { readCache, writeCache } from "@/services/offlineCache";
import type {
  Boat,
  BoatClass,
  BoatMember,
  BoatNote,
  BoatRole,
  BoatSessionNote,
  FileUploadTicket,
  HullType,
  ImageUploadTicket,
  UUID,
} from "@/types";

export type BoatClassSort = "name" | "py_rating" | "crew_size" | "rya_class_id";
export type SortOrder = "asc" | "desc";

export const boatKeys = {
  all: ["boats"] as const,
  mine: ["boats", "mine"] as const,
  search: (q: string) => ["boats", "search", q] as const,
  detail: (id: UUID) => ["boats", id] as const,
  members: (id: UUID) => ["boats", id, "members"] as const,
  notes: (id: UUID) => ["boats", id, "notes"] as const,
  sessionNotes: (id: UUID) => ["boats", id, "session-notes"] as const,
  classes: (
    page = 0,
    search = "",
    hullType: HullType | "" = "",
    sort: BoatClassSort = "name",
    order: SortOrder = "asc",
  ) => ["boat-classes", page, search, hullType, sort, order] as const,
};

const BOATS_MINE_KEY = "boats_mine";
const LAST_BOAT_ID_KEY = "last_boat_id";

/** Last-known "my boats" list, for the recording page in airplane mode. */
export const cachedMyBoats = (): Boat[] | null => readCache<Boat[]>(BOATS_MINE_KEY);

export const rememberLastBoatId = (id: UUID): void => writeCache(LAST_BOAT_ID_KEY, id);
export const lastBoatId = (): UUID | null => readCache<UUID>(LAST_BOAT_ID_KEY);

export const boatsService = {
  list: (mine = false) =>
    api.get<Boat[]>(`/boats${mine ? "?mine=true" : ""}`).then((boats) => {
      if (mine) writeCache(BOATS_MINE_KEY, boats);
      return boats;
    }),
  /** Server-side search for pickers — never pull every boat on the instance. */
  search: (q: string, limit = 20) =>
    api.get<Boat[]>(`/boats?q=${encodeURIComponent(q)}&limit=${limit}`),
  get: (id: UUID) => api.get<Boat>(`/boats/${id}`),
  create: (body: Partial<Boat>) => api.post<Boat>("/boats", body),
  update: (id: UUID, body: Partial<Boat>) => api.patch<Boat>(`/boats/${id}`, body),
  remove: (id: UUID) => api.del(`/boats/${id}`),

  members: (id: UUID) => api.get<BoatMember[]>(`/boats/${id}/members`),
  addMember: (id: UUID, body: { user_id: UUID; role?: BoatRole; default_sailing_role?: string }) =>
    api.post(`/boats/${id}/members`, body),
  setMemberRole: (id: UUID, userId: UUID, role: BoatRole) =>
    api.patch(`/boats/${id}/members/${userId}`, { role }),
  setMemberSailingRole: (id: UUID, userId: UUID, sailingRole: string) =>
    api.patch(`/boats/${id}/members/${userId}`, { default_sailing_role: sailingRole }),
  removeMember: (id: UUID, userId: UUID) => api.del(`/boats/${id}/members/${userId}`),

  notes: (id: UUID) => api.get<BoatNote[]>(`/boats/${id}/notes`),
  createNote: (id: UUID, body: { title: string; body: string }) =>
    api.post<BoatNote>(`/boats/${id}/notes`, body),
  updateNote: (id: UUID, noteId: UUID, body: { title?: string; body?: string }) =>
    api.patch<BoatNote>(`/boats/${id}/notes/${noteId}`, body),
  reorderNotes: (id: UUID, noteIds: UUID[]) =>
    api.patch<BoatNote[]>(`/boats/${id}/notes/order`, { note_ids: noteIds }),
  removeNote: (id: UUID, noteId: UUID) => api.del(`/boats/${id}/notes/${noteId}`),

  sessionNotes: (id: UUID) => api.get<BoatSessionNote[]>(`/boats/${id}/session-notes`),

  createPhoto: (id: UUID) => api.post<ImageUploadTicket>(`/boats/${id}/photos`),
  confirmPhoto: (id: UUID, imageId: UUID) => api.post(`/boats/${id}/photos/${imageId}/confirm`),
  removePhoto: (id: UUID, imageId: UUID) => api.del(`/boats/${id}/photos/${imageId}`),
  uploadCert: (id: UUID) => api.post<FileUploadTicket>(`/boats/${id}/cert`),
  removeCert: (id: UUID) => api.del(`/boats/${id}/cert`),
  uploadMbsa: (id: UUID) => api.post<FileUploadTicket>(`/boats/${id}/mbsa`),
  removeMbsa: (id: UUID) => api.del(`/boats/${id}/mbsa`),

  listClasses: (opts: {
    limit?: number;
    offset?: number;
    search?: string;
    hullType?: HullType | "";
    sort?: BoatClassSort;
    order?: SortOrder;
  } = {}) => {
    const p = new URLSearchParams();
    if (opts.limit) p.set("limit", String(opts.limit));
    if (opts.offset) p.set("offset", String(opts.offset));
    if (opts.search) p.set("search", opts.search);
    if (opts.hullType) p.set("hull_type", opts.hullType);
    if (opts.sort) p.set("sort", opts.sort);
    if (opts.order) p.set("order", opts.order);
    const s = p.toString();
    return api.get<BoatClass[]>(`/boat-classes${s ? `?${s}` : ""}`);
  },
  createClass: (body: Partial<BoatClass>) => api.post<BoatClass>("/boat-classes", body),
  updateClass: (id: UUID, body: Partial<BoatClass>) =>
    api.patch<BoatClass>(`/boat-classes/${id}`, body),
  removeClass: (id: UUID) => api.del(`/boat-classes/${id}`),
  uploadClassLogo: (id: UUID) => api.post<ImageUploadTicket>(`/boat-classes/${id}/logo`),
  confirmClassLogo: (id: UUID, imageId: UUID) =>
    api.post(`/boat-classes/${id}/logo/${imageId}/confirm`),
};
