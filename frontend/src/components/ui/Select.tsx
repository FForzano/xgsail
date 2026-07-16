import type { SelectHTMLAttributes } from "react";

export function Select({
  label,
  id,
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & { label: string; id: string }) {
  return (
    <label className="sf-field" htmlFor={id}>
      <span className="sf-field__label">{label}</span>
      <select id={id} className="sf-field__input sf-select" {...props}>
        {children}
      </select>
    </label>
  );
}
