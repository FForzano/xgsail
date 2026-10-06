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
 * between them, the page tour is always the default.
 *
 * It lives in the app's chrome, never on top of a page's content: in the
 * navbar on desktop, at the end of the section tab bar on a phone. Only a
 * phone screen with no tab bar (Registra's map, race and regatta pages)
 * falls back to the floating button. Still never a per-page decision — a
 * new tour is picked up automatically via `routes` in tours.ts. */
export function TourHelpButton({ placement = "floating" }: { placement?: "floating" | "navbar" | "tabs" }) {
  const { t } = useTranslation();
  const location = useLocation();
  const { requestTour } = useOnboarding();
  const pageTour = tourForPath(location.pathname);

  return (
    <button
      type="button"
      className={`${styles.button} ${styles[placement]}`}
      aria-label={t("onboarding.help.button")}
      // A page tour runs in place: the user pressed "?" while looking at a
      // real activity/club/boat, so its steps' demo-entity `route`s must not
      // navigate them away from it. The `getting-started` fallback is meant
      // to walk across sections, so it keeps its routes.
      onClick={() =>
        pageTour
          ? requestTour(pageTour.id, { force: true, inPlace: true })
          : requestTour("getting-started", { force: true })
      }
    >
      <HelpCircle size={placement === "floating" ? 20 : 18} />
    </button>
  );
}
