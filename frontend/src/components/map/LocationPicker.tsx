import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Crosshair, Search } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { InputField } from "@/components/ui/InputField";
import { Spinner } from "@/components/ui/Spinner";
import { addressToQuery, geocodeQuery, type AddressParts } from "@/services/geocoding";
import { ExplorerMap } from "./ExplorerMap";
import styles from "./LocationPicker.module.css";

/** Picks a lat/lng on a map, from a typed address or the current position.
 *
 * The address is an editable field rather than the surrounding form's stored
 * fields: a club record keeps a city, not a street, so geocoding those fields
 * alone can only ever land on the city centre — which reads as "it ignored me
 * and used my position". Typing the real address is what makes the pin land on
 * the clubhouse.
 *
 * The lookup is an explicit button, never automatic — Nominatim's usage policy
 * forbids querying on every keystroke (see services/geocoding). */
export function LocationPicker({
  value,
  address,
  onChange,
}: {
  value: { lat: number; lng: number } | null;
  /** Address fields from the surrounding form; seed the search box. */
  address?: AddressParts;
  onChange: (position: { lat: number; lng: number } | null) => void;
}) {
  const { t, i18n } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [found, setFound] = useState<string | null>(null);
  const [query, setQuery] = useState(() => addressToQuery(address ?? {}));
  // Only set from a lookup: panning the map by hand must not fight
  // ExplorerMap's own view state.
  const [center, setCenter] = useState<{ lat: number; lng: number } | null>(value);

  const pick = (position: { lat: number; lng: number }, label: string | null) => {
    onChange(position);
    setCenter(position);
    setFound(label);
  };

  const findFromAddress = async () => {
    setBusy(true);
    setError(null);
    setFound(null);
    try {
      const hit = await geocodeQuery(query, i18n.language);
      if (!hit) {
        setError(t("gruppi.addressNotFound"));
        return;
      }
      pick({ lat: hit.lat, lng: hit.lng }, hit.displayName);
    } catch {
      setError(t("errors.generic"));
    } finally {
      setBusy(false);
    }
  };

  const useMyPosition = () => {
    if (!navigator.geolocation) {
      setError(t("map.locateError"));
      return;
    }
    setBusy(true);
    setError(null);
    setFound(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setBusy(false);
        pick({ lat: pos.coords.latitude, lng: pos.coords.longitude }, null);
      },
      () => {
        setBusy(false);
        setError(t("map.locateError"));
      },
      { enableHighAccuracy: true, timeout: 10000 },
    );
  };

  return (
    <div className={styles.picker}>
      <span className="sf-field__label">{t("gruppi.clubLocation")}</span>
      <p className="sf-muted">{t("gruppi.clubLocationHint")}</p>
      <InputField
        label={t("gruppi.addressQuery")}
        id="location-address"
        value={query}
        placeholder={t("gruppi.addressQueryPlaceholder")}
        onChange={(e) => setQuery(e.target.value)}
        // Inside a <form>: Enter here means "search", not "submit the club".
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            void findFromAddress();
          }
        }}
      />
      <div className={styles.row}>
        <Button
          type="button"
          variant="ghost"
          onClick={() => void findFromAddress()}
          disabled={busy || !query.trim()}
        >
          {busy ? <Spinner inline /> : <Search size={16} strokeWidth={1.75} />}{" "}
          {t("gruppi.findFromAddress")}
        </Button>
        <Button type="button" variant="ghost" onClick={useMyPosition} disabled={busy}>
          <Crosshair size={16} strokeWidth={1.75} /> {t("gruppi.useMyPosition")}
        </Button>
      </div>
      <ExplorerMap
        className={styles.map}
        center={center}
        zoom={center ? 16 : undefined}
        marker={value}
        onPick={(lat, lng) => {
          onChange({ lat, lng });
          setFound(null);
        }}
      />
      <div className={styles.row}>
        {value ? (
          <>
            <span className="sf-muted">
              {value.lat.toFixed(5)}, {value.lng.toFixed(5)}
            </span>
            <Button type="button" variant="ghost" onClick={() => onChange(null)}>
              {t("common.remove")}
            </Button>
          </>
        ) : (
          <span className="sf-muted">{t("gruppi.noLocation")}</span>
        )}
      </div>
      {found && <p className="sf-muted">{found}</p>}
      {error && <p className="sf-form__error">{error}</p>}
    </div>
  );
}
