import { useSyncExternalStore } from "react";

// Whether the full-screen navigation display is currently up
// (components/registra/NavModeOverlay.tsx). AppShell reads it to suspend the
// background work that has no business running mid-race — the periodic E1 BLE
// scan, the Apple Watch relay, the swipe/pull gestures.
//
// Session-only, deliberately NOT persisted like unitsStore: navigation mode
// must never survive an app restart, or a user who force-quit mid-session
// would reopen the app into a full-screen instrument with no recording behind
// it.

class NavModeStore {
  private on = false;
  private listeners = new Set<() => void>();

  subscribe = (fn: () => void) => {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  };
  getSnapshot = () => this.on;

  get(): boolean {
    return this.on;
  }

  set(on: boolean) {
    if (this.on === on) return;
    this.on = on;
    this.listeners.forEach((l) => l());
  }
}

export const navModeStore = new NavModeStore();

export function useNavMode(): boolean {
  return useSyncExternalStore(navModeStore.subscribe, navModeStore.getSnapshot);
}
