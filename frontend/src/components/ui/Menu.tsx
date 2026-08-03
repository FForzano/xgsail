import { useState } from "react";
import { MoreVertical } from "lucide-react";
import { Popover } from "@/components/ui/Popover";
import styles from "./Menu.module.css";

export interface MenuItem {
  label: string;
  onClick?: () => void;
  danger?: boolean;
  disabled?: boolean;
  /** Renders as a checkbox row instead of a button. */
  checked?: boolean;
  onCheckedChange?: (v: boolean) => void;
  /** Present → renders as an accordion row: click expands this item's own
   * sub-items in-place (indented, directly below), instead of firing
   * `onClick`. Nests to any depth (e.g. "Mostra su mappa" > "Andature" >
   * per-type checkboxes) — each level indents a bit further. */
  children?: MenuItem[];
}

export interface MenuSection {
  /** Bold section label with a divider above — omit for an unheaded group
   * (e.g. a single trailing danger item). */
  heading?: string;
  items: MenuItem[];
}

function MenuRow({ item, depth }: { item: MenuItem; depth: number }) {
  const [expanded, setExpanded] = useState(false);
  // Each nesting level indents a bit further (base padding + depth step).
  const indentStyle = depth > 0 ? { paddingLeft: `${0.6 + depth * 0.9}rem` } : undefined;

  if (item.children) {
    return (
      <>
        <button
          type="button"
          role="menuitem"
          aria-expanded={expanded}
          disabled={item.disabled}
          className={styles.item}
          style={indentStyle}
          onClick={() => setExpanded((v) => !v)}
        >
          <span>{item.label}</span>
          <span className={styles.chevron}>{expanded ? "▾" : "▸"}</span>
        </button>
        {expanded &&
          item.children.map((child, i) => (
            <MenuRow key={i} item={child} depth={depth + 1} />
          ))}
      </>
    );
  }

  if (item.onCheckedChange) {
    return (
      <label className={`sf-check ${styles.item}`} style={indentStyle}>
        <input
          type="checkbox"
          checked={!!item.checked}
          disabled={item.disabled}
          onChange={(e) => item.onCheckedChange?.(e.target.checked)}
        />
        <span>{item.label}</span>
      </label>
    );
  }

  return (
    <button
      type="button"
      role="menuitem"
      disabled={item.disabled}
      className={`${styles.item} ${item.danger ? styles.itemDanger : ""}`}
      style={indentStyle}
      onClick={item.onClick}
    >
      {item.label}
    </button>
  );
}

/** Consolidated "⋮" action menu: grouped sections (optional bold heading +
 * divider) of buttons, checkboxes, or one-level accordion sub-items —
 * replaces the flat `OptionsMenu` for pages that outgrew a single list
 * (session detail: session actions, track actions incl. trim, per-type map
 * display toggles, delete). */
export function Menu({ sections }: { sections: MenuSection[] }) {
  return (
    <Popover
      panelClassName={styles.panel}
      trigger={({ open, toggle }) => (
        <button
          className="sf-btn sf-btn--ghost sf-btn--icon-sm"
          aria-label="Options"
          aria-haspopup="menu"
          aria-expanded={open}
          onClick={toggle}
        >
          <MoreVertical size={16} />
        </button>
      )}
    >
      {({ close }) =>
        sections.map((section, i) => (
          <div key={i} className={styles.section}>
            {section.heading && <div className={styles.heading}>{section.heading}</div>}
            {section.items.map((item, j) => (
              <MenuRow
                key={j}
                depth={0}
                item={{
                  ...item,
                  onClick: item.onClick && (() => {
                    close();
                    item.onClick?.();
                  }),
                }}
              />
            ))}
          </div>
        ))
      }
    </Popover>
  );
}
