import { useEffect, useState } from "react";
import { resolveApiUrl } from "@/api/client";
import type { SessionStream } from "@/types";

// A session's processed series live in object storage, not in the API response:
// `GET /sessions/:id/streams` hands back a `download_url` per stream and the
// caller fetches the JSON itself. This hook is that fetch — plain `fetch` with
// cancellation, deliberately not a TanStack query, since the URL is presigned
// and short-lived so there is nothing worth caching under a stable key.
//
// `null` means "still resolving", `[]` means "resolved to nothing" — whether
// because no such stream exists or because the fetch failed. Callers gate their
// spinner on `null`, so conflating the two would spin forever on a session that
// simply has no track.
export function useStreamJson<T>(
  streams: SessionStream[] | undefined,
  sensorType: string,
  subjectUserId?: string | null,
): T[] | null {
  const stream = streams?.find(
    (s) =>
      s.sensor_type === sensorType &&
      !!s.download_url &&
      // A session can carry the same sensor for several people (one heart-rate
      // stream per crew member) — without this the first one always wins.
      (subjectUserId === undefined || s.subject_user_id === subjectUserId),
  );
  const url = stream?.download_url ?? null;
  const [data, setData] = useState<T[] | null>(null);

  useEffect(() => {
    if (!url) {
      // Resolved: there is no such stream. Not `null`, which would read as
      // "still loading" forever.
      setData(streams === undefined ? null : []);
      return;
    }
    let cancelled = false;
    setData(null);
    void fetch(resolveApiUrl(url))
      .then((r) => (r.ok ? r.json() : []))
      .then((points: T[]) => {
        if (!cancelled) setData(points);
      })
      .catch(() => {
        if (!cancelled) setData([]);
      });
    return () => {
      cancelled = true;
    };
  }, [url, streams === undefined]);

  return data;
}
