// Shared date/number formatters (timezone-safe: full timestamps go through
// Date, bare YYYY-MM-DD dates are noon-anchored so they don't shift a day).

export function fmtDate(date?: string | null): string {
  if (!date) return "—";
  const d = date.length === 10 ? new Date(date + "T12:00:00") : new Date(date);
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function fmtDateTime(ts?: string | null): string {
  if (!ts) return "—";
  return new Date(ts).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function fmtTime(ms: number): string {
  return new Date(ms).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function fmtDuration(sec?: number | null): string {
  if (!sec) return "—";
  const m = Math.round(sec / 60);
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

export function fmtDistance(m?: number | null): string {
  if (m == null) return "—";
  const nm = m / 1852;
  return nm >= 10 ? `${nm.toFixed(1)} nm` : `${nm.toFixed(2)} nm`;
}

export function fmtKnots(k?: number | null): string {
  return k == null ? "—" : `${k.toFixed(1)} kn`;
}

export function userLabel(u?: { first_name?: string | null; last_name?: string | null; email?: string } | null): string {
  if (!u) return "—";
  const name = [u.first_name, u.last_name].filter(Boolean).join(" ");
  return name || u.email || "—";
}
