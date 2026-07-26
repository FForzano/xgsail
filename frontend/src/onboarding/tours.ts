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
  {
    id: "app-overview",
    priority: 0,
    steps: [
      { target: "nav-diario", titleKey: "onboarding.overview.diario.title", bodyKey: "onboarding.overview.diario.body" },
      { target: "nav-gruppi", titleKey: "onboarding.overview.gruppi.title", bodyKey: "onboarding.overview.gruppi.body" },
      { target: "nav-profilo", titleKey: "onboarding.overview.profilo.title", bodyKey: "onboarding.overview.profilo.body" },
    ],
  },
  {
    id: "diario-personale",
    priority: 1,
    routes: ["/diario"],
    steps: [
      { target: "diario-tabs", titleKey: "onboarding.diario.tabs.title", bodyKey: "onboarding.diario.tabs.body" },
      { target: "diario-upcoming-banner", titleKey: "onboarding.diario.banner.title", bodyKey: "onboarding.diario.banner.body" },
      { target: "diario-filter", titleKey: "onboarding.diario.filter.title", bodyKey: "onboarding.diario.filter.body" },
      { target: "diario-import", titleKey: "onboarding.diario.import.title", bodyKey: "onboarding.diario.import.body" },
      { target: "diario-feed", titleKey: "onboarding.diario.feed.title", bodyKey: "onboarding.diario.feed.body" },
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
