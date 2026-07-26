import { useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { HelpCircle } from "lucide-react";
import { Popover } from "@/components/ui/Popover";
import { tourForPath } from "@/onboarding/tours";
import { useOnboarding } from "@/onboarding/OnboardingContext";
import styles from "./TourHelpButton.module.css";

/** Always-available "?" button to replay a guided tour on demand — the
 * automatic tours in tours.ts only ever fire once per account, so without
 * this there'd be no way back to them once seen/skipped. Offers whichever
 * page-specific tour applies to the current route (if any) plus the app
 * overview, always available as a fallback. Floating rather than per-page so
 * adding a future tour needs no placement decision — it's picked up
 * automatically via `routes` in tours.ts. */
export function TourHelpButton() {
  const { t } = useTranslation();
  const location = useLocation();
  const { requestTour } = useOnboarding();
  const pageTour = tourForPath(location.pathname);

  return (
    <Popover
      panelClassName="sf-optionsmenu__panel sf-options__panel--up"
      title={t("onboarding.help.button")}
      trigger={({ open, toggle }) => (
        <button
          type="button"
          className={styles.button}
          aria-label={t("onboarding.help.button")}
          aria-haspopup="menu"
          aria-expanded={open}
          onClick={toggle}
        >
          <HelpCircle size={20} />
        </button>
      )}
    >
      {({ close }) => (
        <>
          {pageTour && (
            <button
              type="button"
              role="menuitem"
              className="sf-optionsmenu__item"
              onClick={() => {
                requestTour(pageTour.id, { force: true });
                close();
              }}
            >
              {t("onboarding.help.pageTour")}
            </button>
          )}
          <button
            type="button"
            role="menuitem"
            className="sf-optionsmenu__item"
            onClick={() => {
              requestTour("app-overview", { force: true });
              close();
            }}
          >
            {t("onboarding.help.appTour")}
          </button>
        </>
      )}
    </Popover>
  );
}
