import { useState } from "react";
import { useTranslation } from "react-i18next";
import { MapPin } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { geocodeAddress, type AddressParts } from "@/services/geocoding";
import { ExplorerMap } from "./ExplorerMap";
import styles from "./LocationPicker.module.css";

/** Picks a lat/lng on a map, optionally seeded from a typed address.
 *
 * The address lookup is an explicit button, never automatic — Nominatim's
 * usage policy forbids querying on every keystroke (see services/geocoding). */
export function LocationPicker({
  value,
  address,
  onChange,
}: {
  value: { lat: number; lng: number } | null;
  /** Address fields from the surrounding form, used by "find from address". */
  address?: AddressParts;
  onChange: (position: { lat: number; lng: number } | null) => void;
}) {
  const { t, i18n } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Only set from a geocoding result: panning the map by hand must not fight
  // ExplorerMap's own view state.
  const [center, setCenter] = useState<{ lat: number; lng: number } | null>(value);

  const findFromAddress = async () => {
    setBusy(true);
    setError(null);
    try {
      const hit = await geocodeAddress(address ?? {}, i18n.language);
      if (!hit) {
        setError(t("gruppi.addressNotFound"));
        return;
      }
      onChange({ lat: hit.lat, lng: hit.lng });
      setCenter({ lat: hit.lat, lng: hit.lng });
    } catch {
      setError(t("errors.generic"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={styles.picker}>
      <span className="sf-field__label">{t("gruppi.clubLocation")}</span>
      <p className="sf-muted">{t("gruppi.clubLocationHint")}</p>
      <ExplorerMap
        className={styles.map}
        center={center}
        zoom={center ? 14 : undefined}
        marker={value}
        onPick={(lat, lng) => onChange({ lat, lng })}
      />
      <div className={styles.row}>
        <Button type="button" variant="ghost" onClick={() => void findFromAddress()} disabled={busy}>
          {busy ? <Spinner inline /> : <MapPin size={16} strokeWidth={1.75} />}{" "}
          {t("gruppi.findFromAddress")}
        </Button>
        {value && (
          <>
            <span className="sf-muted">
              {value.lat.toFixed(5)}, {value.lng.toFixed(5)}
            </span>
            <Button type="button" variant="ghost" onClick={() => onChange(null)}>
              {t("common.remove")}
            </Button>
          </>
        )}
      </div>
      {error && <p className="sf-form__error">{error}</p>}
    </div>
  );
}
