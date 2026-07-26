// Guided-tour registry: plain data, no React here — see OnboardingContext for
// the runner and TourSpotlight for the visual. Each step's `target` matches a
// `data-tour="..."` attribute somewhere in the DOM (see the components listed
// next to each tour below); a step whose target isn't currently rendered
// (e.g. UpcomingEventsBanner returns null when there are no upcoming events)
// is skipped by the runner, not treated as an error.
//
// Adding a new tour later (e.g. a narrower per-feature one) needs no change
// anywhere else: add an entry here, tag the relevant element(s) with a new
// `data-tour`, and call `requestTour(id)` from wherever that feature lives —
// see docs/estimation-pipeline.md-style extensibility note in the onboarding
// plan. The backend accepts any string tour ID already (backend/onboarding.py).

export interface TourStep {
  /** Matches a `data-tour="..."` attribute. */
  target: string;
  /** i18n key for the step's title. */
  titleKey: string;
  /** i18n key for the step's body copy. */
  bodyKey: string;
  /** Route the step lives on. When set and the app isn't already there, the
   * runner navigates to it before looking for `target` (see
   * OnboardingContext) — lets a single tour walk across pages/tabs. Only the
   * first-run `getting-started` tour crosses sections; the per-page tours
   * offered by the "?" button stay on (or within) their own page so the help
   * button never wanders off the page it was pressed on. */
  route?: string;
}

export interface Tour {
  id: string;
  /** Lower runs first when multiple tours are queued at once. */
  priority: number;
  /** Path prefixes this tour is "about" — used by the help button to offer
   * "replay this page's tour" without a separate route map. Omitted for
   * tours (like the app overview) that aren't tied to one route. */
  routes?: string[];
  steps: TourStep[];
}

export const TOURS: Tour[] = [
  // First-run guided tour: walks the user across the three sections and stops
  // on the one action that unlocks the app's value in each (import a track,
  // join your club, add your boat). It NAVIGATES between sections via each
  // step's `route`; on an empty account the diario step shows a demo card
  // (see TourDemoCard / MyDiaryPage) so the payoff is visible before any real
  // data exists. Runs once per account; replayable from the "?" button.
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
        target: "diario-import",
        route: "/diario/personale",
        titleKey: "onboarding.gettingStarted.import.title",
        bodyKey: "onboarding.gettingStarted.import.body",
      },
      {
        target: "diario-feed",
        route: "/diario/personale",
        titleKey: "onboarding.gettingStarted.session.title",
        bodyKey: "onboarding.gettingStarted.session.body",
      },
      {
        target: "gruppi-search",
        route: "/gruppi",
        titleKey: "onboarding.gettingStarted.groups.title",
        bodyKey: "onboarding.gettingStarted.groups.body",
      },
      {
        target: "profilo-add-boat",
        route: "/profilo",
        titleKey: "onboarding.gettingStarted.boat.title",
        bodyKey: "onboarding.gettingStarted.boat.body",
      },
    ],
  },
  {
    id: "diario-personale",
    priority: 1,
    routes: ["/diario"],
    steps: [
      { target: "diario-tabs", titleKey: "onboarding.diario.tabs.title", bodyKey: "onboarding.diario.tabs.body" },
      { target: "diario-import", titleKey: "onboarding.diario.import.title", bodyKey: "onboarding.diario.import.body" },
      { target: "diario-filter", titleKey: "onboarding.diario.filter.title", bodyKey: "onboarding.diario.filter.body" },
      { target: "diario-feed", titleKey: "onboarding.diario.feed.title", bodyKey: "onboarding.diario.feed.body" },
      { target: "diario-upcoming-banner", titleKey: "onboarding.diario.banner.title", bodyKey: "onboarding.diario.banner.body" },
    ],
  },
  {
    id: "gruppi-overview",
    priority: 1,
    routes: ["/gruppi"],
    steps: [
      { target: "gruppi-tabs", titleKey: "onboarding.gruppi.tabs.title", bodyKey: "onboarding.gruppi.tabs.body" },
      { target: "gruppi-search", titleKey: "onboarding.gruppi.search.title", bodyKey: "onboarding.gruppi.search.body" },
      { target: "gruppi-create", titleKey: "onboarding.gruppi.create.title", bodyKey: "onboarding.gruppi.create.body" },
    ],
  },
  {
    id: "profilo-overview",
    priority: 1,
    routes: ["/profilo"],
    steps: [
      { target: "profilo-tabs", titleKey: "onboarding.profilo.tabs.title", bodyKey: "onboarding.profilo.tabs.body" },
      { target: "profilo-add-boat", titleKey: "onboarding.profilo.boats.title", bodyKey: "onboarding.profilo.boats.body" },
    ],
  },
];

export function getTour(id: string): Tour | undefined {
  return TOURS.find((t) => t.id === id);
}

/** First tour whose `routes` prefixes the given pathname — used by the
 * on-demand help button to offer "replay this page's tour". */
export function tourForPath(pathname: string): Tour | undefined {
  return TOURS.find((t) => t.routes?.some((r) => pathname.startsWith(r)));
}
