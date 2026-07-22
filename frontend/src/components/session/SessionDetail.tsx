import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { resolveApiUrl } from "@/api/client";
import { sessionsService, sessionKeys } from "@/services/sessions";
import { activitiesService, activityKeys } from "@/services/activities";
import { boatsService, boatKeys } from "@/services/boats";
import { useCapabilities } from "@/hooks/useCapabilities";
import { useToast } from "@/hooks/useToast";
import { timeController } from "@/stores/timeController";
import { buildTrack, medianIntervalMs, timeBounds, trackColor } from "@/components/race/raceModel";
import { MapView, type MapMark } from "@/components/race/MapView";
import { Timeline } from "@/components/race/Timeline";
import { SpeedChart } from "@/components/race/SpeedChart";
import { PlaybackIndicators } from "@/components/session/PlaybackIndicators";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Menu, type MenuSection } from "@/components/ui/Menu";
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
import photoGridStyles from "@/components/common/photoGrid.module.css";
import legendStyles from "@/components/race/legend.module.css";
import styles from "./SessionDetail.module.css";

const MAP_LEGEND_DOT_CLASS: Record<string, string> = {
  "leg-upwind": legendStyles.dotLegUpwind,
  "leg-reach": legendStyles.dotLegReach,
  "leg-downwind": legendStyles.dotLegDownwind,
  tack: legendStyles.dotTack,
  gybe: legendStyles.dotGybe,
  course_change: legendStyles.dotCourseChange,
};

// Keys of SessionLeg["leg_type"] and SessionManeuver["maneuver_type"] — one
// map toggle each (see the marks useMemo and the "Mostra su mappa" submenu).
type MapShowState = Record<"upwind" | "downwind" | "reach" | "tack" | "gybe" | "course_change", boolean>;

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

/** Full session analysis view (rich map, trim, maneuver-edit, stats, wind,
 * crew, photos, videos, SessionAnalysis) — shared between the standalone
 * `/barche/:sessionId` route (`variant="page"`) and inline embedding on the
 * parent activity page for solo activities (`variant="embedded"`, which
 * omits the title Card and boat name/date header since the caller already
 * shows those). `extraMarks` lets an embedding page (e.g. the activity's own
 * marks/boe) overlay additional pins on this session's map; `pickMode`/
 * `onMapClick` let it drive the same map's "pick a point" mode (e.g. placing
 * a race mark) instead of duplicating a second map just for that.
 * `onMenuSections` is how "embedded" hands its ⋮ menu sections up to the
 * caller instead of rendering its own — see the effect below. */
