import type { ReactNode } from "react";

export function Card({
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
    <section className={`sf-card ${className}`}>
      {(title || actions) && (
        <div className="sf-card__head">
          {title && <h2 className="sf-card__title">{title}</h2>}
          {actions && <div className="sf-card__actions">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}
