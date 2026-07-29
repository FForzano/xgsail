import { useEffect } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Disc, NotebookText, Settings, Users } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useShareTarget } from "@/hooks/useShareTarget";
import { useAppShellGestures } from "@/hooks/useAppShellGestures";
import { PullRefreshProvider } from "@/contexts/PullRefreshContext";
import * as nativeRecording from "@/services/nativeRecording";
import { useE1AutoSync } from "@/services/e1Sync";
import { useWatchRelay } from "@/hooks/useWatchRelay";
import { ToastViewport } from "@/components/ui/ToastViewport";
import { Avatar } from "@/components/ui/Avatar";
import { ProfileMenu } from "@/components/layout/ProfileMenu";
import { SupportPromptBanner } from "@/components/common/SupportPromptBanner";
import { usersService, userKeys } from "@/services/users";
import { unitsStore } from "@/stores/unitsStore";
import { useNavMode } from "@/stores/navModeStore";
import { canShowSupportLinks } from "@/config/platform";
import { OnboardingProvider, useOnboarding } from "@/onboarding/OnboardingContext";
import { TourHelpButton } from "@/onboarding/TourHelpButton";

// The main navigation exposes ONLY the 3 macro-sections (plus Admin) as
// inline links — sub-pages are reached from inside each section
// (docs/frontend-project.md, "Navigazione principale"). Profilo isn't a
// nav link: on desktop it's the avatar dropdown (ProfileMenu), on mobile
// it's the avatar entry in the bottom action bar. Logout lives in the
// ProfileMenu dropdown on desktop and at the bottom of the Profilo page on
// mobile (see ProfiloLayout.tsx).
export function AppShell() {
  return (
    <OnboardingProvider>
      <AppShellInner />
    </OnboardingProvider>
  );
}

function AppShellInner() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const navigate = useNavigate();
  const { pendingFile } = useShareTarget();
  const queryClient = useQueryClient();
  const { requestTour } = useOnboarding();

  // First thing a freshly-authenticated user sees, once — a guided walkthrough
  // that navigates across the three macro-sections and stops on the first
  // useful action in each (see the `getting-started` tour in tours.ts). Runs at
  // most once per account (server-tracked, see capabilities
  // `onboarding.seenTours`); replayable anytime via TourHelpButton.
  useEffect(() => {
    if (user) requestTour("getting-started");
  }, [user, requestTour]);

  // While the full-screen navigation display is up (components/registra/),
  // the shell suspends every background service it owns: the periodic E1 BLE
  // scan, the Apple Watch relay and the touch-gesture recognizers. Read once
  // here and threaded down as a parameter — the hooks themselves stay
  // unaware of a UI mode store they have no business depending on.
  const navMode = useNavMode();

  // Opportunistic, silent BLE relay of any claimed XGSail E1's buffered
  // sessions — see services/e1Sync.ts. No UI of its own; this is the
  // automatic counterpart to the E1's own WiFi upload.
  useE1AutoSync(queryClient, !navMode);

  // Relay finished sessions arriving from a paired Apple Watch (§9) — also
  // silent, event-driven; uploads land under the signed-in user as the
  // crew_member subject for the physiological streams.
  useWatchRelay(queryClient, user?.id, !navMode);

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
    { to: "/diario", label: t("nav.diario"), Icon: NotebookText, dataTour: "nav-diario" },
    // Available everywhere for the exploration map (nautical chart, POIs,
    // clubs). Recording itself stays native-only — the web has no background
    // GPS/foreground-service access (see services/nativeRecording.ts), so on
    // web the page shows the map with the recording controls disabled.
    { to: "/registra", label: t("nav.registra"), Icon: Disc, dataTour: undefined },
    { to: "/gruppi", label: t("nav.gruppi"), Icon: Users, dataTour: "nav-gruppi" },
    // Icon unused for /profilo (the action bar always shows the Avatar for
    // it instead, see below) — kept only so every section has the same
    // shape.
    { to: "/profilo", label: t("nav.profilo"), Icon: Users, dataTour: "nav-profilo" },
    ...(user?.is_superadmin
      ? [{ to: "/admin", label: t("nav.admin"), Icon: Settings, dataTour: undefined }]
      : []),
  ];
  const navLinkSections = sections.filter((s) => s.to !== "/profilo");

  // One touch-gesture recognizer on <main> drives both: drag left/right to
  // switch between the action bar's sections (same order as the bar), and
  // drag down from the very top to refetch whatever's on screen. Native
  // only — see useAppShellGestures for why both share a single listener.
  const location = useLocation();
  const { ref: mainRef, pull, refreshing } = useAppShellGestures<HTMLElement>(
    sections.map((s) => s.to),
    location.pathname,
    () => queryClient.refetchQueries({ type: "active" }),
    !navMode,
  );

  // `inert` keeps focus, pointer events and screen readers out of the shell
  // while the navigation overlay covers it. Spread rather than written as a
  // JSX prop because React 18's types don't know the attribute yet (React 19
  // adds it) — React still passes unknown lowercase attributes through.
  const inertProps = navMode ? ({ inert: "" } as Record<string, string>) : {};

  return (
    <div className="sf-shell" aria-hidden={navMode || undefined} {...inertProps}>
      {canShowSupportLinks && <SupportPromptBanner />}
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
              data-tour={s.dataTour}
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
        {/* SectionLayout renders the actual reveal strip, below its own tab
            bar — see PullRefreshIndicator/PullRefreshContext. Routes outside
            SectionLayout (Registra, race/regatta detail) don't show one;
            the refetch on release still runs regardless. */}
        <PullRefreshProvider value={{ pull, refreshing }}>
          <Outlet />
        </PullRefreshProvider>
      </main>
      <nav className="sf-actionbar" aria-label="Main">
        {sections.map((s) => (
          <NavLink key={s.to} to={s.to} data-tour={s.dataTour} className="sf-actionbar__item">
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
      <TourHelpButton />
    </div>
  );
}
