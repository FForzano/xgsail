import { api } from "@/api/client";
import type { UserProgress } from "@/types";

export const progressKeys = {
  me: (year?: number) => ["progress", "me", year ?? "current"] as const,
};

function qs(params: Record<string, string | number | undefined>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined) p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

export const progressService = {
  me: (params?: { year?: number; tz_offset_minutes?: number }) =>
    api.get<UserProgress>(
      `/users/me/progress${qs({
        year: params?.year,
        tz_offset_minutes: params?.tz_offset_minutes,
      })}`,
    ),
};
