import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useReducer,
  useState,
  type ReactNode,
} from "react";
import { useAuth } from "@/hooks/useAuth";
import { authService } from "@/services/auth";
import { getTour, type Tour } from "@/onboarding/tours";
import { TourSpotlight } from "@/onboarding/TourSpotlight";

interface QueuedTour {
  id: string;
  priority: number;
}

interface RunnerState {
  activeTourId: string | null;
  activeStepIndex: number;
  queue: QueuedTour[];
}

const INITIAL_STATE: RunnerState = { activeTourId: null, activeStepIndex: 0, queue: [] };

type Action =
  | { type: "REQUEST"; id: string; priority: number; force?: boolean }
  | { type: "STEP"; delta: 1 | -1 }
  | { type: "FINISH_ACTIVE" };

// All queue/active-tour transitions go through one reducer so "insert into
// the queue, then promote it if nothing's active" happens as a single
// atomic state update — juggling that across several independent useState
// setters is exactly the kind of race this is meant to avoid.
function reducer(state: RunnerState, action: Action): RunnerState {
  switch (action.type) {
    case "REQUEST": {
      if (action.force) {
        return { activeTourId: action.id, activeStepIndex: 0, queue: [] };
      }
      if (state.activeTourId === action.id || state.queue.some((q) => q.id === action.id)) {
        return state;
      }
      if (state.activeTourId === null) {
        return { ...state, activeTourId: action.id, activeStepIndex: 0 };
      }
      const queue = [...state.queue, { id: action.id, priority: action.priority }].sort(
        (a, b) => a.priority - b.priority,
      );
      return { ...state, queue };
    }
    case "STEP":
      return { ...state, activeStepIndex: Math.max(0, state.activeStepIndex + action.delta) };
    case "FINISH_ACTIVE": {
      const [head, ...rest] = state.queue;
      return head
        ? { activeTourId: head.id, activeStepIndex: 0, queue: rest }
        : { activeTourId: null, activeStepIndex: 0, queue: [] };
    }
    default:
      return state;
  }
}

export interface OnboardingContextValue {
  activeTour: Tour | null;
  activeStepIndex: number;
  /** Queues a tour to run automatically (no-op if already seen/queued/
   * active). Pass `force: true` to replay it on demand regardless of
   * "seen" state — interrupts whatever's active immediately, since that
   * only happens from a deliberate user click (the help button). */
  requestTour: (id: string, opts?: { force?: boolean }) => void;
  next: () => void;
  back: () => void;
  skip: () => void;
}

const OnboardingContext = createContext<OnboardingContextValue | null>(null);

export function useOnboarding() {
  const ctx = useContext(OnboardingContext);
  if (!ctx) throw new Error("useOnboarding outside OnboardingProvider");
  return ctx;
}

export function OnboardingProvider({ children }: { children: ReactNode }) {
  const { caps, user } = useAuth();
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE);
  // Optimistic overlay on top of `caps.onboarding.seenTours` — avoids
  // waiting on a full capabilities refetch just to stop a just-finished
  // tour from firing again on the next requestTour() call this session.
  const [seenOverride, setSeenOverride] = useState<Set<string>>(new Set());

  const seenTours = useMemo(
    () => new Set([...(caps?.onboarding.seenTours ?? []), ...seenOverride]),
    [caps?.onboarding.seenTours, seenOverride],
  );

  const activeTour = state.activeTourId ? getTour(state.activeTourId) ?? null : null;

  const markSeen = useCallback((id: string) => {
    setSeenOverride((prev) => new Set(prev).add(id));
    // Fire-and-forget: the tour is already dismissed client-side; a failed
    // request just means it might replay once more on another device.
    void authService.markOnboardingSeen(id);
  }, []);

  const requestTour = useCallback(
    (id: string, opts?: { force?: boolean }) => {
      const tour = getTour(id);
      if (!tour) return;
      if (!opts?.force && (!user || seenTours.has(id))) return;
      dispatch({ type: "REQUEST", id, priority: tour.priority, force: opts?.force });
    },
    [user, seenTours],
  );

  const finishActive = useCallback(() => {
    if (!state.activeTourId) return;
    markSeen(state.activeTourId);
    dispatch({ type: "FINISH_ACTIVE" });
  }, [state.activeTourId, markSeen]);

  const next = useCallback(() => {
    if (!activeTour) return;
    if (state.activeStepIndex < activeTour.steps.length - 1) {
      dispatch({ type: "STEP", delta: 1 });
    } else {
      finishActive();
    }
  }, [activeTour, state.activeStepIndex, finishActive]);

  const back = useCallback(() => dispatch({ type: "STEP", delta: -1 }), []);

  const skip = useCallback(() => finishActive(), [finishActive]);

  const value = useMemo<OnboardingContextValue>(
    () => ({
      activeTour,
      activeStepIndex: state.activeStepIndex,
      requestTour,
      next,
      back,
      skip,
    }),
    [activeTour, state.activeStepIndex, requestTour, next, back, skip],
  );

  return (
    <OnboardingContext.Provider value={value}>
      {children}
      {activeTour && (
        <TourSpotlight
          tour={activeTour}
          stepIndex={state.activeStepIndex}
          onNext={next}
          onBack={back}
          onSkip={skip}
        />
      )}
    </OnboardingContext.Provider>
  );
}
