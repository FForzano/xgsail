import { useRef, type KeyboardEvent, type ReactNode } from "react";

export interface TabItem {
  id: string;
  label: ReactNode;
  /** `data-tour` anchor, for a guided-tour step about what this tab holds. */
  dataTour?: string;
}

export const tabId = (prefix: string, id: string) => `${prefix}-tab-${id}`;
export const tabPanelId = (prefix: string, id: string) => `${prefix}-panel-${id}`;

/** In-page tabs (UI state, not routes — those are SectionLayout's NavLinks)
 * in the ARIA tabs pattern: one tab in the Tab order, arrow keys move and
 * select. The caller renders the matching panel with `role="tabpanel"`,
 * `id={tabPanelId(...)}` and `aria-labelledby={tabId(...)}`. Uses the
 * section tab look (`.sf-tabs`/`.sf-tab`). */
export function TabList({
  tabs,
  active,
  onChange,
  label,
  idPrefix,
  className = "",
}: {
  tabs: TabItem[];
  active: string;
  onChange: (id: string) => void;
  label: string;
  idPrefix: string;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const onKeyDown = (e: KeyboardEvent) => {
    const i = tabs.findIndex((tab) => tab.id === active);
    const next =
      e.key === "ArrowRight" ? (i + 1) % tabs.length
      : e.key === "ArrowLeft" ? (i - 1 + tabs.length) % tabs.length
      : e.key === "Home" ? 0
      : e.key === "End" ? tabs.length - 1
      : null;
    if (next == null) return;
    e.preventDefault();
    onChange(tabs[next].id);
    ref.current?.querySelector<HTMLElement>(`#${tabId(idPrefix, tabs[next].id)}`)?.focus();
  };

  return (
    <div ref={ref} role="tablist" aria-label={label} className={`sf-tabs ${className}`} onKeyDown={onKeyDown}>
      {tabs.map((tab) => {
        const selected = tab.id === active;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            id={tabId(idPrefix, tab.id)}
            aria-selected={selected}
            aria-controls={tabPanelId(idPrefix, tab.id)}
            tabIndex={selected ? 0 : -1}
            data-tour={tab.dataTour}
            className={`sf-tab${selected ? " active" : ""}`}
            onClick={() => onChange(tab.id)}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
