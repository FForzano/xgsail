import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { sessionsService, sessionKeys } from "@/services/sessions";
import { boatsService, boatKeys } from "@/services/boats";
import { useCapabilities } from "@/hooks/useCapabilities";
import { useToast } from "@/hooks/useToast";
import { timeController } from "@/stores/timeController";
import { buildTrack, timeBounds, trackColor } from "@/components/race/raceModel";
import { MapView } from "@/components/race/MapView";
import { Timeline } from "@/components/race/Timeline";
import { SpeedChart } from "@/components/race/SpeedChart";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Spinner } from "@/components/ui/Spinner";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { ImageUploader } from "@/components/common/ImageUploader";
import { UserPicker } from "@/components/common/UserPicker";
import { useMediaUpload } from "@/hooks/useMediaUpload";
import { fmtDateTime, fmtDistance, fmtDuration, fmtKnots, userLabel } from "@/utils/format";
import { sessionStatusBadge } from "./SessionsPage";
import type { GpsPoint, UUID } from "@/types";
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
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [addingCrew, setAddingCrew] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [gps, setGps] = useState<GpsPoint[] | null>(null);

  const session = useQuery({
    queryKey: sessionKeys.detail(sessionId!),
    queryFn: () => sessionsService.get(sessionId!),
    enabled: !!sessionId,
  });
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

  const addCrew = useMutation({
    mutationFn: (userId: UUID) => sessionsService.addCrew(sessionId!, { user_id: userId }),
    onSuccess: async () => {
      setAddingCrew(false);
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
    onSuccess: () => navigate("/diario/sessioni"),
    onError: () => notify(t("errors.generic"), "error"),
  });
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
      <Card
        title={
          <>
            {boat?.name ?? t("sessions.boat")} — {fmtDateTime(s.started_at)}{" "}
            <span className={sessionStatusBadge(s.status)}>{s.status}</span>
          </>
        }
        actions={
          manager && (
            <Button variant="danger" className="sf-btn--sm" onClick={() => setDeleting(true)}>
              {t("common.delete")}
            </Button>
          )
        }
      >
        {stats.data && (
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
        )}
        {s.activity_id && (
          <p className="sf-muted">
            <Link to={`/diario/activities/${s.activity_id}`}>{t("sessions.activity")}</Link>
          </p>
        )}
      </Card>

      <Card title={t("sessions.playback")}>
        {streams.isLoading || (gpsStream && gps === null) ? (
          <Spinner />
        ) : tracks.length === 0 ? (
          <p className="sf-muted">{t("sessions.noGps")}</p>
        ) : (
          <div className="sf-section__body">
            <MapView tracks={tracks} className="sf-race__map sf-map--session" />
            <Timeline />
            <SpeedChart tracks={tracks} />
          </div>
        )}
      </Card>

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
                <span>
                  <strong>{userLabel(c.user)}</strong>{" "}
                  <span className="sf-muted">{c.sailing_role}</span>
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

      {addingCrew && (
        <Modal title={t("sessions.addCrew")} onClose={() => setAddingCrew(false)}>
          <UserPicker busy={addCrew.isPending} onPick={(u) => addCrew.mutate(u.id)} />
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
