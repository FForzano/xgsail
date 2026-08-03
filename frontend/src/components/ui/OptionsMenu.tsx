import { MoreVertical } from "lucide-react";
import { Popover } from "@/components/ui/Popover";

export interface OptionsMenuItem {
  label: string;
  onClick: () => void;
  danger?: boolean;
  disabled?: boolean;
}

/** Generic "⋮" options menu — a small anchored dropdown of action items.
 * Reused wherever a card/row needs more actions than fit as inline buttons. */
export function OptionsMenu({
  items,
  triggerDataTour,
}: {
  items: OptionsMenuItem[];
  /** `data-tour` anchor for the trigger button, for callers whose menu is a
   * guided-tour step target (e.g. the diario "importa" action). */
  triggerDataTour?: string;
}) {
  return (
    <Popover
      panelClassName="sf-optionsmenu__panel"
      trigger={({ open, toggle }) => (
        <button
          data-tour={triggerDataTour}
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
        items.map((it, i) => (
          <button
            key={i}
            type="button"
            role="menuitem"
            disabled={it.disabled}
            className={`sf-optionsmenu__item ${it.danger ? "sf-optionsmenu__item--danger" : ""}`}
            onClick={() => {
              close();
              it.onClick();
            }}
          >
            {it.label}
          </button>
        ))
      }
    </Popover>
  );
}
