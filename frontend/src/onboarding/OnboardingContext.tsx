import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";
import { authService } from "@/services/auth";
import { getTour, tourForPath, type Tour } from "@/onboarding/tours";
import { TourSpotlight } from "@/onboarding/TourSpotlight";

interface QueuedTour {
  id: string;
  priority: number;
  /** Carried per queued tour, not inherited from whatever ran before it. */
  inPlace: boolean;
}

interface RunnerState {
  activeTourId: string | null;
  activeStepIndex: number;
  /** The active run ignores every step's `route` — see `requestTour`. */
  activeInPlace: boolean;
  queue: QueuedTour[];
}

const INITIAL_STATE: RunnerState = {
  activeTourId: null,
  activeStepIndex: 0,
  activeInPlace: false,
  queue: [],
};

type Action =
  | { type: "REQUEST"; id: string; priority: number; force?: boolean; inPlace?: boolean; auto?: boolean }
  | { type: "STEP"; delta: 1 | -1 }
  | { type: "FINISH_ACTIVE" };

// All queue/active-tour transitions go through one reducer so "insert into
// the queue, then promote it if nothing's active" happens as a single
// atomic state update — juggling that across several independent useState
// setters is exactly the kind of race this is meant to avoid.
function reducer(state: RunnerState, action: Action): RunnerState {
  switch (action.type) {
    case "REQUEST": {
      const inPlace = action.inPlace ?? false;
      if (action.force) {
        return { activeTourId: action.id, activeStepIndex: 0, activeInPlace: inPlace, queue: [] };
      }
      if (state.activeTourId === action.id || state.queue.some((q) => q.id === action.id)) {
        return state;
      }
      // A first-visit auto-start never queues: `getting-started` navigates
      // through the very pages that have their own page tours, and the
      // pathname it lands on must not stack a second tour behind it. The
      // check lives here rather than in the effect because the reducer is
      // the only place that sees the state a same-flush REQUEST just set.
      if (action.auto && (state.activeTourId !== null || state.queue.length > 0)) {
        return state;
      }
      if (state.activeTourId === null) {
        return { ...state, activeTourId: action.id, activeStepIndex: 0, activeInPlace: inPlace };
      }
      const queue = [...state.queue, { id: action.id, priority: action.priority, inPlace }].sort(
        (a, b) => a.priority - b.priority,
      );
      return { ...state, queue };
    }
    case "STEP":
      return { ...state, activeStepIndex: Math.max(0, state.activeStepIndex + action.delta) };
    case "FINISH_ACTIVE": {
      const [head, ...rest] = state.queue;
      return head
        ? { activeTourId: head.id, activeStepIndex: 0, activeInPlace: head.inPlace, queue: rest }
        : INITIAL_STATE;
    }
    default:
      return state;
  }
}

export interface OnboardingContextValue {
  activeTour: Tour | null;
  activeStepIndex: number;
  /** `data-tour` target of the step currently being shown, or null when no
   * tour is active. Lets a page decide to render a demo stand-in for an empty
   * state only while that specific step is on screen (see `isDemoTarget`). */
  activeStepTarget: string | null;
  /** True when a tour step is currently pointing at `target` — the cue a page
   * uses to swap its empty state for a highlighted demo element carrying the
   * same `data-tour`, so the step has something real to frame. */
  isDemoTarget: (target: string) => boolean;
  /** Queues a tour to run automatically (no-op if already seen/queued/
   * active). Pass `force: true` to replay it on demand regardless of
   * "seen" state — interrupts whatever's active immediately, since that
   * only happens from a deliberate user click (the help button). Pass
   * `inPlace: true` to run it on whatever page the user is already on: every
   * step's `route` is ignored for the whole run, so a tour pointing at a demo
   * entity runs against the real one the user is looking at instead. */
  requestTour: (id: string, opts?: { force?: boolean; inPlace?: boolean }) => void;
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
  const navigate = useNavigate();
  const { pathname } = useLocation();
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
  const activeStep = activeTour?.steps[state.activeStepIndex] ?? null;
  const activeStepTarget = activeStep?.target ?? null;

