import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { sessionsService, sessionKeys } from "@/services/sessions";
import { boatsService, boatKeys } from "@/services/boats";
import { useCapabilities } from "@/hooks/useCapabilities";
import { useToast } from "@/hooks/useToast";
import { timeController } from "@/stores/timeController";
import { buildTrack, medianIntervalMs, timeBounds, trackColor } from "@/components/race/raceModel";
import { MapView, type MapMark } from "@/components/race/MapView";
import { Timeline } from "@/components/race/Timeline";
import { SpeedChart } from "@/components/race/SpeedChart";
import { PlaybackIndicators } from "@/components/session/PlaybackIndicators";
import { MapLegsOptions } from "@/components/session/MapLegsOptions";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { OptionsMenu } from "@/components/ui/OptionsMenu";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { Spinner } from "@/components/ui/Spinner";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Avatar } from "@/components/ui/Avatar";
import { ImageUploader } from "@/components/common/ImageUploader";
import { UserPicker } from "@/components/common/UserPicker";
import { WindCard } from "@/components/common/WindCard";
import { SessionAnalysis } from "@/components/session/SessionAnalysis";
import { useMediaUpload } from "@/hooks/useMediaUpload";
import { fmtDateTime, fmtDistance, fmtDuration, fmtKnots, userLabel } from "@/utils/format";
import { legSequence } from "@/utils/legSequence";
import { sessionStatusBadge } from "@/utils/badges";
import { SAILING_ROLES } from "@/utils/sailingRoles";
import type { GpsPoint, SailingRole, UUID } from "@/types";
import { useRef } from "react";

function VideoUploader({ sessionId, onDone }: { sessionId: UUID; onDone: () => Promise<void> }) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const { upload, busy } = useMediaUpload({
    create: () => sessionsService.createVideo(sessionId),
    confirm: (fileId) => sessionsService.confirmVideo(sessionId, fileId),
    onDone,
  });
  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept="video/mp4"
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) void upload(f);
          e.target.value = "";
        }}
      />
      <Button
        variant="ghost"
        className="sf-btn--sm"
        disabled={busy}
        onClick={() => inputRef.current?.click()}
      >
        {busy ? "…" : t("common.upload")}
      </Button>
    </>
  );
}

