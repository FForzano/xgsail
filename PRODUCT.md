# Product

<!-- impeccable:product-schema 1 -->

## Platform

adaptive

One React SPA ships three ways. The Capacitor iOS and Android shells come first, because most users are expected to use the native apps. The phone-first website comes second. Desktop web is supported but doesn't lead decisions. Native shells take OTA-updated JS bundles (`docs/native-apps.md`, `docs/ota-updates.md`), so they have to tolerate offline cold starts and deferred uploads.

Wearable surfaces are separate from the SPA: the watchOS companion (`frontend/ios/App/XGSailWatch Watch App/`, a hand-built Xcode target), a future Wear OS app, and the E1 device display (in the `xgsail-e1` repo).

## Users

**Primary: the club and amateur sailor.** Dinghy, catamaran and keelboat sailors in local clubs (Italian *circoli velici* are the core community). They race in club regattas, but most of them sail mainly for fun, so "racer" and "enthusiast" describe the same person. They record outings on a phone or a tracker, review them ashore without a coach, and share them with their club and crew. When needs conflict, this user wins.

The app also serves coaches and training groups, club race officers (start lists, divisions, scoring, standings) and self-hosters. These are secondary audiences and don't drive design decisions today.

## Product Purpose

XGSail records sailing sessions and races and turns them into replay and analysis: legs, maneuvers, VMG, polars, points of sail and fused wind. Around that it builds club life: clubs, groups, regattas, scoring, standings and shared outings.

**Analysis ashore is the core value.** Social and club life is what makes the app succeed: sailors come back because their club and crew are there. Recording on the water and device support are essential features, not the core.

Success means club sailors choose XGSail over paid or proprietary alternatives because it's better to use, not only because it's free.

## Positioning

- **Free, with paid-app quality.** There's no paid tier. The bar is the polish of commercial sailing apps.
- **Custom, cheap, self-buildable hardware.** E1 is open reference hardware (`xgsail-e1`): an ESP32 tracker with GNSS, IMU, wind and pressure, an ESP-NOW fleet mesh and OCS start detection. Sailors build it themselves rather than buying a vendor device. Any phone or other tracker also works, through the documented device protocol (`docs/device-protocol.md`).

Supporting facts that are true and must be respected, though they aren't the headline:
- **Open.** The code is Apache 2.0, the stack self-hosts with one `docker compose up`, users own their data and there's no lock-in.
- **Club racing modelled as it really is.** That includes visiting boats, paper entries, scoring divisions, official vs. computed standings, guest boats with a claim flow, and two crew members' recordings merged into one session.

## Operating Context

- **Ashore, after sailing.** On a phone in the native app, at the club or at home: replay on a map, analysis, standings, the boat notebook, club news.
- **On the water.** The phone records in the background (`Registra`). Glance-and-glove usability matters on the **wearable** surfaces (watchOS, future Wear OS, the E1 display), not on the phone screen.
- **Spotty connectivity.** Marinas often have poor signal. The native app cold-starts from cached capabilities, keeps recording with no server, and retries uploads when the network or the app comes back.
- **Shared outings.** Several crew on one boat, several boats in one regatta, and clubs that mix members and visitors.

## Capabilities and Constraints

- **Areas:** Diario (activities, sessions, races, regattas, import), Registra (recording), Gruppi (clubs, groups, devices), Profilo (account, boats, boat notebook, devices), Admin (superadmin), a public landing page, legal pages.
- **Analysis:** track replay, legs, maneuvers (tack/gybe), VMG, polars and points of sail. Fused wind comes from real stations, weather models and tack-derived observations (`docs/estimation-pipeline.md`).
- **Clubs:** regattas with join codes, divisions, RRS A9 scoring and official standings. The explorer map combines our clubs with OpenStreetMap nautical POIs and weather stations.
- **Guided tours** run on demo fixtures (`frontend/src/onboarding/`, `frontend/src/demo/`).
- **Languages:** Italian and English are equal, first-class languages. Neither is the translation, and layouts must hold either language's copy length.
- **Domain terms** are used the way sailors use them: TWA, TWD, VMG, SOG/COG, polar, bolina / traverso / lasco / poppa, tack/gybe (*virata/strambata*), regatta, race, division, standings.

## Brand Commitments

- **Name:** XGSail, at xgsail.com. The logo is `frontend/public/logo.svg`. The tagline in the app is "Next-Gen Sailing Analytics".
- **Voice:** sailor to sailor. Plain and knowledgeable, using real sailing terms without explaining the basics. Never salesy.
- **Free, funded by donations.** Voluntary support only (Buy Me a Coffee), which pays for development, store publishing and servers. There's no paid tier to promote, and nothing may look like a paywall or an upsell.
- **Lineage:** a fork of SailFrames. Credit it honestly, without presenting XGSail as the same product.

## Evidence on Hand

- Product screenshots: `frontend/public/landing/` (analysis, clubs, devices, playback, race, record).
- E1 display renders: `frontend/public/devices/e1-display-modes/`.
- Scope statement and description: `README.md`, `frontend/public/llms.txt`.
- There are no testimonials, user counts, club partnerships or benchmarks on hand. Don't make any up.

## Product Principles

1. **Analysis is the reason to open the app.** Design ambition goes to what a session shows afterwards. Recording and device support have to be dependable and simple, not showcases.
2. **Club life brings people back.** Clubs, crews, regattas and shared outings are what make a sailor return. Treat social surfaces as part of the product's success, not as extras around the analysis.
3. **Free, but never cheap.** Hold the app to the standard of a paid one. Being free is never an excuse for rough edges.
4. **Native first, web close behind.** Design for the native phone apps first and keep the phone-first web just as sound.
5. **Hardware you can build.** Show device support as open and do-it-yourself, never as a vendor ecosystem.

## Accessibility & Inclusion

- Target **WCAG 2.2 AA** across the app.
- Italian and English copy must both fit without truncating or breaking the layout.
- Wearable surfaces (watchOS, Wear OS, E1 display) must be readable at a glance in sunlight and usable with wet or gloved hands.
