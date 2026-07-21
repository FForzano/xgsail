import { createContext, useContext } from "react";

export interface PullRefreshState {
  pull: number;
  refreshing: boolean;
}

/** Shares AppShell's pull-to-refresh state (from useAppShellGestures, whose
 * touch handling lives on `.sf-main`) with SectionLayout, so the reveal strip
 * can render below the section's own tab bar ("Le mie attività" / "Circoli
 * e gruppi" etc.) instead of pushing it down from above. `null` outside
 * AppShell (there is no pull-to-refresh state to read). */
const PullRefreshContext = createContext<PullRefreshState | null>(null);

export const PullRefreshProvider = PullRefreshContext.Provider;

export function usePullRefreshState(): PullRefreshState | null {
  return useContext(PullRefreshContext);
}
