import { NavLink, Outlet } from "react-router-dom";
import type { ReactNode } from "react";

export interface SectionTab {
  to: string;
  label: string;
  end?: boolean;
  /** Small count pill on the tab (e.g. pending join requests) — omitted
   * when 0/undefined. */
  badge?: number;
}

/** Macro-section layout: sub-page tabs (real routes, not UI tabs) + outlet.
 * `header` renders below the tabs, above the outlet, on every sub-page of
 * the section (used by Gruppi for the shared invites/discovery strip) —
 * the tabs come first so they're the first scrollable element and can
 * stick to the top immediately (see `.sf-tabs` in global.css), rather than
 * a variable-height header transiting under a device notch/status bar
 * while it scrolls out of view. `footer` renders below the outlet (used by
 * Profilo for the mobile-only logout button). */
export function SectionLayout({
  tabs,
  header,
  footer,
  context,
  sticky = true,
}: {
  tabs: SectionTab[];
  header?: ReactNode;
  footer?: ReactNode;
  /** Forwarded to the internal `<Outlet>` — read by child routes via
   * `useOutletContext()` (e.g. club sub-pages reading clubId/permissions
   * from `ClubDetailLayout`). */
  context?: unknown;
  /** Set false for a SectionLayout nested inside another one (e.g. club
   * sub-tabs inside Gruppi/Circoli) — only the outermost tab bar should
   * pin to the viewport top on mobile. */
  sticky?: boolean;
}) {
  return (
    <div className="sf-section">
      <nav className={`sf-tabs${sticky ? "" : " sf-tabs--static"}`} aria-label="Section">
        {tabs.map((tab) => (
          <NavLink key={tab.to} to={tab.to} end={tab.end} className="sf-tab">
            {tab.label}
            {!!tab.badge && <span className="sf-tab__badge">{tab.badge}</span>}
          </NavLink>
        ))}
      </nav>
      {header}
      <div className="sf-section__body">
        <Outlet context={context} />
      </div>
      {footer}
    </div>
  );
}