export function SessionDetail({
  sessionId,
  variant = "page",
  extraMarks = [],
  pickMode = false,
  onMapClick,
  onMenuSections,
}: {
  sessionId: UUID;
  variant?: "page" | "embedded";
  extraMarks?: MapMark[];
  pickMode?: boolean;
  onMapClick?: (lat: number, lng: number) => void;
  onMenuSections?: (sections: MenuSection[]) => void;
}) {
  const { t } = useTranslation();
  const { isBoatManager } = useCapabilities();
  const { notify, update } = useToast();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [addingCrew, setAddingCrew] = useState(false);
  const [crewRole, setCrewRole] = useState<SailingRole>("crew");
  const [deleting, setDeleting] = useState(false);
  const [gps, setGps] = useState<GpsPoint[] | null>(null);
  // Per-type map display toggles — replaces the old flat showLegs/
  // showManeuvers pair so bolina/lasco/poppa and virate/abbattute/cambi
  // rotta can each be shown/hidden independently. Hidden by default —
  // opt-in via the "Mostra su mappa" submenu.
  const [mapShow, setMapShow] = useState<MapShowState>({
    upwind: false, downwind: false, reach: false,
    tack: false, gybe: false, course_change: false,
  });
  const [maneuverEditMode, setManeuverEditMode] = useState(false);
  // Track-trim mode: dragging the two handles on the SpeedChart picks the
  // kept window (ms, matching Track.pts[].ms) before "Applica taglio" sends
  // it to the backend (seconds) — see enterTrimMode/applyTrim below.
  const [trimMode, setTrimMode] = useState(false);
  const [trimDraftStartMs, setTrimDraftStartMs] = useState<number | null>(null);
  const [trimDraftEndMs, setTrimDraftEndMs] = useState<number | null>(null);
  // mapShow as it was right before entering trim mode — legs/maneuvers are
  // forced off while trimming (they clutter a view that's only about the
  // track itself) and restored once trim mode ends, applied or cancelled.
  const [mapShowBeforeTrim, setMapShowBeforeTrim] = useState<MapShowState | null>(null);
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
  const [movingActivity, setMovingActivity] = useState(false);
  const [moveTargetId, setMoveTargetId] = useState("");
  const reanalysisPolling = reanalysisToastId !== null;

  const session = useQuery({
    queryKey: sessionKeys.detail(sessionId),
    queryFn: () => sessionsService.get(sessionId),
    enabled: !!sessionId,
  });
  // Only a standalone ("solo") recording can be moved into a real activity
  // (backend/routers/sessions.py::attach_to_activity) — fetched to gate the
  // "move to activity" menu item, not shown anywhere in the page itself.
  const currentActivity = useQuery({
    queryKey: activityKeys.detail(session.data?.activity_id ?? ""),
    queryFn: () => activitiesService.get(session.data!.activity_id!),
    enabled: !!session.data?.activity_id,
  });
  const activityOptions = useQuery({
    queryKey: activityKeys.list({ mine: "true" }),
    queryFn: () => activitiesService.list({ mine: true }),
    enabled: movingActivity,
  });
  // Reanalyze/wind-refresh run in the background (backend/routers/sessions.py)
  // — poll the job status every 3s while one is running, same pattern as
  // ImportPage's upload-processing poll.
  const reanalysisStatus = useQuery({
    queryKey: sessionKeys.reanalysisStatus(sessionId),
    queryFn: () => sessionsService.reanalysisStatus(sessionId),
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
    queryClient.invalidateQueries({ queryKey: sessionKeys.detail(sessionId) });
    queryClient.invalidateQueries({ queryKey: sessionKeys.analysis(sessionId) });
    queryClient.invalidateQueries({ queryKey: sessionKeys.stats(sessionId) });
    queryClient.invalidateQueries({ queryKey: sessionKeys.streams(sessionId) });
  }, [reanalysisToastId, reanalysisStatus.data, sessionId, queryClient, update, t]);
  const streams = useQuery({
    queryKey: sessionKeys.streams(sessionId),
    queryFn: () => sessionsService.streams(sessionId),
    enabled: !!sessionId,
  });
  const stats = useQuery({
    queryKey: sessionKeys.stats(sessionId),
    queryFn: () => sessionsService.stats(sessionId),
    enabled: !!sessionId,
    retry: false, // 404 = not computed yet
  });
  const crew = useQuery({
    queryKey: sessionKeys.crew(sessionId),
    queryFn: () => sessionsService.crew(sessionId),
    enabled: !!sessionId,
  });
  const photos = useQuery({
    queryKey: sessionKeys.photos(sessionId),
    queryFn: () => sessionsService.photos(sessionId),
    enabled: !!sessionId,
  });
  const videos = useQuery({
    queryKey: sessionKeys.videos(sessionId),
    queryFn: () => sessionsService.videos(sessionId),
    enabled: !!sessionId,
  });
  const boats = useQuery({ queryKey: boatKeys.all, queryFn: () => boatsService.list() });
  // Same query key/fn as SessionAnalysis — TanStack Query dedupes, no extra
  // network round-trip — just so the map can plot leg/maneuver markers.
  const analysis = useQuery({
    queryKey: sessionKeys.analysis(sessionId),
    queryFn: () => sessionsService.analysis(sessionId),
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
    void fetch(resolveApiUrl(gpsStream.download_url))
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

  // The boat's actual name/photo (not the generic "Playback" track label) —
  // shown in the map popup, so it needs the real boat even on this
  // single-track map.
  const trackBoat = boats.data?.find((b) => b.id === session.data?.boat_id);
  const trackBoatName = trackBoat?.name ?? t("sessions.playback");
  const trackBoatImageUrl = trackBoat?.photos[0]?.url;
  const tracks = useMemo(() => {
    if (!gps?.length) return [];
    const extra = { boatImageUrl: trackBoatImageUrl, vmg: analysis.data?.vmg_series };
    // Outside trim mode, the map/chart show only the persisted trim window —
    // gps.json itself is never touched (see enterTrimMode), so this is the
    // only place that actually hides the trimmed-away points from view.
    // While trimming, show the full track so the handles can be dragged back
    // out to any point, including past the current trim.
    if (trimMode) {
      return [buildTrack(sessionId, trackBoatName, gps, trackColor(0), extra)];
    }
    const start = session.data?.trim_start_time;
    const end = session.data?.trim_end_time;
    const points =
      start == null && end == null
        ? gps
        : gps.filter((p) => {
            const ms = Date.parse(p.t);
            return (start == null || ms >= start * 1000) && (end == null || ms <= end * 1000);
          });
    return [buildTrack(sessionId, trackBoatName, points, trackColor(0), extra)];
  }, [
    gps,
    sessionId,
    trackBoatName,
    trackBoatImageUrl,
    trimMode,
    session.data?.trim_start_time,
    session.data?.trim_end_time,
    analysis.data?.vmg_series,
  ]);

  useEffect(() => {
    if (tracks.length) timeController.setBounds(...timeBounds(tracks));
  }, [tracks]);

  const marks = useMemo<MapMark[]>(() => {
    const out: MapMark[] = [...extraMarks];
    if (analysis.data?.legs.length) {
      const seq = legSequence(analysis.data.legs);
      for (const l of analysis.data.legs) {
        if (!mapShow[l.leg_type]) continue;
        if (l.start_lat == null || l.start_lon == null) continue;
        // Midpoint of the leg, not its start — the number reads as "this leg",
        // not "the tack that started it". Falls back to the start point if
        // the end position is missing.
        const lat = l.end_lat != null ? (l.start_lat + l.end_lat) / 2 : l.start_lat;
        const lng = l.end_lon != null ? (l.start_lon + l.end_lon) / 2 : l.start_lon;
        out.push({
          id: l.id,
          kind: "leg",
          seq: seq.get(l.id),
          legType: l.leg_type,
          mark_role: t(`sessions.${l.leg_type}`),
          lat,
          lng,
        });
      }
    }
    if (analysis.data?.maneuvers.length) {
      // Rejected maneuvers are hidden outside edit mode (same as the table,
      // see ManeuversTable) — in edit mode they stay visible so a "restore"
      // action is reachable.
      for (const m of analysis.data.maneuvers) {
        if (!mapShow[m.maneuver_type]) continue;
        if (m.start_lat == null || m.start_lon == null) continue;
        if (m.rejected && !maneuverEditMode) continue;
        out.push({
          id: m.id,
          kind: m.pending ? "maneuver-pending" : "maneuver",
          maneuverType: m.maneuver_type,
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
  }, [extraMarks, analysis.data, mapShow, maneuverEditMode, maneuverDraftStart, t]);

  // Small always-visible key for the pin colors (see legend.module.css) — only
  // the types actually present (and currently toggled on) in `marks`, in a
  // stable order (legs, then maneuvers).
  const mapLegend = useMemo(() => {
    const order = ["leg-upwind", "leg-reach", "leg-downwind", "tack", "gybe", "course_change"];
    const seen = new Map<string, string>();
    for (const mk of marks) {
      if (mk.kind === "leg" && mk.legType) seen.set(`leg-${mk.legType}`, mk.mark_role);
      else if ((mk.kind === "maneuver" || mk.kind === "maneuver-pending") && mk.maneuverType) {
        seen.set(mk.maneuverType, mk.mark_role);
      }
    }
    return order.filter((key) => seen.has(key)).map((key) => [key, seen.get(key)!] as const);
  }, [marks]);

  const addCrew = useMutation({
    mutationFn: (userId: UUID) =>
      sessionsService.addCrew(sessionId, { user_id: userId, sailing_role: crewRole }),
    onSuccess: async () => {
      setAddingCrew(false);
      setCrewRole("crew");
      await queryClient.invalidateQueries({ queryKey: sessionKeys.crew(sessionId) });
    },
    onError: () => notify(t("errors.generic"), "error"),
  });
  const removeCrew = useMutation({
    mutationFn: (userId: UUID) => sessionsService.removeCrew(sessionId, userId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: sessionKeys.crew(sessionId) }),
  });
  const removeSession = useMutation({
    mutationFn: () => sessionsService.remove(sessionId),
    onSuccess: () => navigate(session.data ? `/diario/activities/${session.data.activity_id}` : "/diario/personale"),
    onError: () => notify(t("errors.generic"), "error"),
  });
  const moveToActivity = useMutation({
    mutationFn: () => sessionsService.attachToActivity(sessionId, moveTargetId as UUID),
    onSuccess: async (updated) => {
      setMovingActivity(false);
      setMoveTargetId("");
      await queryClient.invalidateQueries({ queryKey: sessionKeys.detail(sessionId) });
      navigate(`/diario/activities/${updated.activity_id}/barche/${sessionId}`);
    },
    onError: () => notify(t("errors.generic"), "error"),
  });
  // Seed the status query with "running" the instant the job is accepted:
  // without this, starting a second job right after the first one finished
  // would briefly poll with the previous (already-resolved) cached result
  // still in place, and the effect below would mistake it for "already done".
  const startReanalysisPolling = () => {
    queryClient.setQueryData(sessionKeys.reanalysisStatus(sessionId), { status: "running", error: null });
    setReanalysisToastId(notify(t("sessions.reanalyzing"), "info", null));
  };
  const reanalyze = useMutation({
    mutationFn: () => sessionsService.reanalyze(sessionId),
    onSuccess: startReanalysisPolling,
    onError: () => notify(t("errors.generic"), "error"),
  });
  const refreshWind = useMutation({
    mutationFn: () => sessionsService.refreshWind(sessionId),
    onSuccess: startReanalysisPolling,
    onError: () => notify(t("errors.generic"), "error"),
  });
  // Restores whatever map-display toggles were active before trim mode
  // forced them all off (see enterTrimMode) — runs whether trim was applied
  // or cancelled, since both paths call this.
  const exitTrimMode = () => {
    setTrimMode(false);
    setTrimDraftStartMs(null);
    setTrimDraftEndMs(null);
    setMapShow((prev) => mapShowBeforeTrim ?? prev);
    setMapShowBeforeTrim(null);
  };
  // Seeds the draft handles from the session's persisted trim (adjustable —
  // reversible, see the plan's "Taglio traccia" section) or, if unset, the
  // full track bounds. Also hides every leg/maneuver pin for the duration —
  // trimming is about the track itself, and they'd only clutter the chart/map.
  const enterTrimMode = () => {
    const [tMin, tMax] = tracks.length ? timeBounds(tracks) : [0, 0];
    const start = session.data?.trim_start_time;
    const end = session.data?.trim_end_time;
    setTrimDraftStartMs(start != null ? start * 1000 : tMin);
    setTrimDraftEndMs(end != null ? end * 1000 : tMax);
    setMapShowBeforeTrim(mapShow);
    setMapShow({ upwind: false, downwind: false, reach: false, tack: false, gybe: false, course_change: false });
    setTrimMode(true);
  };
  const setTrim = useMutation({
    mutationFn: (body: { trim_start_time: number | null; trim_end_time: number | null }) =>
      sessionsService.setTrim(sessionId, body),
    onSuccess: () => {
      exitTrimMode();
      startReanalysisPolling();
    },
    onError: () => notify(t("errors.generic"), "error"),
  });
  const applyTrim = () => {
    if (trimDraftStartMs == null || trimDraftEndMs == null) return;
    setTrim.mutate({ trim_start_time: trimDraftStartMs / 1000, trim_end_time: trimDraftEndMs / 1000 });
  };
  const addManeuver = useMutation({
    mutationFn: () =>
      sessionsService.addManeuver(sessionId, {
        maneuver_type: maneuverDraftType,
        start_time: Math.min(maneuverDraftStart!.timestamp, maneuverDraftEnd!.timestamp),
        end_time: Math.max(maneuverDraftStart!.timestamp, maneuverDraftEnd!.timestamp),
      }),
    onSuccess: async () => {
      setManeuverDraftStart(null);
      setManeuverDraftEnd(null);
      setManeuverDraftType("tack");
      await queryClient.invalidateQueries({ queryKey: sessionKeys.analysis(sessionId) });
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
    mutationFn: (imageId: UUID) => sessionsService.removePhoto(sessionId, imageId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: sessionKeys.photos(sessionId) }),
  });

  const boat = boats.data?.find((b) => b.id === session.data?.boat_id);
  const manager = session.data ? isBoatManager(session.data.boat_id) : false;

  // Single consolidated ⋮ menu (title-level) — replaces the old separate
  // OptionsMenu (session actions) + MapLegsOptions (⚙ on the map). Sections
  // absent for a non-manager viewer: only "Mostra su mappa" (always visible
  // to anyone who can see the analysis) and GPX download (visible to any
  // viewer — matches the backend's _require_visible permission, not the
  // edit-only _can_edit the other actions use).
  const menuSections: MenuSection[] = [];
  if (manager) {
    menuSections.push({
      heading: t("sessions.menuSectionSession"),
      items: [
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
        ...(currentActivity.data?.type === "solo"
          ? [{ label: t("sessions.moveToActivity"), onClick: () => setMovingActivity(true) }]
          : []),
      ],
    });
  }
  menuSections.push({
    heading: t("sessions.menuSectionTrack"),
    items: [
      {
        label: t("sessions.downloadGpx"),
        onClick: () => window.open(sessionsService.gpxDownloadUrl(sessionId), "_blank"),
      },
      // Flat items, no submenu — applying/cancelling happens via the visible
      // button row shown under the map while trimMode is active (clearer
      // than a menu item for a save/cancel action); this just starts/stops it.
      ...(manager
        ? [
            {
              label: trimMode ? t("sessions.editTrimDone") : t("sessions.trimTrack"),
              onClick: () => (trimMode ? exitTrimMode() : enterTrimMode()),
            },
          ]
        : []),
    ],
  });
  if (analysis.data?.legs.length || analysis.data?.maneuvers.length) {
    menuSections.push({
      items: [
        {
          label: t("sessions.menuSectionMap"),
          children: [
            {
              label: t("sessions.pointsOfSail"),
              children: [
                { label: t("sessions.upwind"), checked: mapShow.upwind,
                  onCheckedChange: (v: boolean) => setMapShow((m) => ({ ...m, upwind: v })) },
                { label: t("sessions.reach"), checked: mapShow.reach,
                  onCheckedChange: (v: boolean) => setMapShow((m) => ({ ...m, reach: v })) },
                { label: t("sessions.downwind"), checked: mapShow.downwind,
                  onCheckedChange: (v: boolean) => setMapShow((m) => ({ ...m, downwind: v })) },
              ],
            },
            {
              label: t("sessions.maneuvers"),
              children: [
                { label: t("sessions.tacks"), checked: mapShow.tack,
                  onCheckedChange: (v: boolean) => setMapShow((m) => ({ ...m, tack: v })) },
                { label: t("sessions.gybes"), checked: mapShow.gybe,
                  onCheckedChange: (v: boolean) => setMapShow((m) => ({ ...m, gybe: v })) },
                { label: t("sessions.course_changes"), checked: mapShow.course_change,
                  onCheckedChange: (v: boolean) => setMapShow((m) => ({ ...m, course_change: v })) },
              ],
            },
          ],
        },
      ],
    });
  }
  // Embedded (solo-activity) sessions are deleted via the activity's own
  // Delete action, which cascades to the session — a separate session-level
  // delete here would leave an orphaned, session-less activity behind.
  if (manager && variant === "page") {
    menuSections.push({ items: [{ label: t("common.delete"), danger: true, onClick: () => setDeleting(true) }] });
  }
  // Embedded mode has no menu of its own — the caller (ActivityDetailPage,
  // for a solo activity) merges these sections into its own single ⋮ menu
  // instead of showing a second, redundant one here. `menuSections` is a
  // fresh array/closures every render (same reasoning as `tracks` above,
  // see `sessionAnalysesKey`), so the effect is gated on a primitive
  // signature of its actual inputs instead of `menuSections` itself —
  // otherwise calling `onMenuSections` would hand the parent a "new" array
  // every render, which (since it's stored in the parent's state) would
  // re-render this component too, rebuilding the array again, forever.
  const menuSignature = JSON.stringify([
    manager,
    maneuverEditMode,
    trimMode,
    reanalyze.isPending,
    reanalysisPolling,
    refreshWind.isPending,
    currentActivity.data?.type,
    analysis.data?.legs.length ?? 0,
    analysis.data?.maneuvers.length ?? 0,
    mapShow,
    variant,
  ]);
  useEffect(() => {
    if (variant === "embedded") onMenuSections?.(menuSections);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- gated on
    // `menuSignature`, not `menuSections`/`onMenuSections`, see comment above.
  }, [menuSignature]);

  if (session.isLoading) return <Spinner />;
  if (!session.data) return null;
  const s = session.data;

  return (
    <div className="sf-section__body">
      {variant === "page" && (
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
          actions={menuSections.length > 0 && <Menu sections={menuSections} />}
        >
          {null}
        </Card>
      )}

      <Card className="sf-card--flush sf-card--flush-top">
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
              variant="session"
              vmg={analysis.data?.vmg_series}
              sessionWind={analysis.data?.true_wind}
              wind={
                tracks[0]?.pts[0]
                  ? { lat: tracks[0].pts[0].lat, lng: tracks[0].pts[0].lon, at: s.started_at }
                  : undefined
              }
              controls={
                <Timeline overlay stepMs={medianIntervalMs(tracks[0]) * 5} />
              }
              placementMode={maneuverEditMode}
              onManeuverPlacement={handleManeuverPlacement}
              pickMode={pickMode}
              onMapClick={onMapClick}
              showBoatInfo={false}
              // Even on this single-track map, the popup's "more info" button
              // is a handy shortcut straight to the analysis section below,
              // rather than scrolling past crew/photos/videos to find it.
              onOpenSession={() =>
                document.getElementById("session-analysis")?.scrollIntoView({ behavior: "smooth" })
              }
            />
            {maneuverEditMode && (
              <p className="sf-muted sf-card__pad">
                {maneuverDraftStart ? t("sessions.maneuverPickEnd") : t("sessions.maneuverPickStart")}
              </p>
            )}
            {trimMode && (
              <div className={`${styles.trimBar} sf-card__pad`}>
                <p className="sf-muted">{t("sessions.trimHint")}</p>
                <div className={styles.trimBarActions}>
                  <Button
                    onClick={applyTrim}
                    disabled={setTrim.isPending || trimDraftStartMs == null || trimDraftEndMs == null}
                  >
                    {t("sessions.applyTrim")}
                  </Button>
                  <Button variant="ghost" onClick={exitTrimMode} disabled={setTrim.isPending}>
                    {t("common.cancel")}
                  </Button>
                </div>
              </div>
            )}
            {mapLegend.length > 0 && (
              <div className={`${legendStyles.mapLegend} sf-card__pad`}>
                {mapLegend.map(([key, label]) => (
                  <span key={key} className={legendStyles.mapLegendItem}>
                    <span className={`${legendStyles.dot} ${MAP_LEGEND_DOT_CLASS[key]}`} />
                    {label}
                  </span>
                ))}
              </div>
            )}
            <div className="sf-section__body sf-card__pad">
              <SpeedChart
                tracks={tracks}
                vmg={analysis.data?.vmg_series}
                trimMode={trimMode}
                trimStartMs={trimDraftStartMs}
                trimEndMs={trimDraftEndMs}
                onTrimStartChange={setTrimDraftStartMs}
                onTrimEndChange={setTrimDraftEndMs}
              />
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
          <div className={photoGridStyles.grid}>
            {photos.data.map((p) => (
              <figure key={p.image_id}>
                <img src={p.url} alt="" />
                <Button
                  variant="danger"
                  className={`sf-btn--sm ${photoGridStyles.del}`}
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
          <div className={photoGridStyles.grid}>
            {videos.data.map((v) => (
              <video key={v.file_id} src={v.url} controls style={{ width: "100%" }} />
            ))}
          </div>
        ) : (
          <p className="sf-muted">{t("common.none")}</p>
        )}
      </Card>

      <div id="session-analysis">
        <SessionAnalysis sessionId={sessionId} editMode={maneuverEditMode} />
      </div>

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
      {movingActivity && (
        <Modal
          title={t("sessions.moveToActivity")}
          onClose={() => {
            setMovingActivity(false);
            setMoveTargetId("");
          }}
        >
          <Select
            label={t("activities.title")}
            id="move-target-activity"
            value={moveTargetId}
            onChange={(e) => setMoveTargetId(e.target.value)}
            required
          >
            <option value="" disabled>
              …
            </option>
            {activityOptions.data
              ?.filter((a) => a.type !== "solo" && a.id !== s.activity_id)
              .map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name ?? fmtDateTime(a.started_at)}
                </option>
              ))}
          </Select>
          <Button disabled={!moveTargetId || moveToActivity.isPending} onClick={() => moveToActivity.mutate()}>
            {t("common.confirm")}
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
