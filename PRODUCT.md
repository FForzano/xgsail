# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

The same React SPA ships as a website and inside Capacitor iOS/Android shells (`docs/native-apps.md`). The wrapper doesn't make the design language native. It does mean phone use, offline tolerance and OTA-updated bundles are first-class constraints.

## Users

**Primary: the club and amateur racer.** Dinghy, catamaran and keelboat sailors in local clubs (Italian *circoli velici* are the core community). They record their outings and club regattas on a phone, then review them ashore. When needs conflict, this user wins.

They are not only technical, competitive sailors: many are enthusiasts who sail for the pleasure of it. They read the analysis without a coach beside them, and they come back to the app because it is enjoyable to open, not only because it is useful.

Secondary audiences are already served by the app and will be improved later, but they don't drive design decisions today:
- coaches and training groups who review several sailors' tracks;
- club race officers who run regattas (start lists, divisions, scoring, standings);
- self-hosters who deploy their own instance.

## Product Purpose

XGSail records sailing sessions and races from any phone or GPS/wind tracker. It turns them into replay and analysis: legs, maneuvers, VMG, polars, and fused wind. It also gives clubs regattas, scoring and standings, and lets sailors share within clubs and groups.

The aim is a **free app that is genuinely well made**. Success is a club sailor choosing it over paid or proprietary alternatives because it's better to use, not just because it's free.

## Positioning

**Openness is the mast.** XGSail is Apache 2.0 and self-hostable with one `docker compose up`. Its documented device protocol means no hardware lock-in, and users own their data. Everything else hangs off that.

**It is also built for clubs, not just for individuals.** Real club racing is modelled directly:
- visiting boats that aren't club members, and paper entries with no account;
- scoring divisions, official versus computed standings, and guest boats with a claim flow;
- two crew members' recordings of the same outing merged into one session.

Personal tracking apps and vendor apps tied to one device don't model this.

## Operating Context

- **On the water, on a phone.** The recording flow (`Registra`) is used in bright sun, with wet or gloved hands, often one-handed, while sailing.
- **Ashore, after the session.** People use a phone or laptop at the club or at home for replay on a map, analysis, standings and the boat notebook.
- **Spotty connectivity.** Marinas often have poor signal. The native app cold-starts offline from cached capabilities, keeps recording with no server, and retries deferred uploads when the network or the app comes back.
- **Shared outings.** Several crew on one boat, several boats in one regatta, and clubs that mix members and visitors.

## Capabilities and Constraints

- **Areas:** Diario (activities, sessions, races, regattas, import), Gruppi (clubs, groups, devices), Profilo (account, boats, boat notebook, devices), Registra (live recording), Admin (superadmin), a public landing page, and legal pages.
- **Analysis:** track replay, legs, maneuvers (tack/gybe), VMG, polars, and points of sail. Fused wind comes from real stations, models and tack-derived observations (`docs/estimation-pipeline.md`).
- **Clubs:** regattas with join codes, divisions, RRS A9 scoring and official standings. There's also an explorer map that combines our clubs with OpenStreetMap nautical POIs and weather stations.
- **Guided tours** use demo fixtures (`frontend/src/onboarding/`, `frontend/src/demo/`).
- **Stack:** Vite, React and TypeScript, TanStack Query, Leaflet, Recharts, Tiptap rich text, i18next, and lucide icons. Styles follow a global `sf-*` design-system layer plus CSS Modules (see CLAUDE.md, "Frontend CSS").
- **Languages:** English and Italian are equal, first-class languages. Neither is the translation. Layouts must hold up with either language's copy length.
- **Domain terms** are used as sailors use them: TWA, TWD, VMG, SOG/COG, polar, bolina / traverso / lasco / poppa, tack/gybe (*virata/strambata*), and regatta, race, division and standings.
- **Device:** E1 is open reference hardware in a separate repo (`xgsail-e1`), currently built by the user rather than sold.

## Brand Commitments

- **Name:** XGSail. The site is xgsail.com and the logo is `frontend/public/logo.svg`.
- **Voice:** sailor to sailor. It's plain and knowledgeable, uses real sailing terms without explaining the basics, and is never salesy.
- **Open source and free.** Funding comes from voluntary support (Buy Me a Coffee) and pays for development, store publishing and servers. There's no paid tier to promote.
- **Lineage:** it's a fork of SailFrames. Credit the lineage honestly, without presenting it as the same product.

## Evidence on Hand

- Product screenshots: `frontend/public/landing/` (analysis, clubs, devices, playback, race, record).
- E1 device display renders: `frontend/public/devices/`.
- `README.md` and `frontend/public/llms.txt` hold the scope statement and description.
- There are no testimonials, user counts, club partnerships or benchmarks on hand. Don't make any up.

## Product Principles

1. **Open is the mast.** Never design a flow that implies lock-in, a paywall or data hostage-taking. Self-hosting and data ownership are features to show, not to hide.
2. **Free, but not cheap.** The bar is the quality of paid apps. Being free never excuses rough edges. The app should be pleasant and inviting to open, not just correct: a numbers screen an enthusiast enjoys reading is part of the job.
3. **Works on the water first.** Anything used while sailing must work in glare, with gloves, one-handed and offline. Analysis can be richer ashore.
4. **Analysis is the core; recording is the means.** The product's value is what a session shows afterwards. Recording has to be safe, dependable and simple, so that no data is lost and the screen can be read at a glance. It is not where the design ambition goes; the analysis surfaces are.
5. **Model club racing as it really is.** Visitors, paper entries, shared boats and co-recorded outings are normal cases, not edge cases.
6. **Honest numbers.** Show where the data came from and its limits, such as wind source, missing wind and partial map coverage. Never let a gap look like a calm sea or an empty map.

## Accessibility & Inclusion

- Target **WCAG 2.2 AA** across the app.
- The on-water conditions add to that: contrast that stays readable in sunlight, and large touch targets that work with gloves in the recording flow.
- Copy and layouts must stay intact in both Italian and English.
