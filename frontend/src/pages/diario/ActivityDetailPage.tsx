import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
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
import { BoatSessionCarousel, type BoatSessionCarouselItem } from "@/components/diario/BoatSessionCarousel";
import { SessionDetail } from "@/components/session/SessionDetail";
import { Timeline } from "@/components/race/Timeline";
import { SpeedChart } from "@/components/race/SpeedChart";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { InputField } from "@/components/ui/InputField";
import { Select } from "@/components/ui/Select";
import { OptionsMenu } from "@/components/ui/OptionsMenu";
import { Menu, type MenuSection } from "@/components/ui/Menu";
import { Spinner } from "@/components/ui/Spinner";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { activityDisplayName } from "@/utils/activityName";
import { fmtDateTime, fmtDistance, fmtKnots } from "@/utils/format";
import { MARK_ROLES } from "@/utils/markRoles";
import type { MarkRole, UUID, Visibility } from "@/types";
import { BackLink } from "@/components/ui/BackLink";

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
  const [pickingMarkOnMap, setPickingMarkOnMap] = useState(false);
  // Sections handed up by the embedded SessionDetail (solo activities) — see
  // its `onMenuSections` — merged into this page's own single ⋮ menu instead
  // of showing a second, redundant one on the map card.
  const [soloMenuSections, setSoloMenuSections] = useState<MenuSection[]>([]);
  // Set while editing an already-placed mark — the same form is reused for
  // both add and edit, submitting to `updateMark` instead of `addMark`.
  const [editingMarkId, setEditingMarkId] = useState<UUID | null>(null);
  const mapCardRef = useRef<HTMLDivElement>(null);

  const activity = useQuery({
    queryKey: activityKeys.detail(activityId!),
    queryFn: () => activitiesService.get(activityId!),
    enabled: !!activityId,
  });
  // A "solo" activity is rendered as its single session's own SessionDetail
  // (see the render below) instead of this page's own multi-track map/list
  // — the queries that back those are only needed for the multi-boat case.
  const isSolo = activity.data?.type === "solo";
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
    enabled: !!activityId && !isSolo,
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
      enabled: !!sessions.data && !isSolo,
      retry: false,
    })),
  });
  // Crew + stats per session, for the mobile boat carousel (BoatSessionCarousel)
  // only — the desktop table doesn't need either. Not needed for solo, where
  // SessionDetail shows its own session's crew/stats directly.
  const sessionCrews = useQueries({
    queries: (sessions.data ?? []).map((s) => ({
      queryKey: sessionKeys.crew(s.id),
      queryFn: () => sessionsService.crew(s.id),
      enabled: !!sessions.data && !isSolo,
    })),
  });
  const sessionStatsList = useQueries({
    queries: (sessions.data ?? []).map((s) => ({
      queryKey: sessionKeys.stats(s.id),
      queryFn: () => sessionsService.stats(s.id),
      enabled: !!sessions.data && !isSolo,
      retry: false,
    })),
  });

  // useQueries returns a new array reference on every render regardless of
  // whether any query's data actually changed — depending on `sessionAnalyses`
  // directly below would recompute `tracks` (and, downstream, force MapView
  // to tear down and re-fit the whole map, losing the user's pan/zoom and
  // any in-progress marker drag) on every unrelated state change on this
  // page. This derives a primitive key that only changes value when a
  // query's data actually updates, so the memo below only reruns then.
  const sessionAnalysesKey = sessionAnalyses.map((q) => q.dataUpdatedAt).join(",");

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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `sessionAnalyses`
    // intentionally excluded in favor of `sessionAnalysesKey` (see above).
  }, [activityData.data, sessions.data, sessionAnalysesKey, boats.data]);
  useEffect(() => {
    if (tracks.length) timeController.setBounds(...timeBounds(tracks));
    return () => timeController.pause();
  }, [tracks]);
  const mapMarks = useMemo<MapMark[]>(
    () =>
      (marks.data ?? [])
        // The mark being edited is represented by the draggable preview
        // below instead, so it isn't shown twice at (possibly) two positions.
        .filter((m) => m.id !== editingMarkId)
        .map((m) => ({ id: m.id, mark_role: m.mark_role, lat: m.lat, lng: m.lng })),
    [marks.data, editingMarkId],
  );
  // Live preview of the "add mark" form's current lat/lng (however it was
  // filled — typed or picked on the map) as a dashed marker, so the user can
  // see/adjust its position before submitting.
  const markPreview = useMemo<MapMark | null>(() => {
    const lat = Number(markForm.lat);
    const lng = Number(markForm.lng);
    if (markForm.lat === "" || markForm.lng === "" || Number.isNaN(lat) || Number.isNaN(lng)) return null;
    return {
      mark_role: markForm.mark_role,
      lat,
      lng,
      preview: true,
      // Draggable so the user can fine-tune the position picked on the map
      // before actually submitting the "add mark" form.
      draggable: true,
      onDragEnd: (newLat, newLng) =>
        setMarkForm((f) => ({ ...f, lat: newLat.toFixed(6), lng: newLng.toFixed(6) })),
    };
  }, [markForm]);
  const mapMarksWithPreview = useMemo(
    () => (markPreview ? [...mapMarks, markPreview] : mapMarks),
    [mapMarks, markPreview],
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
  const updateMark = useMutation({
    mutationFn: () =>
      activitiesService.updateMark(activityId!, editingMarkId!, {
        mark_role: markForm.mark_role,
        lat: Number(markForm.lat),
        lng: Number(markForm.lng),
      }),
    onSuccess: async () => {
      setMarkForm({ mark_role: MARK_ROLES[0], lat: "", lng: "" });
      setEditingMarkId(null);
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
    onSuccess: () => navigate("/diario/personale"),
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
  // Visibility on a club-linked activity is stricter than general edit
  // rights — only a club-scoped activity.manage holder may change it, not
  // just any creator (mirrors backend's can_change_activity_visibility).
  const canChangeVisibility =
    isSuperadmin || (a.club_id != null ? can("activity.manage", a.club_id) : a.created_by === user?.id);
  // The one session of a solo activity — rendered inline via SessionDetail
  // (see below) instead of navigating to a separate barche/:sessionId page.
  // Falls back to the regular multi-boat layout if a solo activity somehow
  // doesn't have exactly one session yet (e.g. import still processing).
  const soloSession = isSolo && sessions.data?.length === 1 ? sessions.data[0] : undefined;
  const boatName = (id: string) => boats.data?.find((b) => b.id === id)?.name ?? "—";
  const carouselItems: BoatSessionCarouselItem[] = (sessions.data ?? []).map((s, i) => ({
    sessionId: s.id,
    boatName: boatName(s.boat_id),
    boatPhotoUrl: boats.data?.find((b) => b.id === s.boat_id)?.photos[0]?.url ?? null,
    trackThumbUrl: s.thumbnail?.url ?? null,
    crew: sessionCrews[i]?.data ?? [],
    stats: sessionStatsList[i]?.data,
  }));

  return (
    <div className="sf-section__body">
      <BackLink fallback="/diario/personale" label={t("activities.backToActivities")} />
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
              {canChangeVisibility ? (
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
          soloSession ? (
            // Single merged menu for solo activities — combines this page's
            // own actions (Import, Delete) with the ones handed up by the
            // embedded SessionDetail (see soloMenuSections/onMenuSections),
            // instead of showing a second ⋮ menu on the map card below.
            <Menu
              sections={[
                {
                  items: [
                    {
                      label: t("sessions.import"),
                      onClick: () => navigate(`/diario/activities/import?activityId=${a.id}`),
                    },
                  ],
                },
                ...soloMenuSections,
                ...(canEdit
                  ? [
                      {
                        items: [{ label: t("common.delete"), danger: true, onClick: () => setDeleting(true) }],
                      },
                    ]
                  : []),
              ]}
            />
          ) : (
            <OptionsMenu
              items={[
                {
                  label: t("sessions.import"),
                  onClick: () => navigate(`/diario/activities/import?activityId=${a.id}`),
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
          )
        }
      >
        <p className="sf-muted">
          {fmtDateTime(a.started_at)} — {fmtDateTime(a.ended_at)}
        </p>
        {/* For a multi-boat activity, which boat is which is shown in the
            boats list/table below (thumbnail + name) — but a solo activity
            renders its one session inline with no such list, so this is the
            only place left to say which boat it was. Same thumbnail+name
            treatment as that table, not just a muted line of text. */}
        {soloSession &&
          (() => {
            const boat = boats.data?.find((b) => b.id === soloSession.boat_id);
            return (
              <p className="sf-crew-row">
                {boat?.photos[0]?.url ? (
                  <img src={boat.photos[0].url} alt="" className="sf-session-thumb" />
                ) : (
                  <span className="sf-session-thumb sf-session-thumb--empty" aria-hidden />
                )}
                <strong>{boat?.name ?? t("sessions.boat")}</strong>
              </p>
            );
          })()}
        {a.race_id && (
          <p>
            <Link to={`/diario/regate/race/${a.race_id}`}>{t("regate.open")}</Link>
          </p>
        )}
      </Card>

      {soloSession ? (
        <div ref={mapCardRef}>
          {pickingMarkOnMap && <p className="sf-muted">{t("activities.pickOnMapHint")}</p>}
          <SessionDetail
            sessionId={soloSession.id}
            variant="embedded"
            extraMarks={mapMarksWithPreview}
            pickMode={pickingMarkOnMap}
            onMapClick={(lat, lng) => {
              setMarkForm((f) => ({ ...f, lat: lat.toFixed(6), lng: lng.toFixed(6) }));
              setPickingMarkOnMap(false);
            }}
            onMenuSections={setSoloMenuSections}
          />
        </div>
      ) : (
        <>
          <div ref={mapCardRef}>
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
                {pickingMarkOnMap && <p className="sf-muted sf-card__pad">{t("activities.pickOnMapHint")}</p>}
                <MapView
                  tracks={tracks}
                  marks={mapMarksWithPreview}
                  wind={
                    tracks[0]?.pts[0]
                      ? { lat: tracks[0].pts[0].lat, lng: tracks[0].pts[0].lon, at: a.started_at }
                      : undefined
                  }
                  controls={
                    <Timeline overlay stepMs={medianIntervalMs(tracks[0]) * 5} />
                  }
                  onOpenSession={(sessionId) => navigate(`/diario/activities/${activityId}/barche/${sessionId}`)}
                  showBoatInfo
                  pickMode={pickingMarkOnMap}
                  onMapClick={(lat, lng) => {
                    setMarkForm((f) => ({ ...f, lat: lat.toFixed(6), lng: lng.toFixed(6) }));
                    setPickingMarkOnMap(false);
                  }}
                />
                <div className="sf-section__body sf-card__pad">
                  <SpeedChart tracks={tracks} />
                </div>
              </div>
            )}
          </Card>
          </div>

          <Card title={t("activities.boats")}>
            {sessions.data?.length ? (
              <>
                <p className="sf-muted">{t("activities.boatsHint")}</p>
                <BoatSessionCarousel
                  items={carouselItems}
                  onOpen={(sessionId) => navigate(`/diario/activities/${activityId}/barche/${sessionId}`)}
                />
                <div className="sf-tablewrap sf-desktop-only">
                  <table className="sf-table">
                    <thead>
                      <tr>
                        <th></th>
                        <th>{t("sessions.boat")}</th>
                        <th>{t("sessions.start")}</th>
                        <th>{t("sessions.distance")}</th>
                        <th>{t("sessions.avgSpeed")}</th>
                        <th>{t("sessions.maxSpeed")}</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {sessions.data.map((s, i) => {
                        const stats = sessionStatsList[i]?.data;
                        return (
                          <tr
                            key={s.id}
                            className="sf-table__row--clickable"
                            role="link"
                            tabIndex={0}
                            onClick={() => navigate(`/diario/activities/${activityId}/barche/${s.id}`)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" || e.key === " ") {
                                e.preventDefault();
                                navigate(`/diario/activities/${activityId}/barche/${s.id}`);
                              }
                            }}
                          >
                            <td>
                              {s.thumbnail ? (
                                <img src={s.thumbnail.url} alt="" className="sf-session-thumb" />
                              ) : (
                                <span className="sf-session-thumb sf-session-thumb--empty" aria-hidden />
                              )}
                            </td>
                            <td>{boatName(s.boat_id)}</td>
                            <td>{fmtDateTime(s.started_at)}</td>
                            <td>{stats ? fmtDistance(stats.distance_m) : "—"}</td>
                            <td>{stats ? fmtKnots(stats.avg_speed_kts) : "—"}</td>
                            <td>{stats ? fmtKnots(stats.max_speed_kts) : "—"}</td>
                            <td className="sf-table__chevron" aria-hidden>
                              <svg viewBox="0 0 16 16" width="16" height="16">
                                <path
                                  d="M5 2.5 11.5 8 5 13.5"
                                  fill="none"
                                  stroke="currentColor"
                                  strokeWidth="2.2"
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                />
                              </svg>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </>
            ) : (
              <p className="sf-muted">{t("common.none")}</p>
            )}
          </Card>
        </>
      )}

      <Card title={t("activities.marks")}>
        {marks.data?.length ? (
          <div className="sf-strip">
            {marks.data.map((m) => (
              <div
                key={m.id}
                className={`sf-strip__item sf-strip__item--muted${
                  m.id === editingMarkId ? " sf-strip__item--active" : ""
                }`}
              >
                <span>
                  <strong>{t(`activities.markRoles.${m.mark_role}`)}</strong>{" "}
                  <span className="sf-muted">
                    {m.lat.toFixed(5)}, {m.lng.toFixed(5)}
                  </span>
                </span>
                {canEdit && (
                  <>
                    <Button
                      variant="ghost"
                      className="sf-btn--sm"
                      onClick={() => {
                        setEditingMarkId(m.id);
                        setMarkForm({ mark_role: m.mark_role, lat: String(m.lat), lng: String(m.lng) });
                      }}
                    >
                      {t("activities.editMark")}
                    </Button>
                    <Button
                      variant="ghost"
                      className="sf-btn--sm"
                      onClick={() => {
                        if (m.id === editingMarkId) {
                          setEditingMarkId(null);
                          setMarkForm({ mark_role: MARK_ROLES[0], lat: "", lng: "" });
                        }
                        removeMark.mutate(m.id);
                      }}
                    >
                      {t("common.remove")}
                    </Button>
                  </>
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
              if (editingMarkId) updateMark.mutate();
              else addMark.mutate();
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
            {(tracks.length > 0 || soloSession) && (
              <div className="sf-field">
                <Button
                  type="button"
                  variant={pickingMarkOnMap ? "primary" : "ghost"}
                  onClick={() => {
                    setPickingMarkOnMap((v) => !v);
                    mapCardRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
                  }}
                >
                  {t(pickingMarkOnMap ? "activities.pickingOnMap" : "activities.pickOnMap")}
                </Button>
              </div>
            )}
            {/* Convenience autofill: a finish line very often coincides with
                the start line, so offer to copy the matching start mark's
                position instead of requiring it to be re-entered/re-picked. */}
            {(markForm.mark_role === "finish_pin" || markForm.mark_role === "finish_rc") &&
              (() => {
                const startRole = markForm.mark_role === "finish_pin" ? "pin" : "rc";
                const startMark = marks.data?.find((m) => m.mark_role === startRole);
                if (!startMark) return null;
                return (
                  <div className="sf-field">
                    <Button
                      type="button"
                      variant="ghost"
                      onClick={() =>
                        setMarkForm((f) => ({ ...f, lat: String(startMark.lat), lng: String(startMark.lng) }))
                      }
                    >
                      {t(markForm.mark_role === "finish_pin" ? "activities.sameAsStartPin" : "activities.sameAsStartRc")}
                    </Button>
                  </div>
                );
              })()}
            <div className="sf-field">
              <Button type="submit" disabled={addMark.isPending || updateMark.isPending}>
                {t(editingMarkId ? "activities.saveMark" : "activities.addMark")}
              </Button>
            </div>
            {editingMarkId && (
              <div className="sf-field">
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => {
                    setEditingMarkId(null);
                    setMarkForm({ mark_role: MARK_ROLES[0], lat: "", lng: "" });
                    setPickingMarkOnMap(false);
                  }}
                >
                  {t("activities.cancelEditMark")}
                </Button>
              </div>
            )}
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
