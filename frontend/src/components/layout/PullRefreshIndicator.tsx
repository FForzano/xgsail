import { usePullRefreshState } from "@/contexts/PullRefreshContext";
import { PULL_TRIGGER_PX } from "@/hooks/useAppShellGestures";
import { Spinner } from "@/components/ui/Spinner";

/** Renders the pull-to-refresh reveal strip — see SectionLayout, which
 * places it right after the sticky tab bar so pulling down grows a gap
 * below "Le mie attività"/"Circoli e gruppi" (etc.) instead of pushing that
 * bar down from above it. No-op wherever PullRefreshProvider isn't an
 * ancestor (e.g. pages outside AppShell). */
export function PullRefreshIndicator() {
  const state = usePullRefreshState();
  if (!state) return null;
  const { pull, refreshing } = state;
  return (
    <div
      className="sf-pull-refresh"
      style={{ height: refreshing ? PULL_TRIGGER_PX : pull, opacity: Math.min(pull / PULL_TRIGGER_PX, 1) }}
      aria-hidden={!refreshing}
    >
      <Spinner inline />
    </div>
  );
}
