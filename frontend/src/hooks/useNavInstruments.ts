import { useEffect, useState } from "react";
import { useLiveState } from "@/services/liveFix";
import { useWindAt } from "@/hooks/useWindAt";
import { roundCoord } from "@/utils/geo";
import { tackOf, trueWindAngle, vmg, type Tack } from "@/utils/nav";

// The one composition point for navigation mode's numbers: live GPS + the
// wind lookup + the sailing math, so the display components stay dumb and
// none of this is recomputed per tile. See components/registra/.

// No fix for this long and the readout is stale, not slow — the boat may have
// gone under a bridge, below deck, or the OS may have throttled the watcher.
const FIX_TIMEOUT_MS = 10_000;

const ACCURACY_GOOD_M = 10;
const ACCURACY_FAIR_M = 25;

export type GpsQuality = "good" | "fair" | "poor" | "lost";

export interface NavInstruments {
  sogKts: number | null;
  cogDeg: number | null;
  /** True wind, from the backend's nearest station/model — never a masthead
   * sensor. Null wherever there's no coverage, which is normal offshore. */
  twdDeg: number | null;
  twsKts: number | null;
  gustKts: number | null;
  /** Signed, positive = wind on the starboard bow. Null without both a wind
   * direction and a believable course. */
  twaDeg: number | null;
  tack: Tack | null;
  vmgKts: number | null;
  windSource: string | null;
  windAgeMin: number | null;
  distanceM: number;
  maxSogKts: number;
  avgSogKts: number;
  accuracyM: number | null;
  gpsQuality: GpsQuality;
}

function gpsQualityOf(accuracyM: number | null, fixAt: number | null, now: number): GpsQuality {
  if (fixAt == null || now - fixAt > FIX_TIMEOUT_MS) return "lost";
  if (accuracyM == null) return "fair";
  if (accuracyM <= ACCURACY_GOOD_M) return "good";
  if (accuracyM <= ACCURACY_FAIR_M) return "fair";
  return "poor";
}

export function useNavInstruments(): NavInstruments {
  const { fix, distanceM, maxSogKts, avgSogKts } = useLiveState();

  // "Lost" has to become true from the passage of time alone, with no new fix
  // arriving to trigger a render — hence a tick of its own. 1 Hz, matching the
  // rest of the display.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  // Coordinates are coarsened to ~1 km: without this the query key changes on
  // every fix and the wind endpoint gets hit once a second.
  const { data: wind } = useWindAt(
    fix ? roundCoord(fix.lat) : undefined,
    fix ? roundCoord(fix.lon) : undefined,
  );

  const twdDeg = wind?.twd_deg ?? null;
  const twaDeg = twdDeg != null && fix?.cogDeg != null ? trueWindAngle(fix.cogDeg, twdDeg) : null;

  return {
    sogKts: fix?.sogKts ?? null,
    cogDeg: fix?.cogDeg ?? null,
    twdDeg,
    twsKts: wind?.tws_kts ?? null,
    gustKts: wind?.gust_kts ?? null,
    twaDeg,
    tack: twaDeg == null ? null : tackOf(twaDeg),
    vmgKts: twaDeg != null && fix?.sogKts != null ? vmg(fix.sogKts, twaDeg) : null,
    windSource: wind ? (wind.station_name ?? wind.model ?? wind.provider) : null,
    windAgeMin: wind ? Math.max(0, Math.round((now - Date.parse(wind.observed_at)) / 60_000)) : null,
    distanceM,
    maxSogKts,
    avgSogKts,
    accuracyM: fix?.accuracyM ?? null,
    gpsQuality: gpsQualityOf(fix?.accuracyM ?? null, fix?.at ?? null, now),
  };
}
