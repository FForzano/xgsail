import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { activitiesService, activityKeys } from "@/services/activities";
import { boatsService, boatKeys } from "@/services/boats";
import { sessionsService, sessionKeys } from "@/services/sessions";
import { useAuth } from "@/hooks/useAuth";
import { useCapabilities } from "@/hooks/useCapabilities";
import { useToast } from "@/hooks/useToast";
import { timeController } from "@/stores/timeController";
import { buildTracks, medianIntervalMs, timeBounds } from "@/components/race/raceModel";
import { MapView, type MapMark } from "@/components/race/MapView";
import { Timeline } from "@/components/race/Timeline";
import { SpeedChart } from "@/components/race/SpeedChart";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { InputField } from "@/components/ui/InputField";
import { Select } from "@/components/ui/Select";
import { OptionsMenu } from "@/components/ui/OptionsMenu";
import { Spinner } from "@/components/ui/Spinner";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { activityDisplayName } from "@/utils/activityName";
import { fmtDateTime } from "@/utils/format";
import { sessionStatusBadge } from "@/utils/badges";
import { MARK_ROLES } from "@/utils/markRoles";
import type { MarkRole, UUID, Visibility } from "@/types";

const VISIBILITIES: Visibility[] = ["public", "club", "group", "private"];

