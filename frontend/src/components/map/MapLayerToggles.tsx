import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Layers } from "lucide-react";
import { Button } from "@/components/ui/Button";
import type { MapLayers } from "./useMapLayers";
import styles from "./MapLayerToggles.module.css";

/** The map's overlay switcher: a single button that opens a small checkbox
 * panel. Rendered inside whatever floating slot the host map provides (see
 * MapView's `mapOptions` corner and ExplorerMap), so the same control serves
 * every map — no Leaflet `L.control.layers`, which wouldn't match the app's
 * own overlay styling. */
export function MapLayerToggles({
  layers,
  onToggle,
  detailHidden = false,
  poiHidden = false,
}: {
  layers: MapLayers;
  onToggle: (key: keyof MapLayers, on: boolean) => void;
  /** True when a zoom-gated layer is switched on but the map is zoomed too
   * far out to draw it — without a word here the checkbox looks broken. */
  detailHidden?: boolean;
  /** Same, for the POI layer, which has its own higher threshold (see
   * useNauticalPoi's POI_MIN_ZOOM) — a separate hint because the two
   * thresholds are different numbers for different reasons, so one merged
   * message would be wrong at every zoom between them. */
  poiHidden?: boolean;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const entries: Array<keyof MapLayers> = ["seamark", "poi", "clubs", "stations"];

  return (
    <div className={styles.wrap}>
      <Button
        type="button"
        className="sf-btn--icon"
        variant="ghost"
        data-tour="map-layers"
        aria-label={t("map.layers.title")}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <Layers size={18} strokeWidth={1.75} />
      </Button>
      {open && (
        <div className={styles.panel}>
          {entries.map((key) => (
            <label key={key} className={styles.option}>
              <input
                type="checkbox"
                checked={layers[key]}
                onChange={(e) => onToggle(key, e.target.checked)}
              />
              {t(`map.layers.${key}`)}
            </label>
          ))}
          {detailHidden && <p className={styles.hint}>{t("map.layers.zoomIn")}</p>}
          {poiHidden && <p className={styles.hint}>{t("map.layers.zoomInPoi")}</p>}
        </div>
      )}
    </div>
  );
}
