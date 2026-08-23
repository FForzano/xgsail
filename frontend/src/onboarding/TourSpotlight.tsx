import { useEffect } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import type { Tour } from "@/onboarding/tours";
import { useTourTarget } from "@/onboarding/useTourTarget";
import styles from "./TourSpotlight.module.css";

// Rough bubble dimensions used only for placement math (keeping it from
// overflowing the viewport) — the module's own max-width/max-height still
// govern actual layout, with overflow-y: auto as a hard fallback if a step's
// target is unusually large and the estimate below is wrong.
const BUBBLE_WIDTH = 300;
const BUBBLE_HEIGHT_ESTIMATE = 220;
const GAP = 12;
const PAD = 6;

/** Coachmark overlay for the currently active tour step: dims the page,
 * frames the real target element (found by `data-tour`, see useTourTarget)
 * with four surrounding panels rather than covering it, and anchors a step
 * bubble next to it. Rendered into `document.body` via a portal so it sits
 * above everything regardless of any ancestor's stacking/overflow context. */
export function TourSpotlight({
  tour,
  stepIndex,
  onNext,
  onBack,
  onSkip,
  onStepShown,
}: {
  tour: Tour;
  stepIndex: number;
  onNext: () => void;
  onBack: () => void;
  onSkip: () => void;
  /** Fired once a step's target actually resolved — see OnboardingContext. */
  onStepShown: () => void;
}) {
  const { t } = useTranslation();
  const step = tour.steps[stepIndex];
  const rect = useTourTarget(step.target, onNext);

  useEffect(() => {
    if (rect) onStepShown();
  }, [rect, onStepShown]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onSkip();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onSkip]);

  // Target not (yet) resolved for this step — useTourTarget's own retries
  // will either find it or give up and call onNext itself; nothing to
  // render meanwhile.
  if (!rect) return null;

  const hole = {
    top: rect.top - PAD,
    left: rect.left - PAD,
    width: rect.width + PAD * 2,
    height: rect.height + PAD * 2,
  };

  const viewportW = window.innerWidth;
  const viewportH = window.innerHeight;
  const spaceBelow = viewportH - (hole.top + hole.height);
  const placeAbove = spaceBelow < 180 && hole.top > 180;
  const bubbleLeft = Math.min(Math.max(hole.left, GAP), viewportW - BUBBLE_WIDTH - GAP);
  // Always positioned via `top` (never `bottom`) so it can be clamped
  // uniformly against the viewport regardless of the target's own size —
  // a target much taller than the screen (or right at an edge) must never
  // be able to push the bubble's buttons out of reach. `max-height` +
  // `overflow-y: auto` in the CSS module is the hard backstop if the
  // estimate here is off.
  const desiredTop = placeAbove
    ? hole.top - GAP - BUBBLE_HEIGHT_ESTIMATE
    : hole.top + hole.height + GAP;
  const bubbleTop = Math.min(Math.max(desiredTop, GAP), Math.max(GAP, viewportH - GAP - 80));
  const isLast = stepIndex === tour.steps.length - 1;

  return createPortal(
    <div
      className={styles.root}
      role="dialog"
      aria-modal="true"
      aria-label={t(step.titleKey)}
      // Safety valve: this step's target may end up positioned so the
      // bubble is hard to reach (an unexpectedly large/edge-of-screen
      // target) — tapping anywhere on the dimmed backdrop always advances,
      // so the tour can never trap the user on a step they can't get past.
      // Clicks on the target itself (the "hole", not covered by any mask)
      // reach the real page underneath instead, unaffected by this.
      onClick={onNext}
    >
      <div
        className={styles.mask}
        style={{ top: 0, left: 0, right: 0, height: Math.max(hole.top, 0) }}
      />
      <div
        className={styles.mask}
        style={{ top: hole.top + hole.height, left: 0, right: 0, bottom: 0 }}
      />
      <div
        className={styles.mask}
        style={{ top: hole.top, left: 0, width: Math.max(hole.left, 0), height: hole.height }}
      />
      <div
        className={styles.mask}
        style={{ top: hole.top, left: hole.left + hole.width, right: 0, height: hole.height }}
      />
      <div
        className={styles.highlight}
        style={{ top: hole.top, left: hole.left, width: hole.width, height: hole.height }}
      />
      <div
        className={styles.bubble}
        style={{ top: bubbleTop, left: bubbleLeft }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className={styles.stepCount}>
          {t("onboarding.stepOf", { current: stepIndex + 1, total: tour.steps.length })}
        </div>
        <h3 className={styles.title}>{t(step.titleKey)}</h3>
        <p className={styles.body}>{t(step.bodyKey)}</p>
        <div className={styles.actions}>
          <button type="button" className="sf-btn sf-btn--ghost sf-btn--sm" onClick={onSkip}>
            {t("onboarding.skip")}
          </button>
          <div className={styles.navActions}>
            {stepIndex > 0 && (
              <button type="button" className="sf-btn sf-btn--ghost sf-btn--sm" onClick={onBack}>
                {t("onboarding.back")}
              </button>
            )}
            <button type="button" className="sf-btn sf-btn--sm" onClick={onNext}>
              {isLast ? t("onboarding.done") : t("onboarding.next")}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
