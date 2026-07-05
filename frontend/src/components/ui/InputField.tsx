import type { InputHTMLAttributes, TextareaHTMLAttributes } from "react";

export function InputField({
  label,
  id,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string; id: string }) {
  return (
    <label className="sf-field" htmlFor={id}>
      <span className="sf-field__label">{label}</span>
      <input id={id} className="sf-field__input" {...props} />
    </label>
  );
}

export function TextAreaField({
  label,
  id,
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string; id: string }) {
  return (
    <label className="sf-field" htmlFor={id}>
      <span className="sf-field__label">{label}</span>
      <textarea id={id} className="sf-field__input" rows={3} {...props} />
    </label>
  );
}