  // A step can declare the route it lives on; when the tour reaches it and the
  // app is elsewhere, navigate there first. TourSpotlight/useTourTarget then
  // resolve the target on the newly-mounted page (their own retries absorb the
  // mount delay). An in-place run skips this entirely — see `requestTour`.
  useEffect(() => {
    if (state.activeInPlace) return;
    const target = activeStep?.route;
    if (target && target !== pathname) navigate(target);
  }, [state.activeInPlace, activeStep?.route, pathname, navigate]);

  const markSeen = useCallback((id: string) => {
    setSeenOverride((prev) => new Set(prev).add(id));
    // Fire-and-forget: the tour is already dismissed client-side; a failed
    // request just means it might replay once more on another device.
    void authService.markOnboardingSeen(id);
  }, []);

  // `auto` is deliberately absent from the context's public signature: it's
  // the runner's own first-visit path (see the effect below), not something a
  // page should be able to ask for.
  const requestTour = useCallback(
    (id: string, opts?: { force?: boolean; inPlace?: boolean; auto?: boolean }) => {
      const tour = getTour(id);
      if (!tour) return;
      if (!opts?.force && (!user || seenTours.has(id))) return;
      dispatch({
        type: "REQUEST",
        id,
        priority: tour.priority,
        force: opts?.force,
        inPlace: opts?.inPlace,
        auto: opts?.auto,
      });
    },
    [user, seenTours],
  );

  // Each page tour also fires the first time the user lands on its page, once
  // per account (the `seenTours` check above makes every later visit a no-op),
  // and stays replayable from the "?" button. Keyed on the resolved tour, not
  // on the pathname, so moving between two routes of the same section
  // (/diario/personale → /diario/circoli) doesn't re-request anything.
  const lastAutoTourId = useRef<string | null>(null);
  useEffect(() => {
    // Nothing auto-starts for an anonymous user, and `seenTours` isn't
    // trustworthy until capabilities have loaded — firing before then would
    // replay a tour the account already dismissed.
    if (!user || !caps) return;
    const tour = tourForPath(pathname);
    if (tour?.id === lastAutoTourId.current) return;
    lastAutoTourId.current = tour?.id ?? null;
    // Always in place: an auto-start fires *because* the user just landed on
    // the tour's own page, so navigating anywhere — least of all to the demo
    // entity an entity-scoped tour points at — would yank them off the real
    // record they were looking at. Step routes stay for explicitly requested
    // tours, which is how a user with no data of their own reaches the demo.
    if (tour) requestTour(tour.id, { auto: true, inPlace: true });
  }, [user, caps, pathname, requestTour]);

  // A tour's `routes` are prefixes, so it can auto-start somewhere none of its
  // steps exist — /profilo/barche/{id}/quaderno matches the boat tour, say. It
  // then runs to the end showing nothing and would mark itself seen, silently
  // spending the one automatic run the account gets. Only count it as seen
  // once the user has actually been shown a step.
  const anyStepShown = useRef(false);
  const onStepShown = useCallback(() => {
    anyStepShown.current = true;
  }, []);

  const finishActive = useCallback(() => {
    if (!state.activeTourId) return;
    if (anyStepShown.current) markSeen(state.activeTourId);
    anyStepShown.current = false;
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

  const isDemoTarget = useCallback(
    (target: string) => activeStepTarget === target,
    [activeStepTarget],
  );

  const value = useMemo<OnboardingContextValue>(
    () => ({
      activeTour,
      activeStepIndex: state.activeStepIndex,
      activeStepTarget,
      isDemoTarget,
      requestTour,
      next,
      back,
      skip,
    }),
    [activeTour, state.activeStepIndex, activeStepTarget, isDemoTarget, requestTour, next, back, skip],
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
          onStepShown={onStepShown}
        />
      )}
    </OnboardingContext.Provider>
  );
}
