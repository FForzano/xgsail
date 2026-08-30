import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { windService, windKeys } from "@/services/wind";
import { useToast } from "@/hooks/useToast";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { InputField } from "@/components/ui/InputField";
import { Modal } from "@/components/ui/Modal";
import { Spinner } from "@/components/ui/Spinner";
import { fmtDateTime } from "@/utils/format";
import type { UUID, WindStation, WindStationIssue } from "@/types";
import styles from "./WindStationsPage.module.css";

const PROVIDERS = [
  "noaa_ndbc",
  "noaa_metar",
  "custom_device",
  "cumulus_realtime",
  "cumulus_gauges_json",
];
const STATION_TYPES = ["buoy", "metar", "custom_device"];
// Providers polled by URL (source_url) rather than looked up by
// external_station_id against a fixed provider API — see
// backend/services/wind_providers/__init__.py::URL_BASED_PROVIDERS.
const URL_BASED_PROVIDERS = ["cumulus_realtime", "cumulus_gauges_json"];

const EMPTY_FORM = {
  provider: "noaa_ndbc",
  external_station_id: "",
  source_url: "",
  name: "",
  station_type: "buoy",
  lat: "",
  lng: "",
};
type StationForm = typeof EMPTY_FORM;

function formOf(station: WindStation): StationForm {
  return {
    provider: station.provider,
    external_station_id: station.external_station_id,
    source_url: station.source_url ?? "",
    name: station.name ?? "",
    station_type: station.station_type,
    lat: station.lat != null ? String(station.lat) : "",
    lng: station.lng != null ? String(station.lng) : "",
  };
}

function payloadOf(form: StationForm) {
  return {
    provider: form.provider,
    external_station_id: form.external_station_id,
    source_url: form.source_url || undefined,
    name: form.name || undefined,
    station_type: form.station_type,
    lat: form.lat ? Number(form.lat) : undefined,
    lng: form.lng ? Number(form.lng) : undefined,
  };
}

/** Compact `lat, lng` for the table — em-dash when either is missing, which
 * is exactly the case the `no_coordinates` health badge already flags. */
function fmtCoords(lat: number | null, lng: number | null): string {
  if (lat == null || lng == null) return "—";
  return `${lat.toFixed(4)}, ${lng.toFixed(4)}`;
}

/** Today and 72h ago as `yyyy-mm-dd`, the observation filter's starting range
 * — it mirrors the server's own default window when no range is sent. */
function defaultRange(): { from: string; to: string } {
  const today = new Date();
  const from = new Date(today.getTime() - 3 * 24 * 3600 * 1000);
  const iso = (d: Date) => d.toISOString().slice(0, 10);
  return { from: iso(from), to: iso(today) };
}

