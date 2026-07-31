import { useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

export interface ComboboxOption {
  id: string;
  /** What goes in the input once picked, and what a11y reads out. */
  label: string;
  /** Optional richer row content; falls back to `label`. */
  render?: ReactNode;
}

/** Type-to-filter picker for lists too long for a <select>.
 *
 * Filtering is the caller's job, not this component's: `ClassPicker` narrows an
 * already-loaded catalog in memory, while `BoatPicker` issues a debounced
 * server query. Both need the same open/blur/keyboard behaviour, which is what
 * lives here. */
export function Combobox({
  id,
  label,
  options,
  query,
  onQueryChange,
  onPick,
  selectedLabel,
  emptyOption,
  emptyMessage,
  placeholder,
  disabled,
  autoFocus,
}: {
  id: string;
  label: string;
  options: ComboboxOption[];
  query: string;
  onQueryChange: (q: string) => void;
  onPick: (id: string) => void;
  selectedLabel?: string;
  /** Row that clears the selection (e.g. "no class"); omitted when absent. */
  emptyOption?: { label: string; value: string };
  emptyMessage: string;
  placeholder?: string;
  disabled?: boolean;
  /** Focus on mount — for callers that swap a summary card for this picker. */
  autoFocus?: boolean;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => setActive(0), [options]);

  useEffect(() => {
    if (autoFocus) inputRef.current?.focus();
  }, [autoFocus]);

  const pick = (value: string) => {
    onPick(value);
    onQueryChange("");
    setOpen(false);
    inputRef.current?.blur();
  };

  const rows = emptyOption
    ? [{ id: emptyOption.value, label: emptyOption.label }, ...options]
    : options;

  return (
    <div className="sf-field sf-combobox">
      <span className="sf-field__label">{label}</span>
      <input
        ref={inputRef}
        id={id}
        className="sf-field__input"
        autoComplete="off"
        role="combobox"
        aria-expanded={open}
        aria-controls={`${id}-list`}
        disabled={disabled}
        value={open ? query : (selectedLabel ?? "")}
        placeholder={placeholder ?? t("common.search")}
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          onQueryChange(e.target.value);
          setOpen(true);
        }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setActive((i) => Math.min(i + 1, rows.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((i) => Math.max(i - 1, 0));
          } else if (e.key === "Enter" && open && rows[active]) {
            e.preventDefault();
            pick(rows[active].id);
          } else if (e.key === "Escape") {
            setOpen(false);
          }
        }}
        // Delay so a click on an option (which blurs the input first) still registers.
        onBlur={() => setTimeout(() => setOpen(false), 150)}
      />
      {open && (
        <div className="sf-combobox__list" id={`${id}-list`} role="listbox">
          {rows.length === 0 && (
            <div className="sf-combobox__option sf-muted">{emptyMessage}</div>
          )}
          {rows.map((o, i) => (
            <div
              key={o.id}
              role="option"
              aria-selected={i === active}
              className={`sf-combobox__option${i === active ? " sf-combobox__option--active" : ""}`}
              onMouseEnter={() => setActive(i)}
              onMouseDown={() => pick(o.id)}
            >
              {o.render ?? o.label}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
