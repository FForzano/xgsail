import { useTranslation } from "react-i18next";
import { E1_DISPLAY_MODES, e1DisplayModeSrc, type E1DisplayMode } from "./e1DisplayModes";
import styles from "./DisplayModePicker.module.css";

export function DisplayModePicker({
  value,
  onChange,
}: {
  value: E1DisplayMode;
  onChange: (mode: E1DisplayMode) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="sf-field">
      <span className="sf-field__label">{t("devices.e1.config.displayMode")}</span>
      <div className={styles.grid} role="radiogroup" aria-label={t("devices.e1.config.displayMode")}>
        {E1_DISPLAY_MODES.map((mode) => (
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
              src={e1DisplayModeSrc(mode)}
              alt={t(`devices.e1.config.displayModes.${mode}`)}
            />
            <span className={styles.label}>{t(`devices.e1.config.displayModes.${mode}`)}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