export function WindStationsPage() {
  const { t } = useTranslation();
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<StationForm>(EMPTY_FORM);
  const isUrlBased = URL_BASED_PROVIDERS.includes(form.provider);
  const [observing, setObserving] = useState<WindStation | null>(null);
  const [page, setPage] = useState(0);
  const [range, setRange] = useState(defaultRange);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<WindStation | null>(null);
  const OBS_PAGE_SIZE = 50;

  const stations = useQuery({ queryKey: windKeys.stations, queryFn: () => windService.listStations() });
  // Why a station isn't contributing — a dead sensor, missing coordinates, a
  // feed gone quiet. Its own query so a slow health scan never delays the
  // table itself.
  const health = useQuery({ queryKey: windKeys.health, queryFn: windService.stationsHealth });
  const issuesOf = (id: UUID): WindStationIssue[] =>
    health.data?.find((h) => h.station_id === id)?.issues ?? [];

  const observations = useQuery({
    // The cache grows without bound (every scheduler tick upserts more rows),
    // so the admin view pages through it server-side rather than fetching
    // everything and slicing client-side.
    queryKey: windKeys.observations(observing?.id ?? "none", `${range.from}:${range.to}:${page}`),
    queryFn: () =>
      windService.observations(observing!.id, {
        // The end date is inclusive of the whole day the operator picked.
        start: range.from ? `${range.from}T00:00:00Z` : undefined,
        end: range.to ? `${range.to}T23:59:59Z` : undefined,
        limit: OBS_PAGE_SIZE,
        offset: page * OBS_PAGE_SIZE,
      }),
    enabled: observing !== null,
  });

  const closeForms = async () => {
    setForm(EMPTY_FORM);
    setAdding(false);
    setEditing(null);
    await queryClient.invalidateQueries({ queryKey: windKeys.stations });
    await queryClient.invalidateQueries({ queryKey: windKeys.health });
  };

  const create = useMutation({
    mutationFn: () => windService.createStation(payloadOf(form)),
    onSuccess: closeForms,
    onError: () => notify(t("errors.generic"), "error"),
  });
  const update = useMutation({
    mutationFn: () => windService.updateStation(editing!.id, payloadOf(form)),
    onSuccess: closeForms,
    onError: () => notify(t("errors.generic"), "error"),
  });
  const remove = useMutation({
    mutationFn: (id: UUID) => windService.removeStation(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: windKeys.stations }),
  });

  const editingOrAdding = adding || editing !== null;
  const submitting = create.isPending || update.isPending;

  return (
    <>
      <div className="sf-tablewrap">
        <table className="sf-table">
          <thead>
            <tr>
              <th>{t("common.name")}</th>
              <th>{t("admin.coordinates")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {stations.data?.map((s) => {
              const issues = issuesOf(s.id);
              return (
                <tr key={s.id}>
                  <td>
                    <span className={styles.name}>
                      {s.name ?? "—"}
                      {issues.length > 0 && (
                        <span
                          className={`sf-badge sf-badge--warning ${styles.issue}`}
                          title={issues
                            .map((i) => `${t(`admin.windIssue.${i.code}`)}: ${i.detail}`)
                            .join("\n")}
                        >
                          <AlertTriangle size={12} strokeWidth={2} />
                          {t(`admin.windIssue.${issues[0].code}`)}
                          {issues.length > 1 ? ` +${issues.length - 1}` : ""}
                        </span>
                      )}
                    </span>
                  </td>
                  <td>{fmtCoords(s.lat, s.lng)}</td>
                  <td>
                    <div className={styles.actions}>
                      <Button
                        variant="ghost"
                        className="sf-btn--sm"
                        onClick={() => {
                          setObserving(observing?.id === s.id ? null : s);
                          setPage(0);
                        }}
                      >
                        {t("admin.observations")}
                      </Button>
                      <Button
                        variant="ghost"
                        className="sf-btn--sm"
                        onClick={() => {
                          setForm(formOf(s));
                          setEditing(s);
                        }}
                      >
                        {t("common.edit")}
                      </Button>
                      <Button
                        variant="danger"
                        className="sf-btn--sm"
                        onClick={() => remove.mutate(s.id)}
                      >
                        ×
                      </Button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {observing && (
        <div className={styles.observations}>
          <h3>
            {t("admin.lastObservations")} — {observing.name ?? observing.external_station_id}
          </h3>
          <div className={styles.filters}>
            <InputField
              label={t("common.from")}
              id="ws-obs-from"
              type="date"
              value={range.from}
              max={range.to}
              onChange={(e) => {
                setRange((r) => ({ ...r, from: e.target.value }));
                setPage(0);
              }}
            />
            <InputField
              label={t("common.to")}
              id="ws-obs-to"
              type="date"
              value={range.to}
              min={range.from}
              onChange={(e) => {
                setRange((r) => ({ ...r, to: e.target.value }));
                setPage(0);
              }}
            />
            <Button
              variant="ghost"
              className="sf-btn--sm"
              onClick={() => {
                setRange(defaultRange());
                setPage(0);
              }}
            >
              {t("common.reset")}
            </Button>
          </div>
          {observations.isLoading ? (
            <Spinner />
          ) : (
            <div className={`sf-tablewrap ${styles.obsScroll}`}>
              <table className="sf-table">
                <thead>
                  <tr>
                    <th>{t("common.date")}</th>
                    <th>TWD</th>
                    <th>TWS</th>
                    <th>Gust</th>
                  </tr>
                </thead>
                <tbody>
                  {(observations.data ?? []).map((o) => (
                    <tr key={o.observed_at}>
                      <td>{fmtDateTime(o.observed_at)}</td>
                      <td>{o.twd_deg != null ? `${o.twd_deg}°` : "—"}</td>
                      <td>{o.tws_kts != null ? `${o.tws_kts} kn` : "—"}</td>
                      <td>{o.gust_kts != null ? `${o.gust_kts} kn` : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className={`sf-form__actions ${styles.pager}`}>
            <Button
              variant="ghost"
              className="sf-btn--sm"
              disabled={page === 0}
              onClick={() => setPage((p) => Math.max(0, p - 1))}
            >
              ‹
            </Button>
            <Button
              variant="ghost"
              className="sf-btn--sm"
              disabled={(observations.data?.length ?? 0) < OBS_PAGE_SIZE}
              onClick={() => setPage((p) => p + 1)}
            >
              ›
            </Button>
          </div>
        </div>
      )}

      <div className={`sf-form__actions ${styles.pager}`} style={{ marginTop: "0.75rem" }}>
        <Button onClick={() => { setForm(EMPTY_FORM); setAdding(true); }}>
          {t("admin.addStation")}
        </Button>
      </div>

      {editingOrAdding && (
        <Modal
          title={editing ? t("admin.editStation") : t("admin.addStation")}
          onClose={() => {
            setAdding(false);
            setEditing(null);
          }}
        >
          <form
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              if (editing) update.mutate();
              else create.mutate();
            }}
          >
            <div className="sf-form__row">
              <Select
                label={t("admin.provider")}
                id="ws-provider"
                value={form.provider}
                onChange={(e) => setForm((f) => ({ ...f, provider: e.target.value }))}
              >
                {PROVIDERS.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </Select>
              <InputField
                label={t("admin.stationId")}
                id="ws-ext"
                value={form.external_station_id}
                onChange={(e) => setForm((f) => ({ ...f, external_station_id: e.target.value }))}
                placeholder="44013"
                required
              />
            </div>
            {isUrlBased && (
              <InputField
                label={t("admin.sourceUrl")}
                id="ws-source-url"
                value={form.source_url}
                onChange={(e) => setForm((f) => ({ ...f, source_url: e.target.value }))}
                placeholder="https://example.com/realtime.txt"
                required
              />
            )}
            <div className="sf-form__row">
              <InputField
                label="Lat"
                id="ws-lat"
                type="number"
                step="any"
                value={form.lat}
                onChange={(e) => setForm((f) => ({ ...f, lat: e.target.value }))}
                placeholder="44.79"
              />
              <InputField
                label="Lng"
                id="ws-lng"
                type="number"
                step="any"
                value={form.lng}
                onChange={(e) => setForm((f) => ({ ...f, lng: e.target.value }))}
                placeholder="12.33"
              />
            </div>
            <div className="sf-form__row">
              <InputField
                label={t("common.name")}
                id="ws-name"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              />
              <Select
                label={t("admin.stationType")}
                id="ws-type"
                value={form.station_type}
                onChange={(e) => setForm((f) => ({ ...f, station_type: e.target.value }))}
              >
                {STATION_TYPES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </Select>
            </div>
            <div className="sf-form__actions">
              <Button
                type="submit"
                disabled={
                  submitting ||
                  !form.external_station_id ||
                  (isUrlBased && !form.source_url)
                }
              >
                {editing ? t("common.save") : t("admin.addStation")}
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