export function SessionDetailPage() {
  const { sessionId } = useParams<{ sessionId: UUID }>();
  const { t } = useTranslation();
  const { isBoatManager } = useCapabilities();
  const { notify, update } = useToast();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [addingCrew, setAddingCrew] = useState(false);
  const [crewRole, setCrewRole] = useState<SailingRole>("crew");
  const [deleting, setDeleting] = useState(false);
  const [gps, setGps] = useState<GpsPoint[] | null>(null);
  const [showLegs, setShowLegs] = useState(true);
  const [showManeuvers, setShowManeuvers] = useState(true);
  const [maneuverEditMode, setManeuverEditMode] = useState(false);
  // First of the two track clicks that bracket a manually-added maneuver
  // (see MapView's placementMode) — the second click opens the confirm modal.
  const [maneuverDraftStart, setManeuverDraftStart] =
    useState<{ lat: number; lon: number; timestamp: number } | null>(null);
  const [maneuverDraftEnd, setManeuverDraftEnd] =
    useState<{ lat: number; lon: number; timestamp: number } | null>(null);
  const [maneuverDraftType, setManeuverDraftType] = useState<"tack" | "gybe" | "course_change">("tack");
  // Sticky toast id for the reanalyze/wind-refresh job — created "pending"
  // when triggered, resolved to success/error once the poll below lands.
  const [reanalysisToastId, setReanalysisToastId] = useState<number | null>(null);
  const reanalysisPolling = reanalysisToastId !== null;

  const session = useQuery({
    queryKey: sessionKeys.detail(sessionId!),
    queryFn: () => sessionsService.get(sessionId!),
    enabled: !!sessionId,
  });
  // Reanalyze/wind-refresh run in the background (backend/routers/sessions.py)
  // — poll the job status every 3s while one is running, same pattern as
  // ImportPage's upload-processing poll.
  const reanalysisStatus = useQuery({
    queryKey: sessionKeys.reanalysisStatus(sessionId!),
    queryFn: () => sessionsService.reanalysisStatus(sessionId!),
    enabled: !!sessionId && reanalysisPolling,
    refetchInterval: reanalysisPolling ? 3000 : false,
  });
  useEffect(() => {
    if (reanalysisToastId === null) return;
    const data = reanalysisStatus.data;
    if (!data || data.status === "running") return;
    const toastId = reanalysisToastId;
    setReanalysisToastId(null);
    if (data.status === "failed") {
      update(toastId, data.error || t("errors.generic"), "error");
      return;
    }
    update(toastId, t("sessions.reanalyzeDone"), "success");
    queryClient.invalidateQueries({ queryKey: sessionKeys.detail(sessionId!) });
    queryClient.invalidateQueries({ queryKey: sessionKeys.analysis(sessionId!) });
    queryClient.invalidateQueries({ queryKey: sessionKeys.stats(sessionId!) });
    queryClient.invalidateQueries({ queryKey: sessionKeys.streams(sessionId!) });
  }, [reanalysisToastId, reanalysisStatus.data, sessionId, queryClient, update, t]);
  const streams = useQuery({
    queryKey: sessionKeys.streams(sessionId!),
    queryFn: () => sessionsService.streams(sessionId!),
    enabled: !!sessionId,
  });
  const stats = useQuery({
    queryKey: sessionKeys.stats(sessionId!),
    queryFn: () => sessionsService.stats(sessionId!),
    enabled: !!sessionId,
    retry: false, // 404 = not computed yet
  });
  const crew = useQuery({
    queryKey: sessionKeys.crew(sessionId!),
    queryFn: () => sessionsService.crew(sessionId!),
    enabled: !!sessionId,
  });
  const photos = useQuery({
    queryKey: sessionKeys.photos(sessionId!),
    queryFn: () => sessionsService.photos(sessionId!),
    enabled: !!sessionId,
  });
  const videos = useQuery({
    queryKey: sessionKeys.videos(sessionId!),
    queryFn: () => sessionsService.videos(sessionId!),
    enabled: !!sessionId,
  });
  const boats = useQuery({ queryKey: boatKeys.all, queryFn: () => boatsService.list() });
  // Same query key/fn as SessionAnalysis — TanStack Query dedupes, no extra
  // network round-trip — just so the map can plot leg/maneuver markers.
  const analysis = useQuery({
    queryKey: sessionKeys.analysis(sessionId!),
    queryFn: () => sessionsService.analysis(sessionId!),
    enabled: !!sessionId,
    retry: false,
    // A manually-added maneuver starts `pending` until the worker's
    // async stat computation lands (see POST .../maneuvers) — poll while
    // any maneuver is still pending, same 3s cadence as the reanalysis poll.
    refetchInterval: (query) =>
      query.state.data?.maneuvers.some((m) => m.pending) ? 3000 : false,
  });

  // The gps stream JSON lives in object storage — fetch via its download_url.
  const gpsStream = streams.data?.find((s) => s.sensor_type === "gps" && s.download_url);
  useEffect(() => {
    if (!gpsStream?.download_url) return;
    let cancelled = false;
    void fetch(gpsStream.download_url)
      .then((r) => (r.ok ? r.json() : []))
      .then((points: GpsPoint[]) => {
        if (!cancelled) setGps(points);
      })
      .catch(() => {
        if (!cancelled) setGps([]);
      });
    return () => {
      cancelled = true;
    };
  }, [gpsStream?.download_url]);

  const tracks = useMemo(() => {
    if (!gps?.length) return [];
    return [buildTrack(sessionId!, t("sessions.playback"), gps, trackColor(0))];
  }, [gps, sessionId, t]);

  useEffect(() => {
    if (tracks.length) timeController.setBounds(...timeBounds(tracks));
  }, [tracks]);

  const marks = useMemo<MapMark[]>(() => {
    const out: MapMark[] = [];
    if (showLegs && analysis.data?.legs.length) {
      const seq = legSequence(analysis.data.legs);
      for (const l of analysis.data.legs) {
        if (l.start_lat == null || l.start_lon == null) continue;
        out.push({
          id: l.id,
          kind: "leg",
          seq: seq.get(l.id),
          mark_role: t(`sessions.${l.leg_type}`),
          lat: l.start_lat,
          lng: l.start_lon,
        });
      }
    }
    if (showManeuvers && analysis.data?.maneuvers.length) {
      // Rejected maneuvers are hidden outside edit mode (same as the table,
      // see ManeuversTable) — in edit mode they stay visible so a "restore"
      // action is reachable.
      for (const m of analysis.data.maneuvers) {
        if (m.start_lat == null || m.start_lon == null) continue;
        if (m.rejected && !maneuverEditMode) continue;
        out.push({
          id: m.id,
          kind: m.pending ? "maneuver-pending" : "maneuver",
          mark_role: t(`sessions.${m.maneuver_type}`),
          lat: m.start_lat,
          lng: m.start_lon,
        });
      }
    }
    if (maneuverDraftStart) {
      out.push({
        id: "maneuver-draft-start",
        kind: "maneuver-draft",
        mark_role: t("sessions.maneuverDraftStart"),
        lat: maneuverDraftStart.lat,
        lng: maneuverDraftStart.lon,
      });
    }
    return out;
  }, [analysis.data, showLegs, showManeuvers, maneuverEditMode, maneuverDraftStart, t]);

  const addCrew = useMutation({
    mutationFn: (userId: UUID) =>
      sessionsService.addCrew(sessionId!, { user_id: userId, sailing_role: crewRole }),
    onSuccess: async () => {
      setAddingCrew(false);
      setCrewRole("crew");
      await queryClient.invalidateQueries({ queryKey: sessionKeys.crew(sessionId!) });
    },
    onError: () => notify(t("errors.generic"), "error"),
  });
  const removeCrew = useMutation({
    mutationFn: (userId: UUID) => sessionsService.removeCrew(sessionId!, userId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: sessionKeys.crew(sessionId!) }),
  });
  const removeSession = useMutation({
    mutationFn: () => sessionsService.remove(sessionId!),
    onSuccess: () => navigate(session.data ? `/diario/activities/${session.data.activity_id}` : "/diario/activities"),
    onError: () => notify(t("errors.generic"), "error"),
  });
  // Seed the status query with "running" the instant the job is accepted:
  // without this, starting a second job right after the first one finished
  // would briefly poll with the previous (already-resolved) cached result
  // still in place, and the effect below would mistake it for "already done".
  const startReanalysisPolling = () => {
    queryClient.setQueryData(sessionKeys.reanalysisStatus(sessionId!), { status: "running", error: null });
    setReanalysisToastId(notify(t("sessions.reanalyzing"), "info", null));
  };
  const reanalyze = useMutation({
    mutationFn: () => sessionsService.reanalyze(sessionId!),
    onSuccess: startReanalysisPolling,
    onError: () => notify(t("errors.generic"), "error"),
  });
  const refreshWind = useMutation({
    mutationFn: () => sessionsService.refreshWind(sessionId!),
    onSuccess: startReanalysisPolling,
    onError: () => notify(t("errors.generic"), "error"),
  });
  const addManeuver = useMutation({
    mutationFn: () =>
      sessionsService.addManeuver(sessionId!, {
        maneuver_type: maneuverDraftType,
        start_time: Math.min(maneuverDraftStart!.timestamp, maneuverDraftEnd!.timestamp),
        end_time: Math.max(maneuverDraftStart!.timestamp, maneuverDraftEnd!.timestamp),
      }),
    onSuccess: async () => {
      setManeuverDraftStart(null);
      setManeuverDraftEnd(null);
      setManeuverDraftType("tack");
      await queryClient.invalidateQueries({ queryKey: sessionKeys.analysis(sessionId!) });
    },
    onError: () => notify(t("errors.generic"), "error"),
  });

  const handleManeuverPlacement = (point: { lat: number; lon: number; timestamp: number }) => {
    if (!maneuverDraftStart) {
      setManeuverDraftStart(point);
      return;
    }
    setManeuverDraftEnd(point);
  };

  const removePhoto = useMutation({
    mutationFn: (imageId: UUID) => sessionsService.removePhoto(sessionId!, imageId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: sessionKeys.photos(sessionId!) }),
  });

  if (session.isLoading || !sessionId) return <Spinner />;
  if (!session.data) return null;
  const s = session.data;
  const boat = boats.data?.find((b) => b.id === s.boat_id);
  const manager = isBoatManager(s.boat_id);

  return (
    <div className="sf-section__body">
      {s.activity_id && (
        <Link to={`/diario/activities/${s.activity_id}`} className="sf-backlink">
          ← {t("sessions.backToActivity")}
        </Link>
      )}
      <Card
        title={
          <>
            {boat?.name ?? t("sessions.boat")} — {fmtDateTime(s.started_at)}{" "}
            {reanalysisPolling ? (
              <span className="sf-badge sf-badge--pending">
                <Spinner inline /> {t("sessions.reanalyzing")}
              </span>
            ) : (
              <span className={sessionStatusBadge(s.status)}>{s.status}</span>
            )}
          </>
        }
        actions={
          manager && (
            <OptionsMenu
              items={[
                {
                  label: t("sessions.reanalyze"),
                  onClick: () => reanalyze.mutate(),
                  disabled: reanalyze.isPending || reanalysisPolling,
                },
                {
                  label: t("sessions.refreshWind"),
                  onClick: () => refreshWind.mutate(),
                  disabled: refreshWind.isPending || reanalysisPolling,
                },
                {
                  label: maneuverEditMode ? t("sessions.editManeuversDone") : t("sessions.editManeuvers"),
                  onClick: () => {
                    setManeuverEditMode((v) => !v);
                    setManeuverDraftStart(null);
                    setManeuverDraftEnd(null);
                  },
                },
                {
                  label: t("common.delete"),
                  danger: true,
                  onClick: () => setDeleting(true),
                },
              ]}
            />
          )
        }
      >
        {null}
      </Card>

      <Card className="sf-card--flush">
        {streams.isLoading || (gpsStream && gps === null) ? (
          <div className="sf-card__pad">
            <Spinner />
          </div>
        ) : tracks.length === 0 ? (
          <p className="sf-muted sf-card__pad">{t("sessions.noGps")}</p>
        ) : (
          <div className="sf-section__body">
            <MapView
              tracks={tracks}
              marks={marks}
              className="sf-race__map sf-map--session"
              vmg={analysis.data?.vmg_series}
              sessionWind={analysis.data?.true_wind}
              wind={
                tracks[0]?.pts[0]
                  ? { lat: tracks[0].pts[0].lat, lng: tracks[0].pts[0].lon, at: s.started_at }
                  : undefined
              }
              mapOptions={
                !!(analysis.data?.legs.length || analysis.data?.maneuvers.length) && (
                  <MapLegsOptions
                    showLegs={showLegs}
                    onShowLegsChange={setShowLegs}
                    showManeuvers={showManeuvers}
                    onShowManeuversChange={setShowManeuvers}
                  />
                )
              }
              controls={
                <Timeline className="sf-timeline--overlay" stepMs={medianIntervalMs(tracks[0]) * 5} />
              }
              placementMode={maneuverEditMode}
              onManeuverPlacement={handleManeuverPlacement}
            />
            {maneuverEditMode && (
              <p className="sf-muted sf-card__pad">
                {maneuverDraftStart ? t("sessions.maneuverPickEnd") : t("sessions.maneuverPickStart")}
              </p>
            )}
            <div className="sf-section__body sf-card__pad">
              <SpeedChart tracks={tracks} vmg={analysis.data?.vmg_series} />
              <PlaybackIndicators track={tracks[0]} vmg={analysis.data?.vmg_series} />
            </div>
          </div>
        )}
      </Card>

      {stats.data && (
        <Card title={t("sessions.stats")}>
          <div className="sf-tablewrap">
            <table className="sf-table">
              <tbody>
                <tr>
                  <th>{t("sessions.duration")}</th>
                  <td>{fmtDuration(stats.data.duration_s)}</td>
                  <th>{t("sessions.distance")}</th>
                  <td>{fmtDistance(stats.data.distance_m)}</td>
                </tr>
                <tr>
                  <th>{t("sessions.avgSpeed")}</th>
                  <td>{fmtKnots(stats.data.avg_speed_kts)}</td>
                  <th>{t("sessions.maxSpeed")}</th>
                  <td>{fmtKnots(stats.data.max_speed_kts)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {tracks[0]?.pts[0] && (
        <WindCard lat={tracks[0].pts[0].lat} lng={tracks[0].pts[0].lon} at={s.started_at} />
      )}

      <Card
        title={t("sessions.crew")}
        actions={
          manager && (
            <Button className="sf-btn--sm" onClick={() => setAddingCrew(true)}>
              {t("sessions.addCrew")}
            </Button>
          )
        }
      >
        {crew.data?.length ? (
          <div className="sf-strip">
            {crew.data.map((c) => (
              <div key={c.user_id} className="sf-strip__item sf-strip__item--muted">
                <span className="sf-crew-row">
                  <Avatar
                    profileImage={c.user?.profile_image}
                    firstName={c.user?.first_name}
                    lastName={c.user?.last_name}
                    size="sm"
                  />
                  <span>
                    <strong>{userLabel(c.user)}</strong>{" "}
                    <span className="sf-muted">{c.user?.email}</span>{" "}
                    <span className="sf-badge">{t(`sessions.sailingRoles.${c.sailing_role}`)}</span>
                  </span>
                </span>
                {manager && (
                  <Button
                    variant="ghost"
                    className="sf-btn--sm"
                    onClick={() => removeCrew.mutate(c.user_id)}
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
      </Card>

      <Card
        title={t("sessions.photos")}
        actions={
          <ImageUploader
            create={() => sessionsService.createPhoto(sessionId)}
            confirm={(imageId) => sessionsService.confirmPhoto(sessionId, imageId)}
            onDone={async () => {
              await queryClient.invalidateQueries({ queryKey: sessionKeys.photos(sessionId) });
            }}
          />
        }
      >
        {photos.data?.length ? (
          <div className="sf-photo-grid">
            {photos.data.map((p) => (
              <figure key={p.image_id}>
                <img src={p.url} alt="" />
                <Button
                  variant="danger"
                  className="sf-btn--sm sf-photo__del"
                  onClick={() => removePhoto.mutate(p.image_id)}
                >
                  ×
                </Button>
              </figure>
            ))}
          </div>
        ) : (
          <p className="sf-muted">{t("common.none")}</p>
        )}
      </Card>

      <Card
        title={t("sessions.videos")}
        actions={
          <VideoUploader
            sessionId={sessionId}
            onDone={async () => {
              await queryClient.invalidateQueries({ queryKey: sessionKeys.videos(sessionId) });
            }}
          />
        }
      >
        {videos.data?.length ? (
          <div className="sf-photo-grid">
            {videos.data.map((v) => (
              <video key={v.file_id} src={v.url} controls style={{ width: "100%" }} />
            ))}
          </div>
        ) : (
          <p className="sf-muted">{t("common.none")}</p>
        )}
      </Card>

      <SessionAnalysis sessionId={sessionId} editMode={maneuverEditMode} />

      {addingCrew && (
        <Modal
          title={t("sessions.addCrew")}
          onClose={() => {
            setAddingCrew(false);
            setCrewRole("crew");
          }}
        >
          <Select
            label={t("sessions.sailingRole")}
            id="crew-role"
            value={crewRole}
            onChange={(e) => setCrewRole(e.target.value as SailingRole)}
          >
            {SAILING_ROLES.map((role) => (
              <option key={role} value={role}>
                {t(`sessions.sailingRoles.${role}`)}
              </option>
            ))}
          </Select>
          <UserPicker busy={addCrew.isPending} onPick={(u) => addCrew.mutate(u.id)} />
        </Modal>
      )}
      {maneuverDraftStart && maneuverDraftEnd && (
        <Modal
          title={t("sessions.addManeuver")}
          onClose={() => {
            setManeuverDraftStart(null);
            setManeuverDraftEnd(null);
          }}
        >
          <Select
            label={t("sessions.type")}
            id="maneuver-draft-type"
            value={maneuverDraftType}
            onChange={(e) => setManeuverDraftType(e.target.value as typeof maneuverDraftType)}
          >
            {(["tack", "gybe", "course_change"] as const).map((type) => (
              <option key={type} value={type}>
                {t(`sessions.${type}`)}
              </option>
            ))}
          </Select>
          <Button disabled={addManeuver.isPending} onClick={() => addManeuver.mutate()}>
            {t("common.add")}
          </Button>
        </Modal>
      )}
      {deleting && (
        <ConfirmDialog
          title={t("common.delete")}
          message={t("sessions.deleteConfirm")}
          busy={removeSession.isPending}
          onConfirm={() => removeSession.mutate()}
          onClose={() => setDeleting(false)}
        />
      )}
    </div>
  );
}
