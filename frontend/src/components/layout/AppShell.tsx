import { useEffect } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Capacitor } from "@capacitor/core";
import { Disc, NotebookText, Settings, Users } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useShareTarget } from "@/hooks/useShareTarget";
import { useSwipeNavigation } from "@/hooks/useSwipeNavigation";
import { PULL_TRIGGER_PX, usePullToRefresh } from "@/hooks/usePullToRefresh";
import * as nativeRecording from "@/services/nativeRecording";
import { ToastViewport } from "@/components/ui/ToastViewport";
import { Spinner } from "@/components/ui/Spinner";
import { Avatar } from "@/components/ui/Avatar";
import { ProfileMenu } from "@/components/layout/ProfileMenu";
import { usersService, userKeys } from "@/services/users";
import { unitsStore } from "@/stores/unitsStore";

// The main navigation exposes ONLY the 3 macro-sections (plus Admin) as
// inline links — sub-pages are reached from inside each section
// (docs/frontend-project.md, "Navigazione principale"). Profilo isn't a
// nav link: on desktop it's the avatar dropdown (ProfileMenu), on mobile
// it's the avatar entry in the bottom action bar. Logout lives in the
// ProfileMenu dropdown on desktop and at the bottom of the Profilo page on
// mobile (see ProfiloLayout.tsx).
export function AppShell() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const navigate = useNavigate();
  const { pendingFile } = useShareTarget();

  // Local GPS recordings still waiting to upload (or retrying) — surfaced
  // as a badge on the Registra nav item so it's visible from anywhere in
  // the app, not just while on that page.
  const { recordings: localRecordings, refresh: refreshRecordings } = nativeRecording.useRecordings();
  useEffect(() => {
    refreshRecordings();
  }, [refreshRecordings]);
  const pendingRecordings = localRecordings.filter(
    (r) => r.status === "stopped" || r.status === "failed" || r.status === "uploading",
  ).length;

  // A GPX shared from another app (e.g. Waterspeed) can arrive while the
  // user is anywhere in the app — jump to the import wizard so ImportPage
  // (which also reads useShareTarget()) can pick it up.
  useEffect(() => {
    if (pendingFile) navigate("/diario/activities/import");
  }, [pendingFile, navigate]);
  // Resolved profile_image URL isn't on the auth capabilities payload, only
  // on /users/me — same query key as AnagraficaPage so it's cached, not
  // re-fetched.
  const me = useQuery({
    queryKey: userKeys.me,
    queryFn: usersService.me,
    enabled: !!user,
  });

  // The profile's unit_system is the source of truth; sync it into the
  // local store once loaded so it follows the account across devices.
  useEffect(() => {
    if (me.data?.unit_system && me.data.unit_system !== unitsStore.get()) {
      unitsStore.set(me.data.unit_system);
    }
  }, [me.data?.unit_system]);

  const sections = [
    { to: "/diario", label: t("nav.diario"), Icon: NotebookText },
    // Native-only: recording a GPS track directly from the phone (with the
    // screen locked) has no equivalent on the web, which has no background
    // GPS/foreground-service access — see services/nativeRecording.ts.
    ...(Capacitor.isNativePlatform()
      ? [{ to: "/registra", label: t("nav.registra"), Icon: Disc }]
      : []),
    { to: "/gruppi", label: t("nav.gruppi"), Icon: Users },
    // Icon unused for /profilo (the action bar always shows the Avatar for
    // it instead, see below) — kept only so every section has the same
    // shape.
    { to: "/profilo", label: t("nav.profilo"), Icon: Users },
    ...(user?.is_superadmin
      ? [{ to: "/admin", label: t("nav.admin"), Icon: Settings }]
      : []),
  ];
  const navLinkSections = sections.filter((s) => s.to !== "/profilo");

  // Drag left/right within the page to switch between the action bar's
  // sections, Instagram-tab-style — same order as the bar itself.
  const location = useLocation();
  const mainRef = useSwipeNavigation<HTMLElement>(
    sections.map((s) => s.to),
    location.pathname,
  );

  // Drag down from the top of the page to refetch whatever's currently on
  // screen, Instagram/Twitter-style — native only, see usePullToRefresh.
  const queryClient = useQueryClient();
  const { pull, refreshing } = usePullToRefresh(() => queryClient.refetchQueries({ type: "active" }));

  return (
    <div className="sf-shell">
      <div
        className={`sf-pull-indicator ${refreshing ? "sf-pull-indicator--active" : ""}`}
        style={{ opacity: Math.min(pull / PULL_TRIGGER_PX, 1), transform: `translate(-50%, ${pull}px)` }}
        aria-hidden={!refreshing}
      >
        <Spinner inline />
      </div>
      <header className="sf-navbar">
        <NavLink to="/" className="sf-navbar__brand">
          <img src="/logo.svg" alt="" className="sf-navbar__logo" />
          XGSail
        </NavLink>
        <nav className="sf-navbar__links" aria-label="Main">
          {navLinkSections.map((s) => (
            <NavLink
              key={s.to}
              to={s.to}
              className={`sf-navlink ${s.to === "/admin" ? "sf-navlink--admin" : ""}`}
            >
              {s.label}
              {s.to === "/registra" && pendingRecordings > 0 && <span className="sf-nav-dot" aria-hidden />}
            </NavLink>
          ))}
        </nav>
        <div className="sf-navbar__spacer" />
        <ProfileMenu
          profileImage={me.data?.profile_image ?? null}
          firstName={user?.first_name}
          lastName={user?.last_name}
          email={user?.email}
        />
      </header>
      <main className="sf-main" ref={mainRef}>
        <Outlet />
      </main>
      <nav className="sf-actionbar" aria-label="Main">
        {sections.map((s) => (
          <NavLink key={s.to} to={s.to} className="sf-actionbar__item">
            {s.to === "/profilo" ? (
              <Avatar
                size="sm"
                className="sf-actionbar__avatar"
                profileImage={me.data?.profile_image ?? null}
                firstName={user?.first_name}
                lastName={user?.last_name}
              />
            ) : (
              <span className="sf-actionbar__icon" aria-hidden>
                <s.Icon size={22} strokeWidth={1.75} />
                {s.to === "/registra" && pendingRecordings > 0 && (
                  <span className="sf-nav-dot sf-nav-dot--floating" aria-hidden />
                )}
              </span>
            )}
            <span className="sf-actionbar__label">{s.label}</span>
          </NavLink>
        ))}
      </nav>
      <ToastViewport />
    </div>
  );
}
