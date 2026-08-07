import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "ghost" | "danger";

export function Button({
  variant = "primary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button className={`sf-btn sf-btn--${variant} ${className}`} {...props} />
  );
}

/** Class list for a `<Link>`/`<a>` that must render as an icon-only ghost
 * button — the markup `Button` can't produce, since it renders `<button>`. */
export const ICON_BTN = "sf-btn sf-btn--ghost sf-btn--icon-sm";
