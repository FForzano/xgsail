import { useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Info } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { InputField } from "@/components/ui/InputField";
import { Select } from "@/components/ui/Select";
import { Spinner } from "@/components/ui/Spinner";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useE1Device } from "@/hooks/useE1Device";
import { ConfigWriteError } from "@/services/nativeBle";
import type { CalibrateResult, E1ConfigPatch, E1WifiNetwork } from "@/services/nativeBle";
import { fmtDuration } from "@/utils/format";
import type { Device } from "@/types";
import { E1InfoDialog } from "./E1InfoDialog";
import styles from "./E1DevicePanel.module.css";

const UNIT_ROLES = ["racing_boat", "rc_signal", "rc_pin", "mark", "committee_chase", "spare"] as const;
const MAX_WIFI = 5;

function writeErrorMessage(t: (key: string) => string, err: unknown): string {
  if (err instanceof ConfigWriteError) return t(`devices.e1.config.error.${err.reason}`);
  return err instanceof Error ? err.message : t("errors.generic");
}

export function E1DevicePanel({ device }: { device: Device }) {
  const { t } = useTranslation();
  const e1 = useE1Device(device);
  const [wifi, setWifi] = useState<E1WifiNetwork[]>([]);
  const [boatId, setBoatId] = useState("");
  const [unitRole, setUnitRole] = useState<string>("racing_boat");
  const [apiBaseUrl, setApiBaseUrl] = useState("");
  const [windMac, setWindMac] = useState("");
  const [windOffset, setWindOffset] = useState(0);
  const [rtkEnabled, setRtkEnabled] = useState(false);
  const [autoCleanupUploads, setAutoCleanupUploads] = useState(true);
  const [calibResult, setCalibResult] = useState<CalibrateResult | null>(null);
  const [confirmingCalibrate, setConfirmingCalibrate] = useState(false);
  const [configError, setConfigError] = useState<string | null>(null);
  const [configSaved, setConfigSaved] = useState(false);
  const [infoOpen, setInfoOpen] = useState(false);

  useEffect(() => {
    if (!e1.config) return;
    setWifi(e1.config.wifi);
    setBoatId(e1.config.boat_id);
    setUnitRole(e1.config.unit_role);
    setApiBaseUrl(e1.config.api_base_url);
    setWindMac(e1.config.wind_mac);
    setWindOffset(e1.config.wind_offset);
    setRtkEnabled(e1.config.rtk_enabled);
    setAutoCleanupUploads(e1.config.auto_cleanup_uploads);
  }, [e1.config]);

  if (e1.state === "unsupported") return null;

  const infoButton = (
    <Button variant="ghost" className="sf-btn--sm" onClick={() => setInfoOpen(true)}>
      <Info size={16} strokeWidth={2} /> {t("devices.e1.info.button")}
    </Button>
  );
  const infoDialog = infoOpen && <E1InfoDialog onClose={() => setInfoOpen(false)} />;

  if (e1.state === "searching") {
    return (
      <>
        <Card title={t("devices.e1.title")} actions={infoButton}>
          <Spinner />
          <p className="sf-muted">{t("devices.e1.searching")}</p>
        </Card>
        {infoDialog}
      </>
    );
  }

  if (e1.state === "unreachable") {
    return (
      <>
        <Card title={t("devices.e1.title")} actions={infoButton}>
          <p className="sf-muted">{t("devices.e1.unreachable")}</p>
          <div className="sf-form__actions">
            <Button variant="ghost" onClick={e1.retry}>
              {t("common.retry")}
            </Button>
          </div>
        </Card>
        {infoDialog}
      </>
    );
  }

  const s = e1.status;

  const submitConfig = (e: FormEvent) => {
    e.preventDefault();
    setConfigError(null);
    setConfigSaved(false);
    const patch: E1ConfigPatch = {
      wifi,
      boat_id: boatId,
      unit_role: unitRole as E1ConfigPatch["unit_role"],
      api_base_url: apiBaseUrl,
      wind_mac: windMac,
      wind_offset: windOffset,
      rtk_enabled: rtkEnabled,
      auto_cleanup_uploads: autoCleanupUploads,
    };
    e1.writeConfig.mutate(patch, {
      onSuccess: () => setConfigSaved(true),
      onError: (err) => setConfigError(writeErrorMessage(t, err)),
    });
  };

  const updateWifi = (index: number, patch: Partial<E1WifiNetwork>) => {
    setWifi((prev) => prev.map((w, i) => (i === index ? { ...w, ...patch } : w)));
  };

  return (
    <>
      <Card title={t("devices.e1.status.title")} actions={infoButton}>
        {e1.statusLoading && !s ? (
          <Spinner />
        ) : !s ? (
          <p className="sf-muted">{t("devices.e1.unreachable")}</p>
        ) : (
          <div className={styles.statusGrid}>
            <div className={styles.statusItem}>
              <span className="sf-field__label">{t("devices.battery")}</span>
              <span>
                {s.battery.pct}% ({s.battery.v} V)
                {s.battery.critical && <span className="sf-badge sf-badge--danger">{t("devices.e1.status.criticalBattery")}</span>}
              </span>
            </div>
            <div className={styles.statusItem}>
              <span className="sf-field__label">{t("devices.e1.status.gps")}</span>
              <span>
                {s.gps.fix
                  ? `${t("devices.e1.status.satellites", { count: s.gps.satellites })} · HDOP ${s.gps.hdop} · ${s.gps.speed_kts} kt`
                  : t("devices.e1.status.noFix")}
              </span>
            </div>
            <div className={styles.statusItem}>
              <span className="sf-field__label">WiFi</span>
              <span>{s.wifi.connected ? `${s.wifi.ssid} (${s.wifi.ip})` : t("devices.e1.status.disconnected")}</span>
            </div>
            <div className={styles.statusItem}>
              <span className="sf-field__label">{t("devices.e1.status.sensors")}</span>
              <span>
                IMU {s.sensors.imu ? "✓" : "✗"} · {t("devices.e1.status.pressure")} {s.sensors.pressure ? "✓" : "✗"} ·{" "}
                {t("devices.e1.status.wind")} {s.sensors.wind ? "✓" : "✗"}
              </span>
            </div>
            {s.wind.connected && (
              <div className={styles.statusItem}>
                <span className="sf-field__label">{t("devices.e1.status.windLive")}</span>
                <span>
                  {s.wind.speed_kts} kt · {s.wind.angle_deg}°
                </span>
              </div>
            )}
            <div className={styles.statusItem}>
              <span className="sf-field__label">{t("devices.e1.status.recording")}</span>
              <span>
                {s.recording.logging
                  ? `${t("devices.e1.status.logging")} (${fmtDuration(s.recording.elapsed_s)})`
                  : t("devices.e1.status.idle")}{" "}
                · {t("devices.e1.status.pendingUploads", { count: s.recording.pending_uploads })}
              </span>
            </div>
            <div className={styles.statusItem}>
              <span className="sf-field__label">{t("devices.firmware")}</span>
              <span>{s.firmware_version}</span>
            </div>
            <div className={styles.statusItem}>
              <span className="sf-field__label">{t("devices.uptime")}</span>
              <span>{fmtDuration(s.uptime_s)}</span>
            </div>
          </div>
        )}
      </Card>

      <Card title={t("devices.e1.config.title")}>
        <p className="sf-muted">{t("devices.e1.config.pairingHint")}</p>
        <form onSubmit={submitConfig}>
          {wifi.map((w, i) => (
            <div key={i} className={styles.wifiRow}>
              <div className={styles.wifiField}>
                <InputField
                  label={t("devices.e1.config.wifiSsid")}
                  id={`e1-wifi-ssid-${i}`}
                  value={w.ssid}
                  onChange={(e) => updateWifi(i, { ssid: e.target.value })}
                />
              </div>
              <div className={styles.wifiField}>
                <InputField
                  label={t("devices.e1.config.wifiPass")}
                  id={`e1-wifi-pass-${i}`}
                  type="password"
                  placeholder={t("devices.e1.config.wifiPassUnchanged")}
                  value={w.pass}
                  onChange={(e) => updateWifi(i, { pass: e.target.value })}
                />
              </div>
              <Button
                type="button"
                variant="ghost"
                className="sf-btn--sm"
                onClick={() => setWifi((prev) => prev.filter((_, idx) => idx !== i))}
              >
                {t("common.remove")}
              </Button>
            </div>
          ))}
          {wifi.length < MAX_WIFI && (
            <Button
              type="button"
              variant="ghost"
              className="sf-btn--sm"
              onClick={() => setWifi((prev) => [...prev, { ssid: "", pass: "" }])}
            >
              {t("devices.e1.config.addWifi")}
            </Button>
          )}

          <InputField
            label={t("devices.e1.config.apiBaseUrl")}
            id="e1-api-base-url"
            value={apiBaseUrl}
            onChange={(e) => setApiBaseUrl(e.target.value)}
          />
          <InputField
            label={t("devices.e1.config.boatIdLabel")}
            id="e1-boat-id"
            value={boatId}
            maxLength={15}
            onChange={(e) => setBoatId(e.target.value)}
          />
          <p className="sf-muted">{t("devices.e1.config.boatIdHint")}</p>
          <Select
            label={t("devices.e1.config.unitRole")}
            id="e1-unit-role"
            value={unitRole}
            onChange={(e) => setUnitRole(e.target.value)}
          >
            {UNIT_ROLES.map((role) => (
              <option key={role} value={role}>
                {t(`devices.e1.config.unitRoles.${role}`)}
              </option>
            ))}
          </Select>
          <InputField
            label={t("devices.e1.config.windMac")}
            id="e1-wind-mac"
            value={windMac}
            placeholder="AA:BB:CC:DD:EE:FF"
            onChange={(e) => setWindMac(e.target.value)}
          />
          <InputField
            label={t("devices.e1.config.windOffset")}
            id="e1-wind-offset"
            type="number"
            value={windOffset}
            onChange={(e) => setWindOffset(Number(e.target.value))}
          />
          <label className="sf-field">
            <input type="checkbox" checked={rtkEnabled} onChange={(e) => setRtkEnabled(e.target.checked)} />{" "}
            {t("devices.e1.config.rtkEnabled")}
          </label>
          <label className="sf-field">
            <input
              type="checkbox"
              checked={autoCleanupUploads}
              onChange={(e) => setAutoCleanupUploads(e.target.checked)}
            />{" "}
            {t("devices.e1.config.autoCleanupUploads")}
          </label>
          <p className="sf-muted">{t("devices.e1.config.autoCleanupUploadsHint")}</p>

          {configError && <p className="sf-form__error">{configError}</p>}
          {configSaved && <p className="sf-badge sf-badge--success">{t("common.saved")}</p>}
          <div className="sf-form__actions">
            <Button type="submit" disabled={e1.writeConfig.isPending}>
              {t("common.save")}
            </Button>
          </div>
        </form>
      </Card>

      <Card title={t("devices.e1.calibration.title")}>
        <p className="sf-muted">{t("devices.e1.calibration.hint")}</p>
        <div className="sf-form__actions">
          <Button
            variant="ghost"
            onClick={() => setConfirmingCalibrate(true)}
            disabled={e1.calibrate.isPending}
          >
            {t("devices.e1.calibration.calibrate")}
          </Button>
          <Button
            variant="ghost"
            onClick={() =>
              e1.calibrate.mutate(true, {
                onSuccess: setCalibResult,
              })
            }
            disabled={e1.calibrate.isPending}
          >
            {t("devices.e1.calibration.reset")}
          </Button>
        </div>
        {calibResult && (
          <p className={styles.calibResult}>
            {calibResult.status === "ok"
              ? t("devices.e1.calibration.result", {
                  heel: calibResult.heel_offset,
                  pitch: calibResult.pitch_offset,
                })
              : t(`devices.e1.calibration.error.${calibResult.reason ?? "sd_busy"}`)}
          </p>
        )}
      </Card>

      {confirmingCalibrate && (
        <ConfirmDialog
          title={t("devices.e1.calibration.calibrate")}
          message={t("devices.e1.calibration.confirmLevel")}
          confirmLabel={t("devices.e1.calibration.calibrate")}
          busy={e1.calibrate.isPending}
          onConfirm={() =>
            e1.calibrate.mutate(false, {
              onSuccess: (res) => {
                setCalibResult(res);
                setConfirmingCalibrate(false);
              },
            })
          }
          onClose={() => setConfirmingCalibrate(false)}
        />
      )}
      {infoDialog}
    </>
  );
}
