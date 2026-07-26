import { useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { HelpCircle } from "lucide-react";
import { tourForPath } from "@/onboarding/tours";
import { useOnboarding } from "@/onboarding/OnboardingContext";
import styles from "./TourHelpButton.module.css";

/** Always-available "?" button to replay a guided tour on demand — the
 * automatic tours in tours.ts only ever fire once per account, so without
 * this there'd be no way back to them once seen/skipped. Directly (re)starts
 * whichever page-specific tour applies to the current route, falling back to
 * the app overview on pages with no dedicated tour — no menu to choose
 * between them, the page tour is always the default. Floating rather than
 * per-page so adding a future tour needs no placement decision — it's picked
 * up automatically via `routes` in tours.ts. */
export function TourHelpButton() {
  const { t } = useTranslation();
  const location = useLocation();
  const { requestTour } = useOnboarding();
  const pageTour = tourForPath(location.pathname);

  return (
    <button
      type="button"
      className={styles.button}
      aria-label={t("onboarding.help.button")}
      onClick={() => requestTour(pageTour?.id ?? "getting-started", { force: true })}
    >
      <HelpCircle size={20} />
    </button>
  );
}
