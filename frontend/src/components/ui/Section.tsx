import type { ReactNode } from "react";

/** Flat page-level block: heading + optional actions + content, with none of
 * `Card`'s chrome (border, surface, radius, inset). Detail pages are a stack
 * of these, so `Card` stays reserved for the innermost discrete entity — one
 * boat, one mark, one entry — instead of boxing a whole page region that then
 * boxes its items again, which on a phone costs most of the usable width.
 * Classes use the `sf-block` prefix because `.sf-section` in global.css is
 * already taken by the macro-page (SectionLayout) grid. */
export function Section({
  title,
  actions,
  children,
  className = "",
}: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`sf-block ${className}`}>
      {(title || actions) && (
        <div className="sf-block__head">
          {title && <h2 className="sf-block__title">{title}</h2>}
          {actions && <div className="sf-block__actions">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}