export function ActivityDetailPage() {
  const { activityId } = useParams<{ activityId: UUID }>();
  const { t } = useTranslation();
  const { user } = useAuth();
  const { can, isSuperadmin } = useCapabilities();
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [deleting, setDeleting] = useState(false);
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [markForm, setMarkForm] = useState<{ mark_role: MarkRole; lat: string; lng: string }>({
    mark_role: MARK_ROLES[0],
    lat: "",
    lng: "",
  });

  const activity = useQuery({
    queryKey: activityKeys.detail(activityId!),
    queryFn: () => activitiesService.get(activityId!),
    enabled: !!activityId,
  });
  const sessions = useQuery({
    queryKey: activityKeys.sessions(activityId!),
    queryFn: () => activitiesService.sessions(activityId!),
    enabled: !!activityId,
  });
  const marks = useQuery({
    queryKey: activityKeys.marks(activityId!),
    queryFn: () => activitiesService.marks(activityId!),
    enabled: !!activityId,
  });
  const activityData = useQuery({
    queryKey: activityKeys.data(activityId!),
    queryFn: () => activitiesService.data(activityId!),
    enabled: !!activityId,
  });
  const boats = useQuery({ queryKey: boatKeys.all, queryFn: () => boatsService.list() });
  // Each session has its own VMG series — unlike SessionDetailPage (a single
  // track), the map-wide `vmg` prop can't work here, so each session's
  // analysis is fetched individually and threaded onto its own Track (see
  // Track.vmg) for the popup to read.
  const sessionAnalyses = useQueries({
    queries: (sessions.data ?? []).map((s) => ({
      queryKey: sessionKeys.analysis(s.id),
      queryFn: () => sessionsService.analysis(s.id),
      enabled: !!sessions.data,
      retry: false,
    })),
  });

  // gps.json is never trimmed in place (see SessionDetailPage's trim
  // feature) — each session's own trim_start_time/trim_end_time (from the
  // `sessions` query, which returns full Session records) has to be applied
  // here too, or the activity map would keep showing the untrimmed track.
  const tracks = useMemo(() => {
    if (!activityData.data) return [];
    const built = buildTracks(activityData.data);
    const bySessionId = new Map(sessions.data?.map((s) => [s.id, s]) ?? []);
    const vmgBySessionId = new Map(
      (sessions.data ?? []).map((s, i) => [s.id, sessionAnalyses[i]?.data?.vmg_series]),
    );
    return built
      .map((tr) => {
        const s = bySessionId.get(tr.id);
        const start = s?.trim_start_time;
        const end = s?.trim_end_time;
        const pts =
          start == null && end == null
            ? tr.pts
            : tr.pts.filter(
                (p) => (start == null || p.ms >= start * 1000) && (end == null || p.ms <= end * 1000),
              );
        const boatImageUrl = boats.data?.find((b) => b.id === s?.boat_id)?.photos[0]?.url;
        return { ...tr, pts, boatImageUrl, vmg: vmgBySessionId.get(tr.id) };
      })
      .filter((tr) => tr.pts.length > 0);
  }, [activityData.data, sessions.data, sessionAnalyses, boats.data]);
  useEffect(() => {
    if (tracks.length) timeController.setBounds(...timeBounds(tracks));
    return () => timeController.pause();
  }, [tracks]);
  const mapMarks = useMemo<MapMark[]>(
    () => (marks.data ?? []).map((m) => ({ id: m.id, mark_role: m.mark_role, lat: m.lat, lng: m.lng })),
    [marks.data],
  );

  const addMark = useMutation({
    mutationFn: () =>
      activitiesService.addMark(activityId!, {
        mark_role: markForm.mark_role,
        lat: Number(markForm.lat),
        lng: Number(markForm.lng),
      }),
    onSuccess: async () => {
      setMarkForm({ mark_role: MARK_ROLES[0], lat: "", lng: "" });
      await queryClient.invalidateQueries({ queryKey: activityKeys.marks(activityId!) });
    },
    onError: () => notify(t("errors.generic"), "error"),
  });
  const removeMark = useMutation({
    mutationFn: (markId: UUID) => activitiesService.removeMark(activityId!, markId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: activityKeys.marks(activityId!) }),
  });
  const removeActivity = useMutation({
    mutationFn: () => activitiesService.remove(activityId!),
    onSuccess: () => navigate("/diario/activities"),
    onError: () => notify(t("errors.generic"), "error"),
  });
  const renameActivity = useMutation({
    mutationFn: (name: string) => activitiesService.update(activityId!, { name: name || null }),
    onSuccess: async () => {
      setEditingName(false);
      await queryClient.invalidateQueries({ queryKey: activityKeys.detail(activityId!) });
    },
    onError: () => notify(t("errors.generic"), "error"),
  });
  const updateVisibility = useMutation({
    mutationFn: (visibility: Visibility) => activitiesService.update(activityId!, { visibility }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: activityKeys.detail(activityId!) }),
    onError: () => notify(t("errors.generic"), "error"),
  });

  if (activity.isLoading || !activityId) return <Spinner />;
  if (!activity.data) return null;
  const a = activity.data;
  const canEdit =
    isSuperadmin ||
    a.created_by === user?.id ||
    (a.club_id != null && can("activity.manage", a.club_id));
  const boatName = (id: string) => boats.data?.find((b) => b.id === id)?.name ?? "—";

  return (
    <div className="sf-section__body">
      <Card
        title={
          editingName ? (
            <input
              className="sf-card__title-input"
              autoFocus
              defaultValue={nameDraft}
              onFocus={(e) => e.currentTarget.select()}
              onBlur={(e) => {
                const v = e.target.value.trim();
                if (v === (a.name ?? "")) {
                  setEditingName(false);
                  return;
                }
                renameActivity.mutate(v);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") e.currentTarget.blur();
                if (e.key === "Escape") setEditingName(false);
              }}
            />
          ) : (
            <>
              <span
                className={canEdit ? "sf-card__title--editable" : undefined}
                role={canEdit ? "button" : undefined}
                tabIndex={canEdit ? 0 : undefined}
                onClick={() => {
                  if (!canEdit) return;
                  setNameDraft(a.name ?? "");
                  setEditingName(true);
                }}
              >
                {activityDisplayName(a, t)}
              </span>{" "}
              <span className="sf-badge">{t(`activities.types.${a.type}`)}</span>{" "}
              {canEdit ? (
                <select
                  className="sf-badge sf-badge--select"
                  value={a.visibility}
                  disabled={updateVisibility.isPending}
                  onChange={(e) => updateVisibility.mutate(e.target.value as Visibility)}
                >
                  {VISIBILITIES.map((v) => (
                    <option key={v} value={v}>
                      {t(`activities.visibility.${v}`)}
                    </option>
                  ))}
                </select>
              ) : (
                <span className="sf-badge">{t(`activities.visibility.${a.visibility}`)}</span>
              )}
            </>
          )
        }
        actions={
          <OptionsMenu
            items={[
              {
                label: t("sessions.import"),
                onClick: () => navigate("/diario/activities/import"),
              },
              ...(canEdit
                ? [
                    {
                      label: t("common.delete"),
                      danger: true,
                      onClick: () => setDeleting(true),
                    },
                  ]
                : []),
            ]}
          />
        }
      >
        <p className="sf-muted">
          {fmtDateTime(a.started_at)} — {fmtDateTime(a.ended_at)}
        </p>
        {a.race_id && (
          <p>
            <Link to={`/diario/regate/race/${a.race_id}`}>{t("regate.open")}</Link>
          </p>
        )}
      </Card>

      <Card className="sf-card--flush" title={t("activities.map")}>
        {activityData.isLoading ? (
          <div className="sf-card__pad">
            <Spinner />
          </div>
        ) : activityData.isError ? (
          <p className="sf-muted sf-card__pad">{t("errors.generic")}</p>
        ) : tracks.length === 0 ? (
          <p className="sf-muted sf-card__pad">{t("activities.noGps")}</p>
        ) : (
          <div className="sf-section__body">
            <MapView
              tracks={tracks}
              marks={mapMarks}
              wind={
                tracks[0]?.pts[0]
                  ? { lat: tracks[0].pts[0].lat, lng: tracks[0].pts[0].lon, at: a.started_at }
                  : undefined
              }
              controls={
                <Timeline className="sf-timeline--overlay" stepMs={medianIntervalMs(tracks[0]) * 5} />
              }
              onOpenSession={(sessionId) => navigate(`/diario/activities/${activityId}/barche/${sessionId}`)}
            />
            <div className="sf-section__body sf-card__pad">
              <SpeedChart tracks={tracks} />
            </div>
          </div>
        )}
      </Card>

      <Card title={t("activities.boats")}>
        {sessions.data?.length ? (
          <div className="sf-tablewrap">
            <table className="sf-table">
              <thead>
                <tr>
                  <th></th>
                  <th>{t("sessions.boat")}</th>
                  <th>{t("sessions.start")}</th>
                  <th>{t("common.status")}</th>
                </tr>
              </thead>
              <tbody>
                {sessions.data.map((s) => (
                  <tr key={s.id}>
                    <td>
                      <Link to={`/diario/activities/${activityId}/barche/${s.id}`}>
                        {s.thumbnail ? (
                          <img src={s.thumbnail.url} alt="" className="sf-session-thumb" />
                        ) : (
                          <span className="sf-session-thumb sf-session-thumb--empty" aria-hidden />
                        )}
                      </Link>
                    </td>
                    <td>
                      <Link to={`/diario/activities/${activityId}/barche/${s.id}`}>
                        {boatName(s.boat_id)}
                      </Link>
                    </td>
                    <td>{fmtDateTime(s.started_at)}</td>
                    <td>
                      <span className={sessionStatusBadge(s.status)}>{s.status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="sf-muted">{t("common.none")}</p>
        )}
      </Card>

      <Card title={t("activities.marks")}>
        {marks.data?.length ? (
          <div className="sf-strip">
            {marks.data.map((m) => (
              <div key={m.id} className="sf-strip__item sf-strip__item--muted">
                <span>
                  <strong>{t(`activities.markRoles.${m.mark_role}`)}</strong>{" "}
                  <span className="sf-muted">
                    {m.lat.toFixed(5)}, {m.lng.toFixed(5)}
                  </span>
                </span>
                {canEdit && (
                  <Button
                    variant="ghost"
                    className="sf-btn--sm"
                    onClick={() => removeMark.mutate(m.id)}
                  >
                    {t("common.remove")}
                  </Button>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p className="sf-muted">{t("common.none")}</p>
        )}
        {canEdit && (
          <form
            className="sf-form__row"
            style={{ alignItems: "end", marginTop: "0.75rem" }}
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              addMark.mutate();
            }}
          >
            <Select
              label={t("activities.markRole")}
              id="mark-role"
              value={markForm.mark_role}
              onChange={(e) =>
                setMarkForm((f) => ({ ...f, mark_role: e.target.value as MarkRole }))
              }
            >
              {MARK_ROLES.map((role) => (
                <option key={role} value={role}>
                  {t(`activities.markRoles.${role}`)}
                </option>
              ))}
            </Select>
            <InputField
              label="Lat"
              id="mark-lat"
              type="number"
              step="any"
              value={markForm.lat}
              onChange={(e) => setMarkForm((f) => ({ ...f, lat: e.target.value }))}
              required
            />
            <InputField
              label="Lng"
              id="mark-lng"
              type="number"
              step="any"
              value={markForm.lng}
              onChange={(e) => setMarkForm((f) => ({ ...f, lng: e.target.value }))}
              required
            />
            <div className="sf-field">
              <Button type="submit" disabled={addMark.isPending}>
                {t("activities.addMark")}
              </Button>
            </div>
          </form>
        )}
      </Card>

      {deleting && (
        <ConfirmDialog
          title={t("common.delete")}
          message={t("activities.deleteConfirm")}
          busy={removeActivity.isPending}
          onConfirm={() => removeActivity.mutate()}
          onClose={() => setDeleting(false)}
        />
      )}
    </div>
  );
}
