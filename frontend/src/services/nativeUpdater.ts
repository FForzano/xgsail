import { Capacitor } from "@capacitor/core";
import { CapacitorUpdater } from "@capgo/capacitor-updater";

// After applying an OTA bundle, @capgo/capacitor-updater waits for the app
// to call notifyAppReady() within its readiness timeout; if that call never
// comes, it assumes the new bundle crashed/hung and automatically reverts
// to the previous one (the builtin bundle, the first time this ever runs)
// — silently, mid-session once the timeout elapses. We were never calling
// it, so every OTA update was rolling itself back regardless of whether it
// actually worked. The web bundle never imports this module (see
// contexts/AuthContext.tsx's nativeAuth for the same pattern).
export async function notifyNativeAppReady(): Promise<void> {
  if (!Capacitor.isNativePlatform()) return;
  await CapacitorUpdater.notifyAppReady();
}
