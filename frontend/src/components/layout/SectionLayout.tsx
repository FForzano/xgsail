import { NavLink, Outlet } from "react-router-dom";
import type { ReactNode } from "react";

export interface SectionTab {
  to: string;
  label: string;
  end?: boolean;
}

/** Macro-section layout: sub-page tabs (real routes, not UI tabs) + outlet.
 * `header` renders above the tabs on every sub-page of the section (used by
 * Gruppi for the shared invites/discovery strip). */
export function SectionLayout({ tabs, header }: { tabs: SectionTab[]; header?: ReactNode }) {
  return (
    <div className="sf-section">
      {header}
      <nav className="sf-tabs" aria-label="Section">
        {tabs.map((tab) => (
          <NavLink key={tab.to} to={tab.to} end={tab.end} className="sf-tab">
            {tab.label}
          </NavLink>
        ))}
      </nav>
      <div className="sf-section__body">
        <Outlet />
      </div>
    </div>
  );
}
