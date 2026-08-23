// Guided-tour registry: plain data, no React here — see OnboardingContext for
// the runner and TourSpotlight for the visual. Each step's `target` matches a
// `data-tour="..."` attribute somewhere in the DOM; a step whose target isn't
// currently rendered (e.g. UpcomingEventsBanner returns null when there are no
// upcoming events, or a club sub-tab the user isn't on) is skipped by the
// runner, not treated as an error.
//
// Adding a new tour later needs no change anywhere else: add an entry here, tag
// the relevant element(s) with a new `data-tour`, and — for a tour that isn't
// tied to a route — call `requestTour(id)` from wherever that feature lives.
// The backend accepts any string tour ID already (backend/onboarding.py).

import { DEMO_ACTIVITY_ID, DEMO_BOAT_ID, DEMO_CLUB_ID } from "@/demo";

export interface TourStep {
  /** Matches a `data-tour="..."` attribute. */
  target: string;
  /** i18n key for the step's title. */
  titleKey: string;
  /** i18n key for the step's body copy. */
  bodyKey: string;
  /** Route the step lives on. When set and the app isn't already there, the
   * runner navigates to it before looking for `target` (see
   * OnboardingContext) — lets a single tour walk across pages/tabs, and lets
   * an entity-scoped tour point at a demo entity so a user with no data of
   * their own still has something to be shown. Ignored for the whole run when
   * a tour is started `inPlace`, which covers both the first-visit auto-start
   * and the "?" button — so in practice only `getting-started` (requested by
   * name from AppShell) ever navigates, and an entity tour replays on the real
   * record the user is looking at.
   *
   * Always a leaf path: `/diario`, `/gruppi` and `/profilo` index-redirect to
   * their first tab, which the runner would read as "not there yet" and
   * navigate again on every redirect. */
  route?: string;
}

export interface Tour {
  id: string;
  /** Lower runs first when multiple tours are queued at once. */
  priority: number;
  /** Path prefixes this tour is "about" — used by the help button to offer
   * "replay this page's tour", and by the runner to auto-start it the first
   * time the user lands on one of them. Omitted for tours (like the app
   * overview) that aren't tied to one route. */
  routes?: string[];
  steps: TourStep[];
}

