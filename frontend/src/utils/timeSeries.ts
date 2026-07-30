// Shared primitive for "what was the value at the playback cursor?".
//
// Every time series in the app answers that question, and each one used to
// carry its own copy of the same binary search (raceModel's indexAt on GPS
// fixes, vmgSeries' vmgAt on the VMG series). This is that search, once.
//
// `timeOf` reads the comparable time out of an element rather than the caller
// building a parallel array of times: this runs on every cursor move, so it
// must not allocate. Units are the caller's — just be consistent between
// `timeOf` and `target`.
//
// Returns the index of the last element at or before `target`, or -1 when the
// series is empty or starts after it — deliberately not the nearest element,
// because extrapolating off the front of a series would invent a reading from
// before the recording began.
export function lastIndexAtOrBefore<T>(
  items: readonly T[],
  target: number,
  timeOf: (item: T) => number,
): number {
  if (!items.length || target < timeOf(items[0])) return -1;
  let lo = 0;
  let hi = items.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (timeOf(items[mid]) <= target) lo = mid;
    else hi = mid - 1;
  }
  return lo;
}
