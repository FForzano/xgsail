import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ListFilter } from "lucide-react";
import { Popover } from "@/components/ui/Popover";
import { OptionsMenu } from "@/components/ui/OptionsMenu";
import type { ActivityType } from "@/types";
import styles from "./DiaryToolbar.module.css";

const TYPES: (ActivityType | "")[] = ["", "race", "training", "solo"];

/** Compact header row for a diario tab: a filter popover (replaces the old
 * full labeled `<Select>`, which took as much space as the whole feed
 * card) and, only on the "Personale" tab, an options menu for "Importa" —
 * kept as a menu rather than a bare button so more per-tab actions can land
 * there later without another layout change. */
export function DiaryToolbar({
  type,
  onTypeChange,
  importHref,
}: {
  type: string;
  onTypeChange: (value: string) => void;
  importHref?: string;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <div className={styles.toolbar}>
      <Popover
        panelClassName="sf-optionsmenu__panel"
        trigger={({ open, toggle }) => (
          <button
            className={`sf-btn sf-btn--ghost sf-btn--sm ${styles.filterTrigger}`}
            aria-haspopup="menu"
            aria-expanded={open}
            onClick={toggle}
          >
            <ListFilter size={15} />
            {type ? t(`activities.types.${type}`) : t("activities.type")}
          </button>
        )}
      >
        {({ close }) =>
          TYPES.map((v) => (
            <button
              key={v || "all"}
              type="button"
              role="menuitemradio"
              aria-checked={type === v}
              className={`sf-optionsmenu__item ${type === v ? "sf-optionsmenu__item--active" : ""}`}
              onClick={() => {
                onTypeChange(v);
                close();
              }}
            >
              {v ? t(`activities.types.${v}`) : t("common.none")}
            </button>
          ))
        }
      </Popover>
      {importHref && (
        <OptionsMenu items={[{ label: t("sessions.import"), onClick: () => navigate(importHref) }]} />
      )}
    </div>
  );
}
