import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { windService, windKeys } from "@/services/wind";
import { usersService, userKeys } from "@/services/users";
import { devicesService, deviceKeys } from "@/services/devices";
import { boatsService, boatKeys } from "@/services/boats";
import { useToast } from "@/hooks/useToast";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { InputField } from "@/components/ui/InputField";
import { Spinner } from "@/components/ui/Spinner";
import { fmtDateTime, userLabel } from "@/utils/format";
import type { UUID, WindStation } from "@/types";

const PROVIDERS = ["noaa_ndbc", "noaa_metar", "custom_device"];
const STATION_TYPES = ["buoy", "metar", "custom_device"];

function WindStations() {
  const { t } = useTranslation();
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    provider: "noaa_ndbc",
    external_station_id: "",
    name: "",
    station_type: "buoy",
    lat: "",
    lng: "",
  });
  const [observing, setObserving] = useState<WindStation | null>(null);
  const [page, setPage] = useState(0);
  const OBS_PAGE_SIZE = 50;

  const stations = useQuery({ queryKey: windKeys.stations, queryFn: windService.listStations });
  const observations = useQuery({
    // The cache grows without bound (every scheduler tick upserts more rows),
    // so the admin view pages through it server-side rather than fetching
    // everything and slicing client-side.
    queryKey: windKeys.observations(observing?.id ?? "none", String(page)),
    queryFn: () =>
      windService.observations(observing!.id, { limit: OBS_PAGE_SIZE, offset: page * OBS_PAGE_SIZE }),
    enabled: observing !== null,
  });

  const create = useMutation({
    mutationFn: () =>
      windService.createStation({
        provider: form.provider,
        external_station_id: form.external_station_id,
        name: form.name || undefined,
        station_type: form.station_type,
        lat: form.lat ? Number(form.lat) : undefined,
        lng: form.lng ? Number(form.lng) : undefined,
      }),
    onSuccess: async () => {
      setForm({
        provider: "noaa_ndbc",
        external_station_id: "",
        name: "",
        station_type: "buoy",
        lat: "",
        lng: "",
      });
      await queryClient.invalidateQueries({ queryKey: windKeys.stations });
    },
    onError: () => notify(t("errors.generic"), "error"),
  });
  const remove = useMutation({
    mutationFn: (id: UUID) => windService.removeStation(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: windKeys.stations }),
  });

  return (
    <Card title={t("admin.windStations")}>
      <div className="sf-tablewrap">
        <table className="sf-table">
          <thead>
            <tr>
              <th>{t("admin.provider")}</th>
              <th>{t("admin.stationId")}</th>
              <th>{t("common.name")}</th>
              <th>{t("admin.stationType")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {stations.data?.map((s) => (
              <tr key={s.id}>
                <td>{s.provider}</td>
                <td>{s.external_station_id}</td>
                <td>{s.name ?? "—"}</td>
                <td>{s.station_type}</td>
                <td style={{ display: "flex", gap: "0.4rem" }}>
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
                    variant="danger"
                    className="sf-btn--sm"
                    onClick={() => remove.mutate(s.id)}
                  >
                    ×
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {observing && (
        <div style={{ marginTop: "0.75rem" }}>
          <h3>
            {t("admin.lastObservations")} — {observing.external_station_id}
          </h3>
          {observations.isLoading ? (
            <Spinner />
          ) : (
            <div className="sf-tablewrap" style={{ maxHeight: 260, overflowY: "auto" }}>
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
          <div className="sf-form__actions" style={{ justifyContent: "flex-start" }}>
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

      <form
        className="sf-form__row"
        style={{ alignItems: "end", marginTop: "0.75rem" }}
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          create.mutate();
        }}
      >
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
        <div className="sf-field">
          <Button type="submit" disabled={create.isPending || !form.external_station_id}>
            {t("admin.addStation")}
          </Button>
        </div>
      </form>
    </Card>
  );
}

function Users() {
  const { t } = useTranslation();
  const users = useQuery({ queryKey: userKeys.all, queryFn: usersService.list });
  return (
    <Card title={t("admin.users")}>
      <div className="sf-tablewrap">
        <table className="sf-table">
          <thead>
            <tr>
              <th>{t("common.name")}</th>
              <th>{t("auth.email")}</th>
              <th>{t("common.status")}</th>
              <th>{t("admin.superadmin")}</th>
            </tr>
          </thead>
          <tbody>
            {users.data?.map((u) => (
              <tr key={u.id}>
                <td>{userLabel(u)}</td>
                <td className="sf-muted">{u.email}</td>
                <td>
                  <span
                    className={
                      u.status === "active" ? "sf-badge sf-badge--success" : "sf-badge sf-badge--danger"
                    }
                  >
                    {u.status}
                  </span>
                </td>
                <td>{u.is_superadmin ? "✓" : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function DeviceTypes() {
  const { t } = useTranslation();
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ name: "", category: "boat_tracker", parser_key: "" });

  const types = useQuery({ queryKey: deviceKeys.types, queryFn: devicesService.listTypes });
  const create = useMutation({
    mutationFn: () => devicesService.createType(form),
    onSuccess: async () => {
      setForm({ name: "", category: "boat_tracker", parser_key: "" });
      await queryClient.invalidateQueries({ queryKey: deviceKeys.types });
    },
    onError: () => notify(t("errors.generic"), "error"),
  });
  const remove = useMutation({
    mutationFn: (id: UUID) => devicesService.removeType(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: deviceKeys.types }),
    onError: () => notify(t("errors.generic"), "error"),
  });

  return (
    <Card title={t("admin.deviceTypes")}>
      <div className="sf-tablewrap">
        <table className="sf-table">
          <thead>
            <tr>
              <th>{t("common.name")}</th>
              <th>{t("admin.category")}</th>
              <th>{t("admin.parserKey")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {types.data?.map((dt) => (
              <tr key={dt.id}>
                <td>{dt.name}</td>
                <td>{dt.category}</td>
                <td className="sf-muted">{dt.parser_key}</td>
                <td>
                  <Button variant="danger" className="sf-btn--sm" onClick={() => remove.mutate(dt.id)}>
                    ×
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <form
        className="sf-form__row"
        style={{ alignItems: "end", marginTop: "0.75rem" }}
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <InputField
          label={t("common.name")}
          id="dt-name"
          value={form.name}
          onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
          required
        />
        <Select
          label={t("admin.category")}
          id="dt-cat"
          value={form.category}
          onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}
        >
          <option value="boat_tracker">boat_tracker</option>
          <option value="wearable">wearable</option>
          <option value="wind_station">wind_station</option>
        </Select>
        <InputField
          label={t("admin.parserKey")}
          id="dt-parser"
          value={form.parser_key}
          onChange={(e) => setForm((f) => ({ ...f, parser_key: e.target.value }))}
          placeholder="e1_csv_v1"
          required
        />
        <div className="sf-field">
          <Button type="submit" disabled={create.isPending || !form.name || !form.parser_key}>
            {t("common.add")}
          </Button>
        </div>
      </form>
    </Card>
  );
}

function BoatClasses() {
  const { t } = useTranslation();
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");

  const classes = useQuery({ queryKey: boatKeys.classes, queryFn: boatsService.listClasses });
  const create = useMutation({
    mutationFn: () => boatsService.createClass({ name }),
    onSuccess: async () => {
      setName("");
      await queryClient.invalidateQueries({ queryKey: boatKeys.classes });
    },
    onError: () => notify(t("errors.generic"), "error"),
  });
  const remove = useMutation({
    mutationFn: (id: UUID) => boatsService.removeClass(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: boatKeys.classes }),
    onError: () => notify(t("errors.generic"), "error"),
  });

  return (
    <Card title={t("admin.boatClasses")}>
      <div className="sf-strip">
        {classes.data?.map((c) => (
          <div key={c.id} className="sf-strip__item sf-strip__item--muted">
            <span>
              <strong>{c.name}</strong>
            </span>
            <Button variant="danger" className="sf-btn--sm" onClick={() => remove.mutate(c.id)}>
              ×
            </Button>
          </div>
        ))}
      </div>
      <form
        className="sf-form__row"
        style={{ alignItems: "end", marginTop: "0.75rem" }}
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <InputField
          label={t("common.name")}
          id="bc-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <div className="sf-field">
          <Button type="submit" disabled={create.isPending || !name}>
            {t("common.add")}
          </Button>
        </div>
      </form>
    </Card>
  );
}

export function AdminPage() {
  const { t } = useTranslation();
  return (
    <div className="sf-section">
      <h1>{t("admin.title")}</h1>
      <div className="sf-section__body">
        <WindStations />
        <Users />
        <DeviceTypes />
        <BoatClasses />
      </div>
    </div>
  );
}
