import { useEffect } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import type { Tour } from "@/onboarding/tours";
import { useTourTarget } from "@/onboarding/useTourTarget";
import styles from "./TourSpotlight.module.css";

// Rough bubble width used only to keep it from overflowing the right edge —
// the module's own max-width still governs actual layout.
const BUBBLE_WIDTH = 300;
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
}: {
  tour: Tour;
  stepIndex: number;
  onNext: () => void;
  onBack: () => void;
  onSkip: () => void;
}) {
  const { t } = useTranslation();
  const step = tour.steps[stepIndex];
  const rect = useTourTarget(step.target, onNext);

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
  const isLast = stepIndex === tour.steps.length - 1;

  return createPortal(
    <div className={styles.root} role="dialog" aria-modal="true" aria-label={t(step.titleKey)}>
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
        style={
          placeAbove
            ? { bottom: viewportH - hole.top + GAP, left: bubbleLeft }
            : { top: hole.top + hole.height + GAP, left: bubbleLeft }
        }
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
