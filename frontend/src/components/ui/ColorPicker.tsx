import styles from "./ColorPicker.module.css";

/** A row of preset swatches plus a free `<input type="color">`. Kept as a UI
 * primitive rather than inline in the share modal so any other "pick a color"
 * spot (overlay styling, future export presets) reuses the same control. */
export function ColorPicker({
  label,
  value,
  presets,
  onChange,
}: {
  label: string;
  value: string;
  presets: string[];
  onChange: (color: string) => void;
}) {
  return (
    <div className={styles.picker}>
      <span className="sf-field__label">{label}</span>
      <div className={styles.swatches}>
        {presets.map((c) => (
          <button
            key={c}
            type="button"
            aria-label={c}
            aria-pressed={value.toLowerCase() === c.toLowerCase()}
            className={`${styles.swatch} ${value.toLowerCase() === c.toLowerCase() ? styles.selected : ""}`}
            style={{ background: c }}
            onClick={() => onChange(c)}
          />
        ))}
        <input
          type="color"
          className={styles.custom}
          value={value}
          aria-label={label}
          onChange={(e) => onChange(e.target.value)}
        />
      </div>
    </div>
  );
}
