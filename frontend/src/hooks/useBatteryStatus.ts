import { useEffect, useState } from "react";
import { Capacitor } from "@capacitor/core";
import { Battery } from "@capawesome/capacitor-battery";
import type { PluginListenerHandle } from "@capacitor/core";

export interface BatteryStatus {
  level: number | null; // 0..1, null before the first read (or on web)
  charging: boolean;
  /** Android's power saver / iOS's Low Power Mode. The OS throttles background
   * work and can refuse the wake lock while this is on — worth telling the
   * user rather than leaving the display looking silently broken. Never true
   * on the web: no such concept there. */
  lowPowerMode: boolean;
}

const EMPTY: BatteryStatus = { level: null, charging: false, lowPowerMode: false };

/** Phone battery level and power-save state, for navigation mode's status
 * strip — a sailor watching this screen for hours wants to know if the phone
 * itself will make it, and whether the OS's own power saving might already be
 * working against the wake lock. Native only. Event-driven: the plugin only
 * observes the device while a listener is attached, so this costs nothing
 * once unmounted. */
export function useBatteryStatus(): BatteryStatus {
  const [status, setStatus] = useState<BatteryStatus>(EMPTY);

  useEffect(() => {
    if (!Capacitor.isNativePlatform()) return;
    let cancelled = false;
    const handles: Promise<PluginListenerHandle>[] = [];

    void Promise.all([
      Battery.getBatteryLevel().catch(() => ({ level: null as number | null })),
      Battery.getBatteryState().catch(() => ({ state: "unknown" as const })),
      Battery.isLowPowerModeEnabled().catch(() => ({ enabled: false })),
    ]).then(([{ level }, { state }, { enabled }]) => {
      if (!cancelled) setStatus({ level, charging: state === "charging" || state === "full", lowPowerMode: enabled });
    });

    handles.push(
      Battery.addListener("batteryLevelChange", ({ level }) => setStatus((s) => ({ ...s, level }))),
      Battery.addListener("batteryStateChange", ({ state }) =>
        setStatus((s) => ({ ...s, charging: state === "charging" || state === "full" })),
      ),
      Battery.addListener("lowPowerModeChange", ({ enabled }) => setStatus((s) => ({ ...s, lowPowerMode: enabled }))),
    );

    return () => {
      cancelled = true;
      void Promise.all(handles).then((hs) => hs.forEach((h) => void h.remove()));
    };
  }, []);

  return status;
}
