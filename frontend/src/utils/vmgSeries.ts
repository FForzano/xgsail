import type { VmgPoint } from "@/types";
import { lastIndexAtOrBefore } from "./timeSeries";

// Nearest VMG-series sample at or before `ms`. The series is worker-native
// (timestamps in seconds), the cursor is in ms — hence the conversion.
export function vmgAt(series: VmgPoint[] | null | undefined, ms: number): VmgPoint | null {
  if (!series?.length) return null;
  const idx = lastIndexAtOrBefore(series, ms / 1000, (p) => p.timestamp);
  return idx < 0 ? null : series[idx];
}