export const TOURS: Tour[] = [
  // First-run tour: walks the user across the sections and stops on the one
  // thing that unlocks the app's value in each (import a track, join your
  // club, add your boat). Deliberately short — it is the very first thing a
  // new account sees, and every area has its own tour waiting on its page. It
  // NAVIGATES between sections via each step's `route`; on an empty account
  // the feed step shows a demo card (see TourDemoCard / MyDiaryPage) so the
  // payoff is visible before any real data exists.
  {
    id: "getting-started",
    priority: 0,
    steps: [
      {
        target: "nav-diario",
        route: "/diario/personale",
        titleKey: "onboarding.gettingStarted.welcome.title",
        bodyKey: "onboarding.gettingStarted.welcome.body",
      },
      {
        target: "diario-tabs",
        route: "/diario/personale",
        titleKey: "onboarding.gettingStarted.tabs.title",
        bodyKey: "onboarding.gettingStarted.tabs.body",
      },
      {
        target: "diario-import",
        route: "/diario/personale",
        titleKey: "onboarding.gettingStarted.import.title",
        bodyKey: "onboarding.gettingStarted.import.body",
      },
      {
        target: "diario-feed",
        route: "/diario/personale",
        titleKey: "onboarding.gettingStarted.feed.title",
        bodyKey: "onboarding.gettingStarted.feed.body",
      },
      {
        target: "gruppi-tabs",
        route: "/gruppi/gruppi",
        titleKey: "onboarding.gettingStarted.groups.title",
        bodyKey: "onboarding.gettingStarted.groups.body",
      },
      // Desktop-only anchor (the navbar avatar): on a phone the profile lives
      // in the bottom action bar instead, so this step simply skips itself.
      {
        target: "nav-profilo-desktop",
        route: "/profilo/anagrafica",
        titleKey: "onboarding.gettingStarted.profile.title",
        bodyKey: "onboarding.gettingStarted.profile.body",
      },
      {
        target: "profilo-add-boat",
        route: "/profilo/barche",
        titleKey: "onboarding.gettingStarted.boat.title",
        bodyKey: "onboarding.gettingStarted.boat.body",
      },
    ],
  },
  {
    id: "diario-personale",
    priority: 1,
    routes: ["/diario/personale", "/diario/circoli"],
    steps: [
      { target: "diario-tabs", titleKey: "onboarding.diarioPersonale.tabs.title", bodyKey: "onboarding.diarioPersonale.tabs.body" },
      { target: "diario-import", titleKey: "onboarding.diarioPersonale.import.title", bodyKey: "onboarding.diarioPersonale.import.body" },
      { target: "diario-filter", titleKey: "onboarding.diarioPersonale.filter.title", bodyKey: "onboarding.diarioPersonale.filter.body" },
      { target: "diario-feed", titleKey: "onboarding.diarioPersonale.feed.title", bodyKey: "onboarding.diarioPersonale.feed.body" },
      { target: "diario-upcoming-banner", titleKey: "onboarding.diarioPersonale.banner.title", bodyKey: "onboarding.diarioPersonale.banner.body" },
    ],
  },
  // Written for a single-boat outing, which is what the demo activity is: the
  // solo case renders the session inline, so the session's own blocks
  // (statistics, health, analysis) are anchored on this same page.
  {
    id: "activity-detail",
    priority: 1,
    routes: ["/diario/activities"],
    steps: [
      {
        target: "activity-boats",
        route: `/diario/activities/${DEMO_ACTIVITY_ID}`,
        titleKey: "onboarding.activityDetail.boat.title",
        bodyKey: "onboarding.activityDetail.boat.body",
      },
      { target: "activity-quick-actions", titleKey: "onboarding.activityDetail.quickActions.title", bodyKey: "onboarding.activityDetail.quickActions.body" },
      { target: "activity-map", titleKey: "onboarding.activityDetail.map.title", bodyKey: "onboarding.activityDetail.map.body" },
      { target: "activity-speed-chart", titleKey: "onboarding.activityDetail.speedChart.title", bodyKey: "onboarding.activityDetail.speedChart.body" },
      { target: "activity-menu", titleKey: "onboarding.activityDetail.menu.title", bodyKey: "onboarding.activityDetail.menu.body" },
      { target: "activity-stats", titleKey: "onboarding.activityDetail.stats.title", bodyKey: "onboarding.activityDetail.stats.body" },
      { target: "activity-health", titleKey: "onboarding.activityDetail.health.title", bodyKey: "onboarding.activityDetail.health.body" },
      { target: "activity-analysis", titleKey: "onboarding.activityDetail.analysis.title", bodyKey: "onboarding.activityDetail.analysis.body" },
      { target: "activity-marks", titleKey: "onboarding.activityDetail.marks.title", bodyKey: "onboarding.activityDetail.marks.body" },
    ],
  },
  {
    id: "registra-overview",
    priority: 1,
    routes: ["/registra"],
    steps: [
      { target: "registra-map", titleKey: "onboarding.registraOverview.map.title", bodyKey: "onboarding.registraOverview.map.body" },
      // The layer switcher is the same control on every map (MapLayerToggles),
      // so its anchor is named after the control, not this page.
      { target: "map-layers", titleKey: "onboarding.registraOverview.layers.title", bodyKey: "onboarding.registraOverview.layers.body" },
      { target: "registra-record", titleKey: "onboarding.registraOverview.record.title", bodyKey: "onboarding.registraOverview.record.body" },
      // RegistraPage opens its own bottom sheet while any of the next four
      // steps is active, so these targets exist without the user tapping.
      { target: "registra-fields", titleKey: "onboarding.registraOverview.fields.title", bodyKey: "onboarding.registraOverview.fields.body" },
      { target: "registra-boat", titleKey: "onboarding.registraOverview.boat.title", bodyKey: "onboarding.registraOverview.boat.body" },
      { target: "registra-activity", titleKey: "onboarding.registraOverview.activity.title", bodyKey: "onboarding.registraOverview.activity.body" },
      { target: "registra-start", titleKey: "onboarding.registraOverview.start.title", bodyKey: "onboarding.registraOverview.start.body" },
    ],
  },
  {
    id: "gruppi-overview",
    priority: 1,
    routes: ["/gruppi/gruppi", "/gruppi/clubs"],
    steps: [
      { target: "gruppi-tabs", titleKey: "onboarding.gruppiOverview.tabs.title", bodyKey: "onboarding.gruppiOverview.tabs.body" },
      { target: "gruppi-search", titleKey: "onboarding.gruppiOverview.search.title", bodyKey: "onboarding.gruppiOverview.search.body" },
      { target: "gruppi-create", titleKey: "onboarding.gruppiOverview.create.title", bodyKey: "onboarding.gruppiOverview.create.body" },
    ],
  },
  {
    id: "club-detail",
    priority: 1,
    routes: ["/gruppi/clubs/"],
    steps: [
      {
        target: "club-tabs",
        route: `/gruppi/clubs/${DEMO_CLUB_ID}`,
        titleKey: "onboarding.clubDetail.tabs.title",
        bodyKey: "onboarding.clubDetail.tabs.body",
      },
      { target: "club-news", titleKey: "onboarding.clubDetail.news.title", bodyKey: "onboarding.clubDetail.news.body" },
      { target: "club-news-event", titleKey: "onboarding.clubDetail.event.title", bodyKey: "onboarding.clubDetail.event.body" },
      {
        target: "club-info",
        route: `/gruppi/clubs/${DEMO_CLUB_ID}/informazioni`,
        titleKey: "onboarding.clubDetail.info.title",
        bodyKey: "onboarding.clubDetail.info.body",
      },
      {
        target: "club-events",
        route: `/gruppi/clubs/${DEMO_CLUB_ID}/eventi`,
        titleKey: "onboarding.clubDetail.events.title",
        bodyKey: "onboarding.clubDetail.events.body",
      },
    ],
  },
  {
    id: "profilo-overview",
    priority: 1,
    routes: ["/profilo/anagrafica"],
    steps: [
      { target: "profilo-tabs", titleKey: "onboarding.profiloOverview.tabs.title", bodyKey: "onboarding.profiloOverview.tabs.body" },
      { target: "profilo-anagrafica", titleKey: "onboarding.profiloOverview.details.title", bodyKey: "onboarding.profiloOverview.details.body" },
      { target: "profilo-units", titleKey: "onboarding.profiloOverview.units.title", bodyKey: "onboarding.profiloOverview.units.body" },
    ],
  },
  {
    id: "boats-overview",
    priority: 1,
    routes: ["/profilo/barche"],
    steps: [
      { target: "profilo-add-boat", titleKey: "onboarding.boatsOverview.add.title", bodyKey: "onboarding.boatsOverview.add.body" },
      { target: "profilo-boat-card", titleKey: "onboarding.boatsOverview.example.title", bodyKey: "onboarding.boatsOverview.example.body" },
    ],
  },
  {
    id: "boat-detail",
    priority: 1,
    routes: ["/profilo/barche/"],
    steps: [
      {
        target: "boat-notebook",
        route: `/profilo/barche/${DEMO_BOAT_ID}`,
        titleKey: "onboarding.boatDetail.notebook.title",
        bodyKey: "onboarding.boatDetail.notebook.body",
      },
      { target: "boat-photos", titleKey: "onboarding.boatDetail.photos.title", bodyKey: "onboarding.boatDetail.photos.body" },
      { target: "boat-crew", titleKey: "onboarding.boatDetail.crew.title", bodyKey: "onboarding.boatDetail.crew.body" },
    ],
  },
  {
    id: "devices-overview",
    priority: 1,
    routes: ["/profilo/devices"],
    steps: [
      { target: "devices-add", titleKey: "onboarding.devicesOverview.add.title", bodyKey: "onboarding.devicesOverview.add.body" },
      { target: "devices-row", titleKey: "onboarding.devicesOverview.claimed.title", bodyKey: "onboarding.devicesOverview.claimed.body" },
    ],
  },
  {
    id: "regatta-detail",
    priority: 1,
    // Not `/diario/regate`: that also prefixes the race dashboard
    // (/diario/regate/race/:id), which carries none of these anchors and would
    // consume the tour without showing a single step.
    routes: ["/diario/regate/regatta"],
    steps: [
      { target: "regatta-entries", titleKey: "onboarding.regattaDetail.entries.title", bodyKey: "onboarding.regattaDetail.entries.body" },
      { target: "regatta-racedays", titleKey: "onboarding.regattaDetail.racedays.title", bodyKey: "onboarding.regattaDetail.racedays.body" },
      { target: "regatta-standings", titleKey: "onboarding.regattaDetail.standings.title", bodyKey: "onboarding.regattaDetail.standings.body" },
      // Rendered only by a regatta that actually has divisions; skipped otherwise.
      { target: "regatta-divisions", titleKey: "onboarding.regattaDetail.divisions.title", bodyKey: "onboarding.regattaDetail.divisions.body" },
    ],
  },
];

export function getTour(id: string): Tour | undefined {
  return TOURS.find((t) => t.id === id);
}

/** The tour whose `routes` match the given pathname with the LONGEST prefix —
 * used both by the on-demand help button ("replay this page's tour") and by
 * the runner's first-visit auto-start. Longest wins so that a nested tour
 * (`/profilo/barche/` → boat-detail) beats its parent list
 * (`/profilo/barche` → boats-overview) regardless of the order of TOURS.
 * `getting-started` has no `routes`, so it is never returned here: it is
 * requested explicitly by AppShell instead. */
export function tourForPath(pathname: string): Tour | undefined {
  let best: Tour | undefined;
  let bestLength = -1;
  for (const tour of TOURS) {
    for (const route of tour.routes ?? []) {
      if (pathname.startsWith(route) && route.length > bestLength) {
        best = tour;
        bestLength = route.length;
      }
    }
  }
  return best;
}
