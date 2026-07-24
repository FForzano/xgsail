import { useTranslation } from "react-i18next";
import styles from "./DisplayModePicker.module.css";

const DISPLAY_MODES = [1, 2, 3] as const;

const PREVIEW_SRC: Record<(typeof DISPLAY_MODES)[number], string> = {
  1: "/devices/e1-display-modes/d1.png",
  2: "/devices/e1-display-modes/d2.png",
  3: "/devices/e1-display-modes/d3.png",
};

export function DisplayModePicker({
  value,
  onChange,
}: {
  value: 1 | 2 | 3;
  onChange: (mode: 1 | 2 | 3) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="sf-field">
      <span className="sf-field__label">{t("devices.e1.config.displayMode")}</span>
      <div className={styles.grid} role="radiogroup" aria-label={t("devices.e1.config.displayMode")}>
        {DISPLAY_MODES.map((mode) => (
          <button
            key={mode}
            type="button"
            role="radio"
            aria-checked={value === mode}
            className={`${styles.option} ${value === mode ? styles.optionSelected : ""}`}
            onClick={() => onChange(mode)}
          >
            <img
              className={styles.preview}
              src={PREVIEW_SRC[mode]}
              alt={t(`devices.e1.config.displayModes.${mode}`)}
            />
            <span className={styles.label}>{t(`devices.e1.config.displayModes.${mode}`)}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
