import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ImagePlus, NotebookPen, NotebookText, Pencil, Share2, Video } from "lucide-react";
import { ApiError } from "@/api/client";
import { sessionsService, sessionKeys } from "@/services/sessions";
import { activitiesService, activityKeys } from "@/services/activities";
import { boatsService, boatKeys } from "@/services/boats";
import { polarsService, polarKeys } from "@/services/polars";
import { useAuth } from "@/hooks/useAuth";
import { useCapabilities } from "@/hooks/useCapabilities";
import { useStreamJson } from "@/hooks/useStreamJson";
import { useWindAt } from "@/hooks/useWindAt";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { useUnpinnedSectionTabs } from "@/components/layout/SectionLayout";
import { useToast } from "@/hooks/useToast";
import { useAutoSaveOnClose } from "@/hooks/useAutoSaveOnClose";
import { timeController } from "@/stores/timeController";
import { buildTrack, medianIntervalMs, timeBounds, trackColor } from "@/components/race/raceModel";
import { MapView, type MapMark } from "@/components/race/MapView";
import { Timeline } from "@/components/race/Timeline";
import { SpeedChart } from "@/components/race/SpeedChart";
import { PlaybackIndicators } from "@/components/session/PlaybackIndicators";
import { Section } from "@/components/ui/Section";
import { TabList, tabId, tabPanelId, type TabItem } from "@/components/ui/TabList";
import { Button } from "@/components/ui/Button";
import { Menu, type MenuSection } from "@/components/ui/Menu";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { RichText } from "@/components/ui/RichText";
import { SessionNotesEditor } from "@/components/session/SessionNotesEditor";
import { TrimBar } from "@/components/session/TrimBar";
import { Spinner } from "@/components/ui/Spinner";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Avatar } from "@/components/ui/Avatar";
import { UserPicker } from "@/components/common/UserPicker";
import { WindCard } from "@/components/common/WindCard";
import { PhotoGallery, type GalleryPhoto } from "@/components/common/PhotoGallery";
import { SessionAnalysis, analysisParts } from "@/components/session/SessionAnalysis";
import { ShareImageModal } from "@/components/session/ShareImageModal";
import { HealthCard } from "@/components/session/HealthCard";
import { NavSourceModal } from "@/components/session/NavSourceModal";
import { LossBoard } from "@/components/session/LossBoard";
import { NextOuting } from "@/components/session/NextOuting";
import { ReplayProgress } from "@/components/session/ReplayProgress";
import { BackLink } from "@/components/ui/BackLink";
import { SessionHighlights } from "@/components/session/SessionHighlights";
import { sessionLosses } from "@/utils/sessionLosses";
import { highlightsLead } from "@/utils/sessionHighlights";
import { SessionSummaryRow } from "@/components/session/SessionSummaryRow";
import { useMediaUpload } from "@/hooks/useMediaUpload";
import { fmtDateTime, userLabel } from "@/utils/format";
import { legSequence } from "@/utils/legSequence";
import { richTextExcerpt } from "@/utils/richTextExcerpt";
import { sessionStatusBadge } from "@/utils/badges";
import { SAILING_ROLES } from "@/utils/sailingRoles";
import type { GpsPoint, SailingRole, SessionPhoto, UUID } from "@/types";
import photoGridStyles from "@/components/common/photoGrid.module.css";
import legendStyles from "@/components/race/legend.module.css";
import styles from "./SessionDetail.module.css";
import { legLabel } from "./AnalysisLegs";

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

/** A title-bar action — share, the boat's notebook — rendered as a visible
 * button rather than tucked inside the ⋮ menu. */
interface QuickAction {
  key: string;
  icon: ReactNode;
  label: string;
  /** The word shown beside the icon when `labelled`. Must be contained in
   * `label`, which stays the accessible name (WCAG 2.5.3, label in name). */
  shortLabel: string;
  onClick: () => void;
}

/** Renders a QuickAction list as ghost buttons: icon-only with a tooltip, or
 * `labelled` with a short visible word. */
