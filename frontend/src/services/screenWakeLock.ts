import { Capacitor } from "@capacitor/core";
import { App as CapacitorApp } from "@capacitor/app";
import { KeepAwake } from "@capacitor-community/keep-awake";
import type { PluginListenerHandle } from "@capacitor/core";

// Keeps the screen on while navigation mode is up. An instrument display that
// blanks after 30 seconds is not an instrument.
//
// Two backends, tried in order:
//  1. @capacitor-community/keep-awake — a real OS-level "stay on" flag
//     (Android's FLAG_KEEP_SCREEN_ON / iOS's isIdleTimerDisabled). Reliable
//     everywhere, including iOS < 16.4, but only reaches users once this ships
//     in a native build (a new native plugin can't go out over this app's
//     JS-only @capgo/capacitor-updater OTA channel).
//  2. The W3C Screen Wake Lock API — covers the same ground on Android
//     WebView (Chrome 84+) and iOS 16.4+ TODAY, over OTA, so the feature isn't
//     stuck behind a store release while waiting for #1 to reach everyone.
//
// Both are behind the same acquire()/release() pair below; nothing else in
// the app needs to know which one is actually holding the lock.

let usingPlugin = false;
let sentinel: WakeLockSentinel | null = null;
let appListener: PluginListenerHandle | null = null;
let held = false; // intent, as opposed to whether a lock is held right now

export function isSupported(): boolean {
  return Capacitor.isNativePlatform() || (typeof navigator !== "undefined" && "wakeLock" in navigator);
}

async function requestWebLock(): Promise<boolean> {
  if (!("wakeLock" in navigator) || sentinel) return sentinel != null;
  try {
    sentinel = await navigator.wakeLock.request("screen");
    // The OS can drop the lock on its own (power-save kicking in); forget the
    // stale sentinel so the next re-acquire attempt actually re-requests.
    sentinel.addEventListener("release", () => {
      sentinel = null;
    });
    return true;
  } catch {
    // Rejects when the document isn't visible, or when the OS refuses
    // (battery saver). Not an error worth surfacing — reacquire() will try
    // again on the next resume.
    return false;
  }
}

// Only the web-lock path needs this: it's a per-tab sentinel that both
// Chrome and WebKit release whenever the page is hidden and never take back
// by themselves. Without re-acquiring here, the screen starts sleeping again
// the first time the user glances at a notification — exactly when a sailor
// stops watching and assumes it still works. The native plugin sets a
// persistent OS-level flag instead, so it needs no such dance.
function reacquire() {
  if (held && !usingPlugin && document.visibilityState === "visible") void requestWebLock();
}

/** Requests the lock and keeps it across backgrounding. Returns false when
 * neither backend is available, so the UI can warn once. */
export async function acquire(): Promise<boolean> {
  held = true;

  if (Capacitor.isNativePlatform()) {
    try {
      const { isSupported: pluginSupported } = await KeepAwake.isSupported();
      if (pluginSupported) {
        await KeepAwake.keepAwake();
        usingPlugin = true;
        return true;
      }
    } catch {
      // fall through to the web API below
    }
  }

  usingPlugin = false;
  if (!isSupported()) return false;
  document.addEventListener("visibilitychange", reacquire);
  appListener = await CapacitorApp.addListener("appStateChange", ({ isActive }) => {
    if (isActive) reacquire();
  });
  return requestWebLock();
}

export async function release(): Promise<void> {
  held = false;

  if (usingPlugin) {
    usingPlugin = false;
    try {
      await KeepAwake.allowSleep();
    } catch {
      // nothing to release
    }
    return;
  }

  document.removeEventListener("visibilitychange", reacquire);
  await appListener?.remove();
  appListener = null;
  try {
    await sentinel?.release();
  } catch {
    // already released by the OS
  }
  sentinel = null;
}