function QuickActionButtons({ actions, labelled = false }: { actions: QuickAction[]; labelled?: boolean }) {
  return (
    <>
      {actions.map((a) => (
        <Button
          key={a.key}
          type="button"
          variant="ghost"
          className={labelled ? "sf-btn--sm" : "sf-btn--icon-sm"}
          aria-label={a.label}
          title={a.label}
          onClick={a.onClick}
        >
          {a.icon}
          {labelled && <span>{a.shortLabel}</span>}
        </Button>
      ))}
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
 *
 * The page owns its title bar in both variants; an embedding page supplies
 * its own `heading`, merges its actions into the one ⋮ menu through
 * `menuBefore`/`menuAfter`, and puts its own details (`details`) at the top of
 * the Analisi tab. */
export function SessionDetail({
  sessionId,
  variant = "page",
  extraMarks = [],
  pickMode = false,
  onMapClick,
  back,
  heading,
  menuBefore = [],
  menuAfter = [],
  details,
  mapOverlay,
}: {
  sessionId: UUID;
  variant?: "page" | "embedded";
  extraMarks?: MapMark[];
  pickMode?: boolean;
  onMapClick?: (lat: number, lng: number) => void;
  /** The way out: an icon in the title bar on a phone, a link above it on a
   * wide screen. */
  back: { fallback: string; label: string };
  /** "embedded": the caller's own name and dates in place of the boat's. */
  heading?: { title: ReactNode; meta: ReactNode };
  /** "embedded": the caller's actions, around this page's in the one ⋮. */
  menuBefore?: MenuSection[];
  menuAfter?: MenuSection[];
  /** "embedded": the caller's details, the first block of the Analisi tab. */
  details?: ReactNode;
  /** The caller's own map control (the activity's course marks), stacked
   * with the map's controls; kept in a slot of its own with no map. */
  mapOverlay?: ReactNode;
}) {
  const { t } = useTranslation();
  // Below the two-column breakpoint (matching SessionDetail.module.css) the
  // title bar, replay and tabs are pinned chrome, and space is short.
  const pinnedOnTop = useMediaQuery("(max-width: 999px)");
  const { isBoatManager } = useCapabilities();
  const { user } = useAuth();
  const { notify, update } = useToast();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [addingCrew, setAddingCrew] = useState(false);
  const [removingCrewId, setRemovingCrewId] = useState<UUID | null>(null);
  const [crewRole, setCrewRole] = useState<SailingRole>("crew");
  const [notesForm, setNotesForm] = useState({ notes: "", notes_shared: false });
  const originalNotesFormRef = useRef(notesForm);
  // The ref above tracks *last saved* — it's refreshed by every successful
  // autosave and by the server-sync effect below. Discarding has to restore
  // what the editor was opened with, so it gets its own snapshot, taken once
  // in `openNotes` and never refreshed.
  const openedNotesRef = useRef(notesForm);
  const [notesEditing, setNotesEditing] = useState(false);
  const openNotes = () => {
    openedNotesRef.current = notesForm;
    setNotesEditing(true);
  };
  const [deleting, setDeleting] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [pickingNavSource, setPickingNavSource] = useState(false);
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
  // Owned here (not inside the photo/video Sections) so the same file picker
  // can be triggered either from the Section's own icon button (once there's
  // content) or from the "Aggiungi" menu item (while the section is empty
  // and hidden) — see the ⋮ menu section built below.
  const photoInputRef = useRef<HTMLInputElement>(null);
  const videoInputRef = useRef<HTMLInputElement>(null);

  const session = useQuery({
    queryKey: sessionKeys.detail(sessionId),
    queryFn: () => sessionsService.get(sessionId),
    enabled: !!sessionId,
  });
  // `notes` is only present on the payload when the caller may see it (crew/
  // boat manager, or shared — see backend `_session_payload`), so this stays
  // empty for a viewer with read-only access to someone else's shared note.
  useEffect(() => {
    // Skipped while the modal is open: a periodic autosave invalidates this
    // same query, and if the refetch landed while the user kept typing, this
    // would roll the field back to the just-saved (now stale) text.
    if (notesEditing) return;
    if (session.data?.notes !== undefined) {
      const next = {
        notes: session.data.notes ?? "",
        notes_shared: session.data.notes_shared ?? false,
      };
      setNotesForm(next);
      originalNotesFormRef.current = next;
    }
  }, [session.data?.notes, session.data?.notes_shared, notesEditing]);
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
  // HealthCard's own query (deduped) — read here only so the section index
  // links to it exactly when it renders.
  const physio = useQuery({
    queryKey: sessionKeys.physio(sessionId),
    queryFn: () => sessionsService.physio(sessionId),
    enabled: !!sessionId,
  });
  // Fetched by id rather than via boatsService.list(), which excludes guest
  // boats by design (see backend SqlBoatRepo.list) — a guest boat used in
  // this session must still resolve to its real name/photo here.
  const boatId = session.data?.boat_id;
  const boat = useQuery({
    queryKey: boatKeys.detail(boatId!),
    queryFn: () => boatsService.get(boatId!),
    enabled: !!boatId,
  });
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

  // Just to know whether this session even has a track to choose (a boat
  // tracker plus a crew watch, say) — returns [] with a single one, and without
  // `quality` it's a DB-only question, no series read. The picker itself asks
  // for the quality metrics.
  const navSources = useQuery({
    queryKey: sessionKeys.navSources(sessionId),
    queryFn: () => sessionsService.navSources(sessionId),
    enabled: !!sessionId,
  });

  // The gps stream JSON lives in object storage — fetched via its download_url
  // (see useStreamJson). `subject_type: "boat"` picks the boat's own track when
  // crew wearables contributed their own GPS to the same session; which of
  // several boat tracks wins is the backend's call (services/nav_source.py),
  // and it only ever exposes the resolved one.
  const gps = useStreamJson<GpsPoint>(streams.data, "gps");

  // The boat's actual name/photo (not the generic "Playback" track label) —
  // shown in the map popup, so it needs the real boat even on this
  // single-track map.
  const trackBoatName = boat.data?.name ?? t("sessions.playback");
  const trackBoatImageUrl = boat.data?.photos[0]?.url;
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
          mark_role: legLabel(t, l),
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
      if (mk.kind === "leg" && mk.legType) seen.set(`leg-${mk.legType}`, t(`sessions.${mk.legType}`));
      else if ((mk.kind === "maneuver" || mk.kind === "maneuver-pending") && mk.maneuverType) {
        seen.set(mk.maneuverType, mk.mark_role);
      }
    }
    return order.filter((key) => seen.has(key)).map((key) => [key, seen.get(key)!] as const);
  }, [marks, t]);

  const addCrew = useMutation({
    mutationFn: (userId: UUID) =>
      sessionsService.addCrew(sessionId, { user_id: userId, sailing_role: crewRole }),
    onSuccess: async () => {
      setAddingCrew(false);
      setCrewRole("crew");
      await queryClient.invalidateQueries({ queryKey: sessionKeys.crew(sessionId) });
    },
    onError: (err) => notify(err instanceof ApiError ? err.detail : t("errors.generic"), "error"),
  });
  const removeCrew = useMutation({
    mutationFn: (userId: UUID) => sessionsService.removeCrew(sessionId, userId),
    onSuccess: () => {
      setRemovingCrewId(null);
      return queryClient.invalidateQueries({ queryKey: sessionKeys.crew(sessionId) });
    },
  });
  const updateCrewRole = useMutation({
    mutationFn: ({ userId, role }: { userId: UUID; role: SailingRole }) =>
      sessionsService.updateCrewRole(sessionId, userId, { sailing_role: role }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: sessionKeys.crew(sessionId) }),
    onError: (err) => notify(err instanceof ApiError ? err.detail : t("errors.generic"), "error"),
  });
  const saveNotes = useMutation({
    mutationFn: () =>
      sessionsService.updateNotes(sessionId, {
        notes: notesForm.notes || null,
        notes_shared: notesForm.notes_shared,
      }),
    onSuccess: async () => {
      originalNotesFormRef.current = notesForm;
      await queryClient.invalidateQueries({ queryKey: sessionKeys.detail(sessionId) });
    },
    // No onError here: `useAutoSaveOnClose` below is the single place that
    // surfaces a save failure (on close) or retries silently (periodic) —
    // an onError here too would double the toast on every close-time failure.
  });
  const discardNotes = async () => {
    const opened = openedNotesRef.current;
    await sessionsService.updateNotes(sessionId, {
      notes: opened.notes || null,
      notes_shared: opened.notes_shared,
    });
    await queryClient.invalidateQueries({ queryKey: sessionKeys.detail(sessionId) });
  };
  const {
    requestClose: requestCloseNotes,
    discardAction: notesDiscardAction,
    discardDialog: notesDiscardDialog,
  } = useAutoSaveOnClose({
    canSave: () => true, // an emptied note is a valid, save-worthy state
    isDirty: () =>
      notesForm.notes !== originalNotesFormRef.current.notes ||
      notesForm.notes_shared !== originalNotesFormRef.current.notes_shared,
    save: () => saveNotes.mutateAsync(),
    onClosed: () => setNotesEditing(false),
    // The session's note row always exists already, so discarding only reverts.
    discard: { destroysRecord: () => false, run: discardNotes },
  });
  const removeSession = useMutation({
    mutationFn: () => sessionsService.remove(sessionId),
    onSuccess: () => navigate(session.data ? `/diario/activities/${session.data.activity_id}` : "/diario/personale"),
    onError: (err) => notify(err instanceof ApiError ? err.detail : t("errors.generic"), "error"),
  });
  const moveToActivity = useMutation({
    mutationFn: () => sessionsService.attachToActivity(sessionId, moveTargetId as UUID),
    onSuccess: async (updated) => {
      setMovingActivity(false);
      setMoveTargetId("");
      await queryClient.invalidateQueries({ queryKey: sessionKeys.detail(sessionId) });
      navigate(`/diario/activities/${updated.activity_id}/barche/${sessionId}`);
    },
    onError: (err) => notify(err instanceof ApiError ? err.detail : t("errors.generic"), "error"),
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
    onError: (err) => notify(err instanceof ApiError ? err.detail : t("errors.generic"), "error"),
  });
  const refreshWind = useMutation({
    mutationFn: () => sessionsService.refreshWind(sessionId),
    onSuccess: startReanalysisPolling,
    onError: (err) => notify(err instanceof ApiError ? err.detail : t("errors.generic"), "error"),
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
    onError: (err) => notify(err instanceof ApiError ? err.detail : t("errors.generic"), "error"),
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
    onError: (err) => notify(err instanceof ApiError ? err.detail : t("errors.generic"), "error"),
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
  // Presign/PUT/confirm flow for the hidden file inputs above — same hook
  // `ImageUploader`/the old inline `VideoUploader` used, called directly so
  // the trigger isn't tied to any one visible button (see photoInputRef/
  // videoInputRef).
  const photoUpload = useMediaUpload({
    create: () => sessionsService.createPhoto(sessionId),
    confirm: (imageId) => sessionsService.confirmPhoto(sessionId, imageId),
    onDone: async () => {
      await queryClient.invalidateQueries({ queryKey: sessionKeys.photos(sessionId) });
    },
  });
  const videoUpload = useMediaUpload({
    create: () => sessionsService.createVideo(sessionId),
    confirm: (fileId) => sessionsService.confirmVideo(sessionId, fileId),
    onDone: async () => {
      await queryClient.invalidateQueries({ queryKey: sessionKeys.videos(sessionId) });
    },
  });
  // No inline error UI once the trigger can live in the ⋮ menu (nothing to
  // anchor it to) — reuse the toast pattern the rest of this file already
  // uses for mutation errors.
  useEffect(() => {
    if (photoUpload.error) notify(t("errors.generic"), "error");
  }, [photoUpload.error, notify, t]);
  useEffect(() => {
    if (videoUpload.error) notify(t("errors.generic"), "error");
  }, [videoUpload.error, notify, t]);

  const manager = session.data ? isBoatManager(session.data.boat_id) : false;
  // Mirrors the backend's is_session_crew_or_manager: who can write the
  // shared crew notes and add photos/videos (a superset of who can edit the
  // session's core fields, since any crew member — not just a boat owner/
  // admin — should be able to log the outing).
  const crewOrManager = manager || (crew.data?.some((c) => c.user_id === user?.id) ?? false);

  // Mirrors the backend's delete_photo rule exactly (backend/routers/
  // sessions.py): the photo's own uploader, or a boat owner/admin — never a
  // plain crew member on someone else's shot, which the server would 403.
  const sessionGalleryPhotos = useMemo<GalleryPhoto[]>(
    () =>
      (photos.data ?? []).map((p) => ({
        id: p.image_id,
        url: p.url,
        caption: p.user ? t("sessions.photoBy", { name: userLabel(p.user) }) : undefined,
        subtitle: fmtDateTime(p.created_at),
        onDelete: p.created_by === user?.id || manager ? () => removePhoto.mutate(p.image_id) : undefined,
      })),
    [photos.data, manager, user?.id, removePhoto, t],
  );

  // Single consolidated ⋮ menu (title-level) — replaces the old separate
  // OptionsMenu (session actions) + MapLegsOptions (⚙ on the map). Sections
  // absent for a non-manager viewer: only "Mostra su mappa" (always visible
  // to anyone who can see the analysis) and GPX download (visible to any
  // viewer — matches the backend's _require_visible permission, not the
  // edit-only _can_edit the other actions use).
  const menuSections: MenuSection[] = [...menuBefore];
  const openNotebook = () =>
    navigate(`/profilo/barche/${session.data?.boat_id}/quaderno`, {
      state: { backLabel: t("boatNotes.backToSession") },
    });
  // Share stays in this component because ShareImageModal needs its tracks/
  // stats/crew. The notebook, always relevant to whoever manages the boat,
  // is a visible button on a wide screen and a ⋮ item in a phone's title bar.
  const titleActions: QuickAction[] = [];
  if (manager && !pinnedOnTop) {
    titleActions.push({
      key: "notebook",
      icon: <NotebookText size={16} />,
      label: t("sessions.openBoatNotebook"),
      shortLabel: t("sessions.actionShort.notebook"),
      onClick: openNotebook,
    });
  }
  titleActions.push({
    key: "share",
    icon: <span className={styles.shareIcon}><Share2 size={pinnedOnTop ? 18 : 16} /></span>,
    label: t("sessions.share"),
    shortLabel: t("sessions.share"),
    onClick: () => setSharing(true),
  });
  if (manager && pinnedOnTop) {
    menuSections.push({ items: [{ label: t("sessions.openBoatNotebook"), onClick: openNotebook }] });
  }
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
      // Only when there's actually a choice: with one recording device — the
      // overwhelmingly common case — the endpoint returns nothing and this
      // stays out of the way.
      //
      // Crew, not just managers (mirrors is_session_crew_or_manager): when two
      // people aboard both recorded, the shared session usually sits in one of
      // their private solo activities, and a manager-only gate would leave the
      // other unable to touch the track they contributed — or to separate it.
      ...(crewOrManager && (navSources.data?.length ?? 0) > 1
        ? [
            {
              label: t("sessions.navSource.choose"),
              onClick: () => setPickingNavSource(true),
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
  // Delete action (in `menuAfter`), which cascades to the session — a
  // session-level delete there would leave a session-less activity behind.
  if (manager && variant === "page") {
    menuSections.push({ items: [{ label: t("common.delete"), danger: true, onClick: () => setDeleting(true) }] });
  }
  menuSections.push(...menuAfter);

  const losses = useMemo(
    () => (analysis.data ? sessionLosses(analysis.data.legs, analysis.data.maneuvers) : []),
    [analysis.data],
  );
  // The five worst moments, numbered on the speed strip in ranking order so a
  // dip in the line and its row in "Where you lost" carry the same number.
  const lossMarkers = useMemo(
    () => losses.slice(0, 5).map((l, i) => ({ ms: l.atSec * 1000, label: String(i + 1) })),
    [losses],
  );
  // The session's cover is its oldest photo, same rule as the diary entry's.
  const coverPhoto = useMemo(
    () =>
      (photos.data ?? []).reduce<SessionPhoto | null>(
        (a, b) => (!a || b.created_at < a.created_at ? b : a),
        null,
      ),
    [photos.data],
  );

  // The replay and the tab bar pin to the top of a phone; the section's own
  // tabs above would leave too little screen, so they scroll away here.
  useUnpinnedSectionTabs();
  const [searchParams, setSearchParams] = useSearchParams();
  // Both deduped against SessionAnalysis/WindCard's own queries — read here
  // only to offer the Wind tab exactly when it has something to show.
  const polar = useQuery({
    queryKey: polarKeys.session(sessionId),
    queryFn: () => polarsService.forSession(sessionId),
    enabled: !!sessionId,
  });
  const startPoint = tracks[0]?.pts[0];
  const windAtStart = useWindAt(startPoint?.lat, startPoint?.lon, session.data?.started_at);

  // The tab bar pins right under the replay on a phone, and a panel needs
  // enough height to keep both pinned; both depend on the replay's measured
  // height (the map, plus a legend or trim bar when shown).
  const stageRef = useRef<HTMLDivElement>(null);
  const replayRef = useRef<HTMLDivElement>(null);
  const tabBarRef = useRef<HTMLDivElement>(null);
  const tabsColumnRef = useRef<HTMLDivElement>(null);
  const titleBarRef = useRef<HTMLElement>(null);
  const hasReplay = !!session.data && tracks.length > 0;
  useEffect(() => {
    const stage = stageRef.current;
    const replay = replayRef.current;
    const bar = tabBarRef.current;
    const title = titleBarRef.current;
    if (!stage || !replay || !bar || !title) return;
    const measure = () => {
      stage.style.setProperty("--titlebar-h", `${title.offsetHeight}px`);
      stage.style.setProperty("--replay-h", `${replay.offsetHeight}px`);
      stage.style.setProperty("--tabbar-h", `${bar.offsetHeight}px`);
    };
    const observer = new ResizeObserver(measure);
    observer.observe(title);
    observer.observe(replay);
    observer.observe(bar);
    return () => observer.disconnect();
  }, [!!session.data, hasReplay]);

  // On a phone the replay folds (shorter map, the strip down to a progress
  // bar) once the panel has scrolled a little under it, and unfolds back at
  // the top. Two discrete states, switched from a passive, rAF-throttled
  // scroll listener with hysteresis; CSS animates between them. How far the
  // panel has gone under the pinned chrome does not depend on the replay's
  // own height, so the switch cannot feed back into itself.
  const [collapsed, setCollapsed] = useState(false);
  useEffect(() => {
    if (!pinnedOnTop || !hasReplay) {
      setCollapsed(false);
      return;
    }
    let frame = 0;
    const check = () => {
      frame = 0;
      const stage = stageRef.current;
      const title = titleBarRef.current;
      if (!stage || !title) return;
      const under = title.getBoundingClientRect().bottom - stage.getBoundingClientRect().top;
      setCollapsed((was) => (was ? under > 8 : under > 48));
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(check);
    };
    check();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      cancelAnimationFrame(frame);
    };
  }, [pinnedOnTop, hasReplay]);

  if (session.isLoading) return <Spinner />;
  if (!session.data) return null;
  const s = session.data;

  const parts = analysis.data ? analysisParts(analysis.data, maneuverEditMode) : null;
  const hasNotes = !!richTextExcerpt(s.notes, 1);
  const photoCount = photos.data?.length ?? 0;
  // A tab shows when it has something in it, or an add action this viewer
  // may use; Analysis always shows, it is where the page opens.
  const tabs: TabItem[] = [{ id: "analisi", label: t("sessions.tabs.analysis") }];
  if (parts?.wind || polar.data?.length || windAtStart.data) {
    tabs.push({ id: "vento", label: t("sessions.tabs.wind") });
  }
  if (crew.data?.length || hasNotes || physio.data?.length || crewOrManager) {
    tabs.push({
      id: "equipaggio",
      label: t("sessions.tabs.crew"),
      // Health only mounts with this tab open, so the tour points here.
      dataTour: physio.data?.length ? "activity-health" : undefined,
    });
  }
  const mediaCount = photoCount + (videos.data?.length ?? 0);
  if (mediaCount || crewOrManager) {
    tabs.push({
      id: "foto",
      label: (
        <>
          {t("sessions.tabs.photos")}
          {mediaCount > 0 && <span className={styles.tabCount}>{mediaCount}</span>}
        </>
      ),
    });
  }
  const requestedTab = searchParams.get("tab");
  const activeTab = tabs.some((tab) => tab.id === requestedTab) ? requestedTab! : "analisi";
  // Replace, not push: switching tabs is not a page the back button should
  // step through, but reload and a shared link keep the tab.
  const selectTab = (id: string, reveal = false) => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (id === "analisi") next.delete("tab");
        else next.set("tab", id);
        return next;
      },
      { replace: true },
    );
    // Once the tab bar is pinned, a new tab starts at its top rather than
    // wherever the last one had been scrolled to; `reveal` scrolls there from
    // anywhere. The bar's sticky offset is where it pins.
    const column = tabsColumnRef.current;
    const bar = tabBarRef.current;
    if (!column || !bar) return;
    const pinAt = parseFloat(getComputedStyle(bar).top) || 0;
    const top = column.getBoundingClientRect().top;
    if (reveal || top < pinAt) window.scrollTo({ top: window.scrollY + top - pinAt });
  };

  const stepMs = tracks[0] ? medianIntervalMs(tracks[0]) * 5 : 5000;
  const lossBoard = analysis.data && <LossBoard legs={analysis.data.legs} maneuvers={analysis.data.maneuvers} />;
  const highlights = analysis.data && (
    <SessionHighlights
      legs={analysis.data.legs}
      maneuvers={analysis.data.maneuvers}
      maxSpeedKts={stats.data?.max_speed_kts}
      points={tracks[0]?.pts ?? []}
    />
  );
  // A clean day opens on what went well; otherwise the losses keep the lead
  // and the good part follows them.
  const leadWithHighlights = highlightsLead(
    losses.reduce((sum, l) => sum + l.lostM, 0),
    stats.data?.distance_m,
  );

  return (
    <div className={`sf-section__body ${styles.root}`}>
      <input
        ref={photoInputRef}
        type="file"
        accept="image/*"
        multiple
        hidden
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          e.target.value = "";
          if (files.length === 0) return;
          void photoUpload.uploadMany(files).then(({ failed, firstError }) => {
            if (failed === 0) return;
            // 409 is the per-session photo cap (auth/permissions.py's
            // session_photo_limit) — a count of failures wouldn't say so.
            const capped = firstError instanceof ApiError && firstError.status === 409;
            notify(
              capped
                ? t("sessions.photoLimitReached")
                : t("sessions.photoUploadPartial", { count: failed }),
              "error",
            );
          });
        }}
      />
      <input
        ref={videoInputRef}
        type="file"
        accept="video/mp4"
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) void videoUpload.upload(f);
          e.target.value = "";
        }}
      />
      {/* Rendered unconditionally (not gated on `variant`) so a batch upload
          triggered from the embedded activity view is just as visible as one
          from the standalone session page. */}
      {photoUpload.progress && (
        <p className="sf-muted">
          <Spinner inline />{" "}
          {t("sessions.photoUploading", { done: photoUpload.progress.done, total: photoUpload.progress.total })}
        </p>
      )}
      <header ref={titleBarRef} className={styles.titleBar}>
        <BackLink fallback={back.fallback} label={back.label} iconOnly={pinnedOnTop} className={styles.back} />
        <div className={styles.titleRow}>
          {coverPhoto && (
            <button
              type="button"
              className={styles.cover}
              aria-label={t("sessions.coverPhoto", { count: photoCount })}
              title={t("sessions.coverPhoto", { count: photoCount })}
              onClick={() => selectTab("foto", true)}
            >
              <img src={coverPhoto.url} alt="" />
              {photoCount > 1 && (
                <span className={styles.coverCount} aria-hidden="true">{photoCount}</span>
              )}
            </button>
          )}
          <div className={styles.titleText}>
            <h1 className={`sf-page-title ${styles.title}`}>{heading?.title ?? boat.data?.name ?? t("sessions.boat")}</h1>
            <p className={styles.meta}>
              {heading?.meta ?? <time dateTime={s.started_at ?? undefined}>{fmtDateTime(s.started_at)}</time>}
              {/* A processed session is the normal case — only a state that
                  needs attention earns a tag next to the date. */}
              {reanalysisPolling ? (
                <span className="sf-badge sf-badge--pending">
                  <Spinner inline /> {t("sessions.reanalyzing")}
                </span>
              ) : (
                s.status !== "processed" && <span className={sessionStatusBadge(s.status)}>{s.status}</span>
              )}
            </p>
          </div>
          <div className={styles.titleActions} data-tour="activity-quick-actions">
            <QuickActionButtons actions={titleActions} labelled={!pinnedOnTop} />
          </div>
          <Menu
            sections={menuSections}
            triggerDataTour="activity-menu"
            triggerLabel={pinnedOnTop ? undefined : t("sessions.actionShort.more")}
          />
        </div>
      </header>

      <div ref={stageRef} className={`${styles.stage} ${collapsed ? styles.collapsed : ""}`}>
        <div ref={replayRef} className={hasReplay ? styles.replay : undefined}>
          {streams.isLoading || gps === null ? (
            <Spinner />
          ) : tracks.length === 0 ? (
            <>
              <p className="sf-muted">{t("sessions.noGps")}</p>
              {/* With no map to lay it on, the caller's control keeps a slot. */}
              {mapOverlay && <div className={styles.overlaySlot}>{mapOverlay}</div>}
            </>
          ) : (
            <>
              <div className={`sf-bleed ${styles.mapSlot}`} data-tour="activity-map">
                <MapView
                  nautical
                  tracks={tracks}
                  marks={marks}
                  variant="session"
                  compact={collapsed}
                  mapOptions={mapOverlay}
                  vmg={analysis.data?.vmg_series}
                  sessionWind={analysis.data?.true_wind}
                  wind={startPoint ? { lat: startPoint.lat, lng: startPoint.lon, at: s.started_at } : undefined}
                  placementMode={maneuverEditMode}
                  onManeuverPlacement={handleManeuverPlacement}
                  pickMode={pickMode}
                  onMapClick={onMapClick}
                  showBoatInfo={false}
                  onOpenSession={() => selectTab("analisi", true)}
                />
              </div>
              {/* The scrubber: transport above the speed strip, under the map
                  rather than on it. On a phone the strip folds to a slim
                  progress bar while the panel is scrolled. */}
              <Timeline stepMs={stepMs} className={styles.transport} />
              <div className={styles.scrub} data-tour="activity-speed-chart">
                <div className={styles.scrubChart}>
                  <SpeedChart
                    tracks={tracks}
                    vmg={analysis.data?.vmg_series}
                    markers={lossMarkers}
                    compact={pinnedOnTop}
                    trimMode={trimMode}
                    trimStartMs={trimDraftStartMs}
                    trimEndMs={trimDraftEndMs}
                    onTrimStartChange={setTrimDraftStartMs}
                    onTrimEndChange={setTrimDraftEndMs}
                  />
                </div>
                {pinnedOnTop && (
                  <div className={styles.scrubBar}>
                    <ReplayProgress markers={lossMarkers} stepMs={stepMs} label={t("sessions.replayPosition")} />
                  </div>
                )}
              </div>
              {maneuverEditMode && (
                <p className="sf-muted">
                  {maneuverDraftStart ? t("sessions.maneuverPickEnd") : t("sessions.maneuverPickStart")}
                </p>
              )}
              {trimMode && trimDraftStartMs != null && trimDraftEndMs != null && (
                <TrimBar
                  startMs={trimDraftStartMs}
                  endMs={trimDraftEndMs}
                  onStartChange={setTrimDraftStartMs}
                  onEndChange={setTrimDraftEndMs}
                  onApply={applyTrim}
                  onCancel={exitTrimMode}
                  busy={setTrim.isPending}
                />
              )}
              {mapLegend.length > 0 && (
                <div className={legendStyles.mapLegend}>
                  {mapLegend.map(([key, label]) => (
                    <span key={key} className={legendStyles.mapLegendItem}>
                      <span className={`${legendStyles.dot} ${MAP_LEGEND_DOT_CLASS[key]}`} />
                      {label}
                    </span>
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        <div ref={tabsColumnRef} className={styles.tabsColumn}>
          <div ref={tabBarRef} className={styles.tabBar}>
            <TabList
              tabs={tabs}
              active={activeTab}
              onChange={(id) => selectTab(id)}
              label={t("sessions.tabs.label")}
              idPrefix="session"
              className={styles.tabList}
            />
          </div>
          <div
            role="tabpanel"
            id={tabPanelId("session", activeTab)}
            aria-labelledby={tabId("session", activeTab)}
            className={`sf-section__body ${styles.panel}`}
          >
            {activeTab === "analisi" && (
              <>
                {details}
                {stats.data && (
                  <div data-tour="activity-stats">
                    <SessionSummaryRow
                      stats={stats.data}
                      maneuverCount={analysis.data?.maneuvers.filter((m) => !m.rejected).length}
                    />
                  </div>
                )}
                {/* The readouts at the replay cursor: under the totals rather
                    than pinned, where they would cost the panel a row. */}
                {tracks.length > 0 && <PlaybackIndicators track={tracks[0]} vmg={analysis.data?.vmg_series} />}
                {analysis.data && tracks.length > 0 && (
                  <div className={styles.ranking}>
                    {leadWithHighlights ? highlights : lossBoard}
                    {leadWithHighlights ? lossBoard : highlights}
                  </div>
                )}
                {analysis.data && <NextOuting legs={analysis.data.legs} maneuvers={analysis.data.maneuvers} />}
                <div data-tour="activity-analysis">
                  <SessionAnalysis
                    sessionId={sessionId}
                    part="performance"
                    editMode={maneuverEditMode}
                    maxSpeedKts={stats.data?.max_speed_kts}
                    onRefreshWind={manager ? () => refreshWind.mutate() : undefined}
                    refreshingWind={refreshWind.isPending || reanalysisPolling}
                  />
                </div>
              </>
            )}

            {activeTab === "vento" && (
              <>
                <SessionAnalysis sessionId={sessionId} part="wind" />
                {startPoint && <WindCard lat={startPoint.lat} lng={startPoint.lon} at={s.started_at} />}
              </>
            )}

            {activeTab === "equipaggio" && (
              <>
                <Section
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
                      {crew.data.map((c) => {
                        // Mirrors the backend rule exactly (PATCH /sessions/{id}/crew/{user_id}):
                        // a manager, or the crew member correcting their own role.
                        const canEditRole = manager || c.user_id === user?.id;
                        return (
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
                                {canEditRole ? (
                                  <select
                                    className="sf-badge sf-badge--select"
                                    value={c.sailing_role}
                                    disabled={updateCrewRole.isPending}
                                    onChange={(e) =>
                                      updateCrewRole.mutate({ userId: c.user_id, role: e.target.value as SailingRole })
                                    }
                                  >
                                    {SAILING_ROLES.map((role) => (
                                      <option key={role} value={role}>
                                        {t(`sessions.sailingRoles.${role}`)}
                                      </option>
                                    ))}
                                  </select>
                                ) : (
                                  <span className="sf-badge">{t(`sessions.sailingRoles.${c.sailing_role}`)}</span>
                                )}
                              </span>
                            </span>
                            {manager && (
                              <Button
                                variant="ghost"
                                className="sf-btn--sm"
                                onClick={() => setRemovingCrewId(c.user_id)}
                              >
                                {t("common.remove")}
                              </Button>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <p className="sf-muted">{t("common.none")}</p>
                  )}
                </Section>

                {(hasNotes || crewOrManager) && (
                  <Section
                    title={
                      <>
                        {t("sessions.notes")}{" "}
                        {hasNotes && s.notes_shared && <span className="sf-badge">{t("sessions.notesSharedBadge")}</span>}
                      </>
                    }
                    actions={
                      hasNotes && crewOrManager && (
                        <Button
                          type="button"
                          variant="ghost"
                          className="sf-btn--icon-sm"
                          aria-label={t("common.edit")}
                          title={t("common.edit")}
                          onClick={openNotes}
                        >
                          <Pencil size={16} />
                        </Button>
                      )
                    }
                  >
                    {hasNotes ? (
                      <RichText html={s.notes} tier="full" />
                    ) : (
                      <div>
                        <Button type="button" variant="ghost" className="sf-btn--sm" onClick={openNotes}>
                          <NotebookPen size={16} />
                          {t("sessions.addNotes")}
                        </Button>
                      </div>
                    )}
                  </Section>
                )}

                {/* Renders nothing unless this viewer may see someone's health
                    data — see HealthCard, which also handles the multi-crew case. */}
                <HealthCard sessionId={sessionId} />
              </>
            )}

            {activeTab === "foto" && (
              <>
                {(photoCount > 0 || crewOrManager) && (
                  <Section
                    title={t("sessions.photos")}
                    actions={
                      photoCount > 0 && crewOrManager && (
                        <Button
                          type="button"
                          variant="ghost"
                          className="sf-btn--icon-sm"
                          disabled={photoUpload.busy}
                          aria-label={t("sessions.addPhoto")}
                          title={t("sessions.addPhoto")}
                          onClick={() => photoInputRef.current?.click()}
                        >
                          <ImagePlus size={16} />
                        </Button>
                      )
                    }
                  >
                    {photoCount > 0 ? (
                      <PhotoGallery photos={sessionGalleryPhotos} />
                    ) : (
                      <div className={styles.emptyAdd}>
                        <p className="sf-muted">{t("sessions.noPhotos")}</p>
                        <Button
                          type="button"
                          variant="ghost"
                          className="sf-btn--sm"
                          disabled={photoUpload.busy}
                          onClick={() => photoInputRef.current?.click()}
                        >
                          <ImagePlus size={16} />
                          {t("sessions.addPhoto")}
                        </Button>
                      </div>
                    )}
                  </Section>
                )}

                {(videos.data?.length || crewOrManager) && (
                  <Section
                    title={t("sessions.videos")}
                    actions={
                      !!videos.data?.length && crewOrManager && (
                        <Button
                          type="button"
                          variant="ghost"
                          className="sf-btn--icon-sm"
                          disabled={videoUpload.busy}
                          aria-label={t("sessions.addVideo")}
                          title={t("sessions.addVideo")}
                          onClick={() => videoInputRef.current?.click()}
                        >
                          <Video size={16} />
                        </Button>
                      )
                    }
                  >
                    {videos.data?.length ? (
                      <div className={photoGridStyles.grid}>
                        {videos.data.map((v) => (
                          <video key={v.file_id} src={v.url} controls style={{ width: "100%" }} />
                        ))}
                      </div>
                    ) : (
                      <div className={styles.emptyAdd}>
                        <p className="sf-muted">{t("sessions.noVideos")}</p>
                        <Button
                          type="button"
                          variant="ghost"
                          className="sf-btn--sm"
                          disabled={videoUpload.busy}
                          onClick={() => videoInputRef.current?.click()}
                        >
                          <Video size={16} />
                          {t("sessions.addVideo")}
                        </Button>
                      </div>
                    )}
                  </Section>
                )}
              </>
            )}
          </div>
        </div>
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
      {notesEditing && (
        <Modal
          title={t("sessions.notes")}
          onClose={requestCloseNotes}
          size="wide"
          fillBody
          headerActions={notesDiscardAction}
        >
          <SessionNotesEditor
            id="session-notes"
            value={notesForm.notes}
            onChange={(html) => setNotesForm((f) => ({ ...f, notes: html }))}
            shared={notesForm.notes_shared}
            onSharedChange={(notes_shared) => setNotesForm((f) => ({ ...f, notes_shared }))}
          />
        </Modal>
      )}
      {notesDiscardDialog}
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
      {removingCrewId && (
        <ConfirmDialog
          title={t("common.remove")}
          message={t("sessions.removeCrewConfirm", {
            name: userLabel(crew.data?.find((c) => c.user_id === removingCrewId)?.user),
          })}
          busy={removeCrew.isPending}
          onConfirm={() => removeCrew.mutate(removingCrewId)}
          onClose={() => setRemovingCrewId(null)}
        />
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
      {sharing && (
        <ShareImageModal
          data={{
            boatName: boat.data?.name ?? t("sessions.boat"),
            boatPhotoUrl: boat.data?.photos[0]?.url ?? null,
            track: tracks[0] ?? null,
            startedAt: s.started_at,
            stats: stats.data ?? null,
            crew: crew.data ?? [],
          }}
          sessionPhotos={photos.data ?? []}
          onClose={() => setSharing(false)}
        />
      )}
      {pickingNavSource && (
        <NavSourceModal
          sessionId={sessionId}
          canEdit={crewOrManager}
          onClose={() => setPickingNavSource(false)}
        />
      )}
    </div>
  );
}
