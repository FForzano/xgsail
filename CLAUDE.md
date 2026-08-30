# XGSail — Sailing Analytics Platform

## Project Context for Claude Code

This repository is **XGSail**: the software application layer only —
backend API, frontend SPA, native iOS/Android app shells, standalone
OTA update service, ingestion/processing workers, and self-hosted
deployment. It is **not** the hardware/firmware repository. Firmware,
PCB design (KiCad), and embedded-device internals live in the separate
upstream project (SailFrames Core) and its E1 successor
(`xgsail-e1`) — out of scope here.

XGSail is an open-source (Apache 2.0) fork of SailFrames: it keeps the
original's license and general purpose — sailing session analytics —
but the data model, API surface, and frontend have been substantially
redesigned rather than incrementally patched. See "Structural
differences from upstream" in `README.md` for specifics.

XGSail is hardware-agnostic by design: devices integrate through
a stable, documented ingestion contract (`docs/device-protocol.md`)
rather than through code that assumes a specific board. See
`README.md` for the full scope statement ("What XGSail Is" /
"Is Not").

---

## Project Overview

- **License:** Apache 2.0
- **Getting started:** `docker compose up --build` brings up the entire
  self-hosted stack locally (Postgres + MinIO + backend + frontend +
  workers), with the same code deploying to AWS (S3/Lambda) via
  env-gated config — no code forks between the two targets.
- **Status:** the users/auth/roles/clubs/groups/devices redesign has
  landed on `main` — schema, API, and frontend already reflect it.
  Since then the platform has grown a native app layer (Capacitor
  iOS/Android shells, `docs/native-apps.md`) and a self-hosted OTA
  JS-bundle update path for it (`ota-service/`, `docs/ota-updates.md`),
  plus a first pytest-based test harness (`tests/`, root
  `pyproject.toml`). `docs/device-protocol.md` (ingestion contract) and
  `docs/estimation-pipeline.md` (raw sensor/API data → legs/maneuvers/
  VMG/polar numbers) remain the sources of truth for those areas.

---

## Commands

```bash
# Local startup (production-like: nginx serving the built SPA)
docker compose up --build

# Local startup with frontend hot reload (dev loop)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
# (rebuild once; after that just `up` — no --build needed for src changes,
# only for package.json changes)

# Tests — run from repo root, not from backend/
pytest                    # all suites: tests/backend, tests/windfusion, tests/worker
pytest tests/backend      # backend only
cd frontend && npm run typecheck   # frontend has no test runner yet — tsc is the gate

# DB migrations (Alembic)
cd backend && alembic revision --autogenerate -m "description"
cd backend && alembic upgrade head
cd backend && alembic downgrade -1

# Schema/ORM drift gate — what CI runs on every push (needs a live Postgres;
# `docker compose up postgres` is enough). Run from the repo root.
alembic -c backend/alembic.ini upgrade head    # from an EMPTY db
alembic -c backend/alembic.ini check           # no drift vs. Base.metadata
alembic -c backend/alembic.ini downgrade base && alembic -c backend/alembic.ini upgrade head

# OTA service (standalone Node/Express, independent of backend/DB)
cd ota-service && npm run dev         # tsx watch
cd ota-service && npm run build       # tsc
cd ota-service && npm run typecheck

# API docs (auto-generated OpenAPI)
http://localhost:8000/api/docs   # Swagger UI
http://localhost:8000/api/redoc  # ReDoc
```

`docker-compose.dev.yml` is an overlay, not a standalone stack — it
swaps the frontend service for the Vite dev server (HMR, source mounted
from host). The base `docker-compose.yml` stays the documented
self-hosted stack; `deploy/docker-compose.prod.yml` is the production
variant.

`pyproject.toml` at repo root exists only to configure pytest (`tests/`
as `testpaths`, `pythonpath` spanning `.`, `workers/process_upload`, and
`libs/xgsail_windfusion`) — it is not a build target for any of the
deployable pieces, which each have their own setup (`deploy/
requirements.txt` for the backend, each worker's own Dockerfile,
`libs/xgsail_windfusion/pyproject.toml` for the shared lib).

---

## Architecture

**Framework:** FastAPI (backend), Vite + React + TypeScript (frontend,
also wrapped via Capacitor for iOS/Android), Express (`ota-service/`),
Alembic (DB migrations). Entry points: `backend/main.py` (FastAPI app
composition), `frontend/src/main.tsx` (SPA entry), `ota-service/src/
server.ts`.

### Request lifecycle (backend API)

1. Request hits the frontend (nginx proxy in self-hosted, Vite dev
   server locally) or, for native apps, goes cross-origin straight to
   the backend host
2. Routed to a backend API endpoint (`backend/routers/`)
3. Auth validates JWT — httpOnly cookie for web, `Authorization: Bearer`
   for native (`backend/auth/permissions.py`'s `current_user()`, see
   "Native apps" below) — or device key / hook token depending on the
   router
4. Route handler delegates to business logic (`backend/services/`)
5. Services read/write via repositories (`backend/repositories/`)
6. Response serialized via a Pydantic `schemas/` DTO
7. Frontend consumes via TanStack Query hooks, re-renders via React

### Key layers

**Routers** (`backend/routers/`) — HTTP/routing concerns only, one
module per resource, registered in `routers/__init__.py`
(`ALL_ROUTERS`). Thin entry points; business logic lives in services.
Shared HTTP helpers go in `routers/_common.py`, not copy-pasted per
router.

**Services** (`backend/services/`) — business logic by domain (course,
geo, gpx, wind estimation, import processing, maneuver reconciliation,
regatta scoring, `boat_merge` for resolving a guest-boat claim).

**Repositories** (`backend/repositories/`) — data-access layer only.
Base class in `repositories/base.py`, SQL implementations in
`repositories/sql/`.

**DB models** (`backend/db/models/`) — SQLAlchemy ORM entities,
Alembic-migrated.

**Schemas** (`backend/schemas/`) — Pydantic request/response DTOs,
separate from DB models so API and persistence can evolve independently.

**Storage** (`backend/storage/`) — object-store abstraction (S3/MinIO).
Presigned URLs, uploads, and webhooks all go through this layer;
`ota-service/` reuses its env var names (see "Environment variables")
to point at the same MinIO instance without depending on this module.

**Frontend-copy-owner modules** (`backend/legal.py`, `backend/
onboarding.py`, `backend/support.py`) — each is the backend's single
source of truth for an ID/cadence whose actual copy lives in the
frontend (`frontend/src/content/legal/*`, `frontend/src/onboarding/
tours.ts`, `frontend/src/components/common/SupportPromptBanner.tsx`
respectively). Don't duplicate that copy server-side — these modules
only track versioning/timing.

**Guided tours** (`frontend/src/onboarding/`) — a coachmark runner plus a
plain-data registry (`tours.ts`). A step names a `data-tour` attribute;
a step whose target isn't in the DOM is skipped, not an error. Each
page tour auto-starts once per account on first visit (tracked in
`caps.onboarding.seenTours`, IDs mirrored in `backend/onboarding.py`)
and replays from the "?" button. Both of those run *in place*, so a
step's `route` only ever navigates for a tour requested by name —
today just `getting-started`.

**`frontend/src/demo/`** — fixture records (a solo outing, a club, a
boat, a device) that let those tours show a populated page to an empty
account, rendered by the *real* pages rather than a second copy of the
UI. See the Gotchas entry below before touching it.

**`backend/richtext.py`** — the prose-sanitization boundary, not a
frontend-copy-owner module. Every free-text prose column (activity/
club/group/regatta descriptions, boat notes, note templates, post
bodies, session notes, race-day notes) is stored as sanitized HTML;
this module's `normalize()` (via `nh3`) is what a DTO field type
(`RichTextBasic`/`RichTextFull`/`RichTextPost` from this same module)
applies before anything reaches the database. See the Gotchas entry
below before adding a new prose field.

**Auth** (`backend/auth/`) — passwords, JWT tokens (cookie for web,
Bearer for native — see "Native apps"), and RBAC seeding
(`seed_superadmin`, `seed_device_types`, `seed_defaults` in `main.py`).
Two authorization models:
1. **Scoped RBAC** (`roles`/`permissions`/`role_permissions`/`user_roles`,
   see `backend/db/models/rbac.py` + `backend/routers/rbac.py`) for
   institutional roles (`superadmin`, `club_admin`, `race_officer`),
   scoped via `user_roles.scope_club_id`.
2. **Per-resource ownership** (`user_boats.role`, `user_groups.role`)
   for personal/boat-scoped resources — the relationship itself grants
   access, no centralized permission check. `session_crew` is the
   session-level counterpart: `is_session_crew_or_manager` is what gates
   notes, media, the choice of navigation track, and separating a
   contributed track — a session is routinely co-owned by two people who
   recorded the same outing, and only one of them owns the activity it
   ended up in (see the Gotchas below and `docs/device-protocol.md` §10).
3. **Regatta start list** (`regatta_entries`) for the one case neither
   covers: a competitor who is not a club member and not an editor of
   the organizing club's race activity, but must still be able to
   attach their own recording to the race they sailed. Keys on the
   **boat**, so it works identically for member and visiting boats
   (`can_attach_session_to_activity`). Sailors get on the list either
   by the organizer entering them or by redeeming the regatta's
   `join_code`. An entry's `boat_id` is **nullable**: an organizer can
   also enter a boat that has no XGSail record at all (a paper entry),
   captured as `boat_name`/`sail_number` instead, and link it to a real
   boat later (`PATCH /regattas/{id}/entries/{entry_id}`). The same
   entry also carries the boat's scoring **division** (`division_id`,
   e.g. "Catamarani" vs. "Derive") — a per-regatta label
   (`regatta_divisions`), not a reference to the global `boat_classes`
   catalog; see the Gotchas bullet below before touching scoring or
   standings for a divided regatta.
4. **Guest boats** (`boats.is_guest`) for a boat the recorder doesn't own —
   a friend's boat, a club charter. No new role: the creator is a plain
   `user_boats.role="owner"` like any boat creator, so every check above
   keeps working unchanged. `boat_claims` (`backend/db/models/boat_claim.py`)
   is how the real owner takes it over — approval is gated to the guest
   boat's own owner/admin (`backend/routers/boats.py`'s
   `_require_claim_approver`), since it grants boat membership and boat
   membership is what gates session read access. See the Gotchas below.

**Workers** (`workers/`) — heavy processing (GPS/CSV/GPX analysis,
video transcoding, maneuver-detector training). Invoked by the backend
over HTTP; the same container image also runs as a Lambda in AWS.

**`libs/xgsail_windfusion`** — standalone Python package (own
`pyproject.toml`) implementing the wind-fusion/calibration algorithm,
imported by both `backend/services/` and `workers/process_upload/` —
the reason the shared logic lives here instead of duplicated in each.

**`ota-service/`** — standalone Node/Express service (own `package.json`,
Dockerfile), no dependency on the FastAPI backend or Postgres. Serves a
self-hosted OTA manifest + presigned bundle URLs from MinIO for the
native app's `@capgo/capacitor-updater` (the open-source plugin, not
Capgo's paid cloud). See "Native apps" below.

### Adding a new API endpoint

1. Add/extend a router in `backend/routers/<resource>.py`, register it
   in `routers/__init__.py`'s `ALL_ROUTERS`
2. Add a Pydantic DTO in `backend/schemas/<resource>.py`
3. Implement logic in `backend/services/<domain>.py`
4. Add a repository method in `backend/repositories/sql/` if new data
   access is needed
5. Frontend: add/extend a TanStack Query hook, consume in a page/component

### Adding a migration

```bash
cd backend && alembic revision --autogenerate -m "description"
# edit the generated file in backend/alembic/versions/
cd backend && alembic upgrade head
```

Always provide a working `downgrade()` so rollbacks stay safe.

---

## Code Style Guidelines

Applies across the whole repo (backend, frontend, workers, ota-service):

- **Simple and readable over clever.** Optimize for the next person
  reading the code, not for fewest lines or cleverest trick.
- **Isolate responsibilities.** Router modules stay thin (HTTP concerns
  only); business logic lives in `services`/`repositories`; don't mix
  request parsing, DB access, and response shaping in one function.
- **Reuse before writing — in this order:** (1) an existing function/
  component/hook already in the codebase; (2) a well-maintained library
  already a dependency; (3) a new well-maintained library, only when
  nothing existing covers it. Don't reach for an abandoned or
  barely-used package over a few extra lines of plain code.
- **No duplicated logic — including CSS.** Extract shared blocks/
  patterns into one function/component/CSS Module instead of copying.
  Applies especially to router HTTP helpers (`routers/_common.py`),
  frontend data logic (hooks/utils, not duplicated per page), frontend
  styles (see below), and cross-language reuse like `ota-service`
  deliberately reusing the backend's MinIO env var names rather than
  inventing its own.
- **No over-engineering.** No speculative abstractions, no
  hypothetical-future handling, no half-finished work.
- **Minimal comments** — only a non-obvious *why*, never *what*.
- **This is a standing rule, not a one-time cleanup.** Spot a
  pre-existing duplicate → flag it, then fix it once agreed, don't add
  a third copy.

### Frontend CSS: global vs. CSS Modules

`frontend/src/styles/global.css` holds only true cross-cutting
design-system primitives — app shell/navbar chrome, the mobile bottom
action bar, macro-page (`sf-section`) layout, buttons, card/form/field
primitives, table/list/badge primitives. These stay global classes
(`sf-*`) because dozens of pages reference the class names directly.

Anything scoped to one feature or component belongs in a colocated
`Component.module.css` (e.g. `PolarChart.tsx` / `PolarChart.module.css`),
imported as `styles` and referenced as `styles.someClass` (camelCase
locals). A stylesheet shared by a small, known set of consumers (e.g.
three club/group detail layouts sharing an entity-header look) is fine
as one shared module — it doesn't need to be strictly 1:1.

Rule of thumb: grep how many files would reference the class. A
handful in one feature area → CSS Module. Spread across most
pages/`pages/**` → global.css. Combine both with a template string:
`` className={`sf-muted ${styles.hint}`} ``.

#### `Section` vs. `Card`

Two page-block primitives in `components/ui/`, and picking the wrong one
is what made the detail pages nest a box inside a box:

- **`Section`** (`sf-block*` in global.css — the name `sf-section` was
  already taken by the macro-page layout) is the default for a
  *page-level region*: heading + optional actions + content, no border,
  surface, radius or inset. Stacked `Section`s read apart via a hairline
  + spacing, not boxes.
- **`Card`** (`sf-card*`) is reserved for an *innermost discrete
  entity* — one boat, one mark, one entry — typically tappable. A region
  that lists card-shaped items is a `Section` containing those items (or
  flat `sf-strip` rows), never a `Card` of `Card`s.

`.sf-bleed` (global, mobile-only) cancels `.sf-main`'s `--sf-page-pad`
inset so a map/chart child of a `Section` runs edge-to-edge on a phone —
the replacement for the old `sf-card--flush` / `sf-card--flush-top` map
wrappers.

---

## Repository Structure

```
.
├── CLAUDE.md                   # This file
├── README.md                   # Project scope: what XGSail is / isn't
├── pyproject.toml              # Repo-root pytest config only — not a build target
├── docs/
│   ├── device-protocol.md      # Hardware-agnostic device integration protocol
│   ├── estimation-pipeline.md  # Position/wind/maneuver estimation pipeline
│   ├── native-apps.md          # Capacitor iOS/Android shells, Bearer auth for native
│   └── ota-updates.md          # ota-service architecture + manifest/bundle contract
├── backend/                    # FastAPI REST API (API-only, no static mount)
│   ├── main.py                 # Composition root: CORS, RBAC startup seed, routers
│   ├── routers/                # One module per resource (see below)
│   ├── services/                # Business logic: course, geo, gpx, wind, import, maneuvers, scoring, boat_merge
│   ├── repositories/           # Data-access layer (base.py + sql/ implementation)
│   ├── auth/                   # Passwords, tokens (cookie + Bearer), permissions, RBAC seed
│   ├── db/                     # SQLAlchemy models + base
│   ├── storage/                # Object-store abstraction (S3/MinIO)
│   ├── schemas/                # Pydantic request/response DTOs
│   ├── alembic/                # DB migrations
│   ├── legal.py                # Legal-doc version tracking (copy lives in frontend)
│   ├── onboarding.py           # Guided-tour ID tracking (copy lives in frontend)
│   ├── support.py              # Support-prompt cadence (copy lives in frontend)
│   └── richtext.py             # Prose HTML sanitization (nh3), the stored-XSS boundary
├── frontend/                   # Vite + React + TS SPA, wrapped via Capacitor
│   ├── src/                    # pages/, components/, hooks/, styles/ (see below)
│   └── ios/App/XGSailWatch Watch App/   # Native watchOS companion (hand-added Xcode target)
├── ota-service/                # Standalone Node/Express OTA update server (native app)
├── libs/
│   └── xgsail_windfusion/      # Shared Python wind-fusion/calibration package
├── workers/                    # Heavy-processing tasks — same handler runs on AWS
│   ├── process_upload/         # GPS/CSV/GPX → analysis
│   ├── train_maneuver/         # Maneuver-detector training/export
│   └── video/                  # MP4 → HLS via ffmpeg
├── tests/                      # pytest suites (see "Commands")
│   ├── backend/
│   ├── windfusion/
│   └── worker/
├── deploy/                     # Self-hosted + prod stack: Dockerfile.backend,
│   │                           # docker-compose.prod.yml, minio-init.sh
├── scripts/                    # One-off/maintenance: migrations, backfills,
│   │                           # calibration, deploy-ota.sh
├── docker-compose.yml          # One-command local (self-hosted) stack
└── docker-compose.dev.yml      # Dev overlay: Vite dev server with HMR
```

`frontend/src/pages/` groups routes by area: `diario/` (activities,
sessions, races, regattas, import), `gruppi/` (clubs, groups, devices),
`profilo/` (account, boats, devices, password), `admin/` (superadmin).
Shared UI primitives live in `components/ui/`; data fetching in
`hooks/` (TanStack Query).

### Backend routers (`backend/routers/`)

One module per resource, registered in `routers/__init__.py`
(`ALL_ROUTERS`): `app_config`, `legal`, `auth`, `users`, `rbac`,
`boats`, `clubs`, `groups`, `posts`, `note_templates`, `devices`,
`integrations`, `activities`, `sessions`, `live_recordings`, `polars`,
`regattas`, `racedays`, `races`, `device_api`, `imports`, `ingest`,
`uploads`, `download`, `wind`, `osm_poi`, `system`, `video`.

Principals differ per router: cookie- or Bearer-authenticated users
(most routers — see "Native apps"), `DeviceKey`-authenticated hardware
(`device_api`), hook-token system callers (`system` + the `ingest`
webhook), and the token-signed upload/download proxies (`uploads`,
`download`). Devices integrate via the claim + device-key flow in
`docs/device-protocol.md` — there is no device-specific upload path
left in the router layer.

---

## Data Flow

```
[Device or manual import]
  → presigned upload URL (backend/storage) → PUT to S3/MinIO

[Object storage]
  ObjectCreated event → webhook (MinIO: /hooks/minio, or S3 notification)
  → backend invokes workers/process_upload (or workers/video for video
    files) over HTTP — same container image also runs as a Lambda in
    the AWS deployment
  → worker writes processed/normalized data back to storage + updates
    ingestion status in Postgres via the backend

[Frontend / native app]
  SPA or Capacitor shell (frontend/) → REST API (backend/) → Postgres
  (metadata) + object storage (processed data, referenced by
  data_ref/raw_ref)

[Two crew members, one outing]
  each phone records its own track → both upload as manual imports →
  find_or_create_session merges them by boat + time window into ONE session,
  both recorders added to session_crew, both tracks kept as session_uploads
  → nav_source resolves which track the analysis uses
  → /api/live-recordings announces a recording in progress so the second
    person can join it deliberately; /sessions/{id}/uploads/{id}/detach
    undoes a merge that was wrong (docs/device-protocol.md §10–§11)

[Native app OTA update]
  frontend/dist → scripts/deploy-ota.sh (zip + checksum + upload) →
  MinIO app-updates/{manifest.json, bundles/{version}.zip} →
  ota-service polls/serves manifest.json to the native app via
  @capgo/capacitor-updater — independent of backend/Postgres
```

See `docs/estimation-pipeline.md` for how raw GPS/wind readings become
the legs/maneuvers/VMG/polar numbers shown in session analysis,
`docs/device-protocol.md` before changing anything upload/ingestion-
related, and `docs/ota-updates.md` before changing anything in
`ota-service/` or `scripts/deploy-ota.sh`.

---

## Self-Hosted Stack

```bash
cp .env.example .env   # edit secrets — never commit a real .env
docker compose up --build
```

Services (see `docker-compose.yml`): `postgres` (metadata), `minio`
(S3-compatible blob storage, console on :9001), `backend` (FastAPI,
:8000), `frontend` (nginx serving the SPA build + proxying `/api` →
backend, same-origin), `ota-service` (Express, :8081, native-app OTA
updates — talks only to MinIO, no backend/DB dependency), `wind-scheduler`
(a `curl` loop that periodically triggers the backend's weather-provider
fetch), plus the `process_upload`/`video` workers invoked by the backend
on MinIO upload events. `train_maneuver` is defined in the same file but
sits behind the `training` Compose profile, so a plain `docker compose up`
does **not** start it — see `deploy/README.md` for the full request-flow
diagram and how the self-hosted (MinIO) path differs from the AWS
(S3/Lambda) path — same code, env-gated.

---

## Native apps (iOS/Android)

`frontend/` is wrapped in Capacitor (`frontend/capacitor.config.ts`) to
produce iOS 14+/Android 8+ shells around the same web app — the
generated `frontend/ios/`/`frontend/android/` native projects are only
touched at native build time, never by `vite dev`/`vite build`.

**Auth differs from web**: the web app uses httpOnly cookies
(`sf_access`/`sf_refresh`), which depend on same-origin proxying (Vite
dev proxy locally, nginx in prod). A Capacitor WebView talks
cross-origin to the real backend host instead, where cookie jars
aren't reliable — so native uses `Authorization: Bearer <jwt>`.
`backend/auth/permissions.py`'s `current_user()` accepts a Bearer
header first, falling back to the cookie for web. Native refresh
tokens come back in the `/auth/login`/`/auth/refresh` response body and
are persisted via `@aparajita/capacitor-secure-storage` — never
`@capacitor/preferences` (unencrypted) or `localStorage`.

**Offline-tolerant cold start (native only)**: if fetching capabilities
fails with a network error (not a 401/403) and a native refresh token
exists, `AuthContext` restores the last-known `Capabilities` snapshot
from `localStorage` (`services/offlineCache.ts`, key `sf_caps_cache`)
instead of bouncing to `/login`, and flags this via `identityStale`
until the app is back online and re-verifies. Only the capabilities
object goes into `localStorage` this way — never a token, which stays
in secure storage/memory as above. `RegistraPage.tsx` similarly caches
the "my boats" list and last-used boat id (`services/boats.ts`) so the
recording flow's boat picker still works with no connectivity, and
retries deferred uploads both on network recovery and on app foreground.

**OTA updates** for the native shell's JS bundle are served by
`ota-service/` (see "Data Flow" and `docs/ota-updates.md`), not through
app-store review — only the bundle updates this way, not native
Capacitor plugin changes, which still require a store release.

---

## Weather Data Integration

- **NOAA NDBC buoys**, **METAR** stations, and **Cumulus** personal
  weather stations, fetched via `backend/services/wind_providers/` and
  exposed through `backend/routers/wind.py`.
- `wind_stations` / `wind_observations` (see `backend/db/models/wind.py`)
  cache this external data locally (avoids re-fetching on every render,
  preserves history past whatever window the upstream API retains).
  Station selection/aggregation, the sensor-fault guards, and the
  estimation algorithms that turn raw observations into a usable wind
  signal are documented in `docs/estimation-pipeline.md`; the underlying fusion/calibration math
  lives in `libs/xgsail_windfusion`, shared with `workers/process_upload`.

---

## Gotchas

- **The native watchOS app doesn't rebuild from the React frontend.**
  It's a hand-added Xcode target at `frontend/ios/App/XGSailWatch Watch
  App/`, maintained separately — editing `frontend/src` has no effect on it.
- **Devices have no separate upload path in the router layer.** All
  device data flows through the same presigned-upload + webhook
  pipeline as manual imports; don't add a device-specific endpoint,
  extend the claim + device-key flow in `docs/device-protocol.md` instead.
- **A regatta's participants are not its club's members.** Club
  regattas are routinely sailed by visiting boats, so anything gating
  race participation on club membership (`member_clubs`, `activity.manage`)
  is wrong by construction — go through `regatta_entries`, which keys
  on the boat. See "Auth" above.
- **`regatta_entries` is not `results`.** An entry says a boat is
  expected at the event and exists *before* the racing; a result
  carries scoring. Pre-creating results rows as a start list puts
  boats in the standings before they have sailed.
- **`regattas.join_code` must never reach a public payload.** Regattas
  are pub-readable; the code is kept out via
  `RegattaORM.__wire_exclude__` and served only by the manage-gated
  `/join-code` endpoint. It is also deliberately absent from
  `_REGATTA_FIELDS`, so a generic `PATCH /regattas/{id}` can't set it.
- **A manual entry's `boat_id` is NULL, and `get_entry(regatta_id, None)`
  must not match it.** `boat_id == None` renders as `IS NULL` in SQL, so
  without the guard in `SqlRegattaRepo.get_entry` a caller passing a null
  boat would be authorized against an arbitrary manual entry. The same
  reason `GET /standings` filters `None` out of its `boat_ids` union — a
  null would become a phantom ranked row (no boat to display). That filter
  is only about the *ranked rows*, though — manual entries are still visible
  and still counted, by two separate routes:
  - `GET /standings` returns them in a sibling `unranked` list, keyed by
    `entry_id` (never `boat_id`) and carrying only `display_name`/
    `display_sail_number`, which the frontend renders as muted, medal-less
    rows after the ranked ones. Never move them into `standings`.
  - the RRS A9 penalty's fleet size (`scoring.total_entered_count`)
    deliberately counts manual entries back in, or a club whose start list is
    mostly paper entries would score every DNF/DNS against a fleet far
    smaller than the one that actually started.
  Ranked rows whose boat no longer resolves (`_boat_summary` → `None`) are
  dropped from the payload, so `standings[].boat` is never null — several
  frontend consumers read `row.boat.id` directly.
- **Official standings win over computed ones.** If any
  `official_standings` row exists for a regatta, `GET /standings` serves
  those instead of running the scoring algorithm, and flags the response
  with `is_official`. Deleting the rows reverts to computed. Don't add
  scoring logic assuming the computed path always runs.
- **A boat's scoring division comes from its `regatta_entries` row, never
  from `results` or from the boat's own class.** `results` deliberately has
  no `division_id` — it derives from the entry so there is one source of
  truth (`backend/db/models/race.py`, `RegattaEntryORM.division_id`).
  `regattas.class_id` is unrelated display metadata; don't wire it into
  scoring as if it grouped boats.
- **A race's `division_id IS NULL` means it counts for every division, not
  "no division."** That's the normal case — one start, all divisions racing
  together — versus the rarer race reserved to a single division. Treating
  NULL as "unassigned" in `scoring.division_slices` or `GET /standings`
  would silently drop that race from every division's ranking.
- **`GET /standings`'s top-level `races`/`standings`/`unranked` keep
  meaning "every race, one regatta-wide ranking," even for a regatta with
  divisions.** `divisions` is an additive array alongside them, empty when
  a regatta has none. Don't "simplify" by moving everything under
  `divisions` — older native OTA bundles read the top-level lists and
  don't know the key exists.
- **A guest boat's creator is a plain `owner`, not a new role, and
  `sessions.boat_id` stays `NOT NULL`.** `boats.is_guest` only flags the row
  as an unverified placeholder (`backend/db/models/boat.py`); the creator
  gets `user_boats.role="owner"` exactly like any boat creator. That's
  deliberate — a nullable `sessions.boat_id` with a free-text name (mirroring
  `regatta_entries`' paper entries) was rejected because every existing
  membership-keyed check (`_is_manager`, `find_or_create_session`, progress
  stats, session-split) would need a null-boat fallback. Don't add one; a
  guest boat is a real boat everywhere except the picker.
- **`repos.boats.list()` hides guest boats unless `include_guest=True`.**
  It feeds the instance-wide `BoatPicker` that enters boats in regattas, so
  an unverified placeholder must not appear there by default. But
  `backend/auth/permissions.py`'s capabilities builder must pass
  `include_guest=True` — otherwise a guest boat's own creator would vanish
  from their own `boats_owner` capability and fail `StartChecklist`-style
  "do you have a boat yet" checks. A new caller that forgets the flag
  silently drops a user's own guest boats from their capabilities.
- **`PATCH /boats/{id}` cannot flip `is_guest`/`guest_created_by` by
  design.** `SqlBoatRepo.update()` only writes `_UPDATABLE_FIELDS`, which
  excludes both — a plain boat edit must not be able to promote a
  placeholder and skip the claim/approval flow. `clear_guest()` (called
  only from `boat_merge.promote_guest_boat`) is the sole way out.
- **Approving a boat claim is an authorization decision, not a
  courtesy.** It grants `user_boats` membership, and boat membership is
  what gates session read access (`backend/routers/sessions.py`), so
  `approve_claim` is gated to the guest boat's own owner/admin
  (`_require_claim_approver`) and `_require_pending_claim` checks
  `claim.boat_id == boat_id` before anything else — the same class of bug
  as the `get_entry(regatta_id, None)` gotcha above: without that check,
  the manager of an unrelated boat B could resolve a claim filed against
  boat A.
- **`boat_claims.boat_id` is `ON DELETE CASCADE`, so merging the guest boat
  away deletes the very claim being resolved.** `approve_claim` calls
  `repos.boats.resolve_claim()` *before* `boat_merge.merge_boat()` for
  exactly this reason — merge first would leave nothing to mark approved.
  Don't reorder those two calls.
- **`boat_merge.merge_boat` refuses a source that isn't `is_guest`,
  because it deletes the source boat outright.** In `SqlBoatRepo.merge_into`,
  the three tables unique on `(parent, boat_id)` — `regatta_entries`,
  `results`, `official_standings` — drop the *guest's* colliding row rather
  than the target's, since the target is the record the organizer actually
  entered/scored. Polar curves are never combined (`bulk_upsert` semantics
  mean two curves would leave contradictory rows in the same twa/tws bin) —
  the target's curve wins if it has one. `live_recordings` rows are dropped,
  not migrated, same reasoning as the presence-not-data gotcha below.
- **A restored offline capabilities snapshot is a UI hint, not an
  authorization decision.** `AuthContext`'s `identityStale`/cached `caps`
  (see "Native apps") only steer what the native app *shows* while
  offline; every mutation is still checked server-side via
  `current_user()` once the request actually reaches the backend. Don't
  add a client-only check that trusts stale `caps` to gate something the
  server doesn't also enforce, and never extend `offlineCache.ts` to hold
  anything token-shaped — only `localStorage`-safe, non-secret data.
- **A deployed database can only be repaired by a new revision.** Deploys
  are unattended (Watchtower pulls `*-latest` on the VM) and the backend
  runs `alembic upgrade head` at startup, so an environment already
  stamped at revision N will never re-run a *corrected* revision ≤ N — and
  a fix-up script somebody has to run by hand simply never runs. When a
  shipped migration turns out to be wrong, fix it in place **and** add a
  follow-up revision that repairs the databases which already applied the
  broken one, written so every statement is a no-op where the schema is
  already right (`0045_reconcile_manual_entry_schema.py` is the worked
  example). Do not delete such a revision as "redundant" — it is the only
  thing standing between a corrected file and a still-broken production.
- **Demo tour data is keyed on the id in the request path, and nothing
  anywhere turns "demo mode" on.** `matchDemoRequest` (in
  `frontend/src/demo/`) intercepts a call inside `api/client.ts`'s
  `request()` only when the path carries a `DEMO_UUID_PREFIX` id, so a
  request about a real record can never be served a fixture. Don't
  replace that with a mode flag, and don't fake a *list* endpoint —
  a list has no demo id in its path, which is exactly what keeps the
  demo out of the user's own data. Mutations on a demo id are silent
  no-ops: a guided demo is read-only, and an error toast mid-tour is
  worse than nothing happening.
- **The demo records are granted membership in `useCapabilities`, never
  in `caps.memberships`.** A club's news tab, a boat's notebook/crew and
  a session's add-photo actions are all gated on membership, so
  `memberOfClub`/`isBoatOwner`/`isBoatManager` return true for a demo id
  (`isDemoId`). Injecting the ids into `caps.memberships` instead would
  break every consumer that reads those arrays as "does this user own a
  boat yet" — `StartChecklist` among them. Membership only: `can()` is
  deliberately untouched, so no manage UI appears on a record that
  can't be edited.
- **A tour is only marked seen once a step actually rendered.** `Tour.routes`
  are prefixes, so a tour can auto-start on a page where none of its steps
  exist (`/profilo/barche/{id}/quaderno` matches the boat tour). Without
  the `anyStepShown` guard in `OnboardingContext`, that run would spend
  the one automatic showing the account ever gets, in silence.
- **Native auth is Bearer, not cookie.** Adding an endpoint that reads
  auth state directly from the request cookie (instead of going
  through `current_user()`) silently breaks it for the native apps —
  see "Native apps" above.
- **`ota-service/` is a separate deployable with its own env vars and
  no backend/DB dependency**, even though the base `docker-compose.yml`
  does start it alongside everything else. It reuses the backend's
  MinIO credential var names by convention (see "Environment
  variables"), but never talks to Postgres or the FastAPI backend, so a
  missing OTA update is never a backend bug — check `ota-service`'s own
  logs/env, not the backend's.
- **`scripts/deploy-ota.sh` rebuilds the frontend independently of the
  native shell build, so it needs its own copy of every native-only env
  var — a full native release setting one in `.env.native` does NOT
  carry over.** `VITE_PUBLIC_WEB_ORIGIN` (see "Native apps") is required
  there for exactly this reason: an OTA bundle built without it silently
  reintroduces broken shareable links (join links, etc.) in every
  already-installed app, even though the original store/sideload build
  was correct. When adding a new native-only `VITE_*` env var, add it to
  `scripts/deploy-ota.sh` and its CI invocation
  (`.github/workflows/docker-publish.yml`'s `deploy-ota` job) at the same
  time as `.env.native.example`, or it silently drops out of every OTA
  update after the first.
- **Repo-root `pyproject.toml` only configures pytest.** It is not a
  package manifest for the backend, a worker, or `libs/
  xgsail_windfusion` — each of those has its own build setup; don't
  add dependencies to the root file expecting them to reach any
  deployable.
- **A boat's notebook (`boat_notes`) is member-only even though
  boats are pub-readable.** `_boat_payload` serves boats to
  anonymous callers, so the notebook is deliberately *not*
  embedded in it — it has its own `GET /boats/{id}/notes` behind
  the same member gate as `/members`, with writes restricted to
  `_is_manager`. Don't "simplify" it into the boat payload.
  `boats.notes` (a single public Text column) was replaced by this
  table in revision `0047`, which migrated existing values into
  a first entry.
- **A boat has two kinds of notes with two different audiences —
  don't gate one like the other.** `boat_notes` (the setup
  notebook) is readable by **any** boat member, `visitor` included.
  `sessions.notes` (the per-outing crew log) is readable only per
  `session_notes_visible_to`: the crew of *that* session or the
  boat's owner/admin, widening to the session's normal audience only
  when `notes_shared` is set. So `GET /boats/{id}/session-notes`
  gates twice — boat membership to enumerate, then per-session
  visibility for the content — and a list endpoint that filtered only
  on boat membership would hand every private crew note to every boat
  visitor. The per-item filter runs after the SQL `LIMIT`, so a short
  page does not mean the list ended; topping it up would leak how many
  rows the caller can't see.
- **Prose fields store sanitized HTML, and the sanitizer lives on the
  Pydantic DTO type, not in the router.** A new endpoint whose DTO uses
  a bare `str` for a prose field bypasses it entirely — and since
  boats/clubs/groups/regattas are pub-readable, that is stored XSS
  against logged-out visitors, not just a formatting bug. Use
  `RichTextBasic`/`RichTextFull`/`RichTextPost` from `backend/
  richtext.py`.
- **`sessions.notes_plain` is the column that search and the "has
  notes" check read, never `sessions.notes`.** An emptied note is
  `<p></p>`, which is not the empty string, so a blank check against
  `notes` would put every session of the boat in the logbook as an
  empty row; and an `ILIKE` against `notes` would match markup
  (`strong`, `li`, `href`) and miss text split by a tag. The mirror is
  derived in `SqlSessionRepo.create`/`update`, so nothing can write
  `notes` without it.
- **A note editor's dirty-check ref is not its discard snapshot.** Every
  editor behind `useAutoSaveOnClose` keeps an `original*Ref` for
  `isDirty()`, and that ref tracks *last saved* — it is refreshed by each
  successful autosave (and, in `SessionDetail`, by the server-sync
  effect). "Scarta modifiche" has to restore what the editor was opened
  with, so each call site keeps a **second**, never-refreshed `opened*Ref`
  captured in its open handler. Reverting from the dirty-check ref would
  restore the autosaved text the user is trying to throw away. A new
  autosave editor needs both refs, and the one it opens for a
  brand-new record also needs the delete branch: if a periodic autosave
  already created the row, discarding must remove it, since reverting to
  a record that never existed is meaningless (`discard.destroysRecord`).
- **A local recording's live state is memory-only; the on-disk index is
  not.** `nativeRecording.ts` keeps `active` (and the plugin watcher) in a
  module variable, so a `recording`/`paused`/`uploading` entry found in
  `recordings/index.json` at startup is by definition an orphan of a dead
  process — and nothing self-heals it: `stop()` returns early without an
  in-memory `active`, and the upload retry only looks at `stopped`/`failed`.
  Such an entry used to render in the Registra sheet as a permanently
  "recording" row whose elapsed time grew for days, with every control
  hidden (upload is gated on stopped/failed, delete was hidden for
  recording/paused). `reconcileOrphans()` on first load and the `interrupted`
  status exist for exactly this; don't reintroduce a status the row's
  controls can't act on, and keep delete unconditional there — that list
  never contains the active recording.
- **`RichText.tsx` is the only place in the frontend allowed to use
  `dangerouslySetInnerHTML`.** Rendering a prose value any other way
  either shows raw tags or reintroduces the XSS surface. One-line
  prose previews (card subtitles, `title=` attributes) use
  `richTextExcerpt`, never `RichText` — a `<p>`/`<table>` injected
  into a single-line slot breaks the layout.
- **The editor's Tiptap extension set (`frontend/src/components/ui/
  richTextSchema.ts`) and the backend allow-list (`backend/richtext.py`)
  must stay in lockstep.** A tag the editor can produce but the
  sanitizer drops is silently eaten on save, and the user watches
  their content disappear.

- **Two people recording one outing land on one session, automatically.**
  `find_or_create_session` reuses a session of the same boat whose window
  overlaps within `SESSION_MERGE_GAP_MINUTES`, and adds both recorders to
  `session_crew`. Everything downstream has to assume a session has several
  contributors: each keeps its own `session_uploads` row, physio stays
  per-person, and only one track is analysed
  (`nav_source.resolve_nav_upload`). `docs/device-protocol.md` §10 is the
  contract; the inverse is `POST /sessions/{id}/uploads/{upload_id}/detach`.
- **`ON DELETE SET NULL` does not fire on `UPDATE`.** Re-parenting a
  `session_uploads` row leaves `sessions.primary_nav_upload_id` naming a track
  the session no longer owns, and `resolve_nav_upload` degrades quietly (logs,
  falls back to the ranking) — so the corruption stays invisible until someone
  wonders why their explicit choice stopped applying. Anything that moves an
  upload between sessions clears/carries the pointer by hand
  (`services/session_split.py`). Same file is the only user of
  `SqlSessionRepo.recompute_window`, the one method that can *shrink* a
  session window — `extend_window` widens monotonically, which is right while
  data is arriving and wrong once some has left.
- **`session_streams.first_t`/`last_t` are NULL on every stream written before
  revision `0050`, and nothing backfills them.** A migration must not read
  object storage, and copying `sessions.started_at`/`ended_at` in would be
  wrong — that is the *merged* window, the very thing per-stream bounds exist
  to disambiguate. So `nav_source` skips its coverage criterion entirely
  unless every candidate is measurable; a ranking change that scores NULL as
  "covers nothing" silently demotes every historical track.
- **`live_recordings` is presence, not data.** No row creates or reserves a
  session, an activity or an upload, liveness is a read-time predicate over
  `last_seen_at` (no cleanup job exists to add one to), and the banner it
  feeds is a UI hint — never an authorization decision, same rule as the
  offline capabilities snapshot. The announce/heartbeat/end calls live in
  `hooks/useLiveRecordingPresence.ts`, mounted in `AppShell`: not in
  `services/nativeRecording.ts`, which is deliberately free of API/auth
  imports so recording keeps working with no server at all, and not in
  `RegistraPage`, which unmounts while recordings carry on. Every such call is
  best-effort and must never touch the recordings index or block a recording.
- **`POST /imports/{id}/complete` returns keys that `GET /imports/{id}` does
  not** (`session_merged`, `session_crew`). The wizard polls the GET
  afterwards and assigns it to the same state, so anything that folds those
  keys into the polled row erases the merge notice on the first tick — see
  `useImportUpload`'s separate `mergeInfo`.
- **`?mine=true` on activities means "created by me **or** crewed by me".**
  A shared outing lives in the private `solo` activity of whoever uploaded
  first, so an authorship-only filter hid the second recorder's own outing
  from their own diary. The clause is SQL and runs before `LIMIT`/`OFFSET`,
  for the reason `_visibility_clause` documents.
- **`wind_cache.json`'s `real_stations` is a multi-station list, not one
  station's series.** `gather_raw_wind` now fuses up to 3 in-range stations
  instead of only the nearest, concatenating every station's rows into that
  one list — a consumer must group them by `station_id` first
  (`_station_groups` in `workers/process_upload/processing/
  wind_estimation.py`) or it interpolates two stations' readings across each
  other into a zig-zag. A cache written before this change carries no
  `station_id` at all, which is why the grouping key falls back to the
  station's `(station_lat, station_lng)`. Getting this wrong degrades the
  wind series silently — nothing errors.

- **A real weather station reporting nonsense is worse than one
  reporting nothing, because it outweighs every model in the fusion.** A
  dead vane keeps serving well-formed numbers — one frozen direction
  forever — so nothing errors while TWA, points of sail, VMG and the polar
  all come out ~190° wrong for every session at that spot (this is real,
  not hypothetical: see `tests/backend/test_wind_quality.py`). Two guards:
  `wind_providers/_units.py` rejects out-of-range values at the parser
  (a station's `-9999` sentinel parses as a float perfectly well), and
  `services/wind_quality.py` drops a station whose readings are
  mechanically faulty, called from `_real_station_observations` so the one
  check covers both the fused wind and the map's arrow. It excludes a
  station **wholesale** rather than nulling the bad field —
  `weighted_wind_mean` averages vectors, and a vector needs both
  components. Wrong coordinates and a misconfigured wind unit stay
  undetectable from the data; only `calibrate_wind_weights.py
  --ablate-stations` surfaces those.

- **A club and an OSM sailing club can be the same place, and `clubs.osm_ref`
  is the only thing that says so.** The explorer map draws clubs from two
  independent sources — our own rows and Overpass POIs — so the same club
  appears twice until someone creates it from the POI or claims an existing
  club as that element (`PATCH /clubs/{id}`, already manage-gated: claiming is
  a management act on that club, not a new permission). The column is UNIQUE
  because that constraint *is* the anti-duplication guarantee, and it holds
  `"{osm_type}/{osm_id}"` verbatim so the frontend compares it to
  `NauticalPoi.id` with no parsing on either side. The map hides a claimed
  POI **only while the clubs layer is on** — the club's pin is what replaces
  it, and hiding both would erase the place from the map. Same rule as the
  unnamed-POI filter next to it: never hide something whose replacement isn't
  being drawn.

- **A ticked map layer that draws nothing must always say why.** The browser no
  longer queries Overpass: it calls our own `GET /osm-poi`, and
  `backend/services/osm_poi.py` owns the Overpass fetch behind a per-cell cache
  (`CELL_DEG = 0.5`, refetched at most every `CELL_TTL_DAYS`, a failed cell
  retried no sooner than `RETRY_AFTER_FAILURE_MIN`). Freshness is driven by the
  read path, not by a scheduler: a never-seen cell is filled inline, and one
  expired cell the request touched is re-fetched **after** the response as a
  background task, so a user never waits on Overpass for data we already have.
  The only cells whose age anyone can observe are the ones being looked at,
  which is why that beats a timer — and why the stack needs no extra container
  for it. `POST /api/system/osm-poi/refresh` remains as the manual lever.
  A request whose bbox still has
  unfetched cells answers `coverage: "partial"`, which the frontend treats
  exactly like an error. That matters because the layer is also zoom-gated in
  two tiers: clubs from `CLUBS_MIN_ZOOM = 9`, POIs and weather stations only
  from `NEAR_DETAIL_MIN_ZOOM = 11` (clubs are the layer worth spotting from
  furthest out). Every one of those produces the same symptom — a checked box
  and an empty map, indistinguishable from "there is nothing here", already
  reported twice as a regression it wasn't. `useNauticalLayers` therefore
  returns one flag per reason (`clubsHidden`, `nearDetailHidden`, `poiFailed`)
  and `MapLayerToggles` renders each, so incomplete data is surfaced, not
  swallowed.

- **The Overpass endpoint list is configuration, and a single entry still has
  to be a list.** This happened: narrowing `ENDPOINTS` to one instance by
  commenting the others out left `("https://overpass-api.de/api/interpreter"` +
  `)` — no trailing comma, so a plain string. `for endpoint in ENDPOINTS` then
  iterated its *characters*, POSTing to `"h"`, to `"t"`, to `"t"`... 39 times.
  Every one raised `MissingSchema`, every one was swallowed by the loop's
  `except Exception` and logged as an endpoint that failed, and **not one
  packet left the box** while the logs read exactly like an Overpass outage.
  The tell in the database is total: `osm_poi_cells.fetched_at` NULL
  everywhere and `osm_pois` empty — no successes at all, as opposed to the
  partial, patchy damage a real outage or the remark bug below leaves. Hence
  `OVERPASS_ENDPOINTS` and `parse_endpoints`: the list is swapped without
  touching code, and a malformed one is a startup error. `scripts/
  check_overpass.py` is the other half — run it on the host that is failing
  and it separates DNS, egress, rate limiting and a bad instance, none of
  which the application can tell apart after the fact.

- **Overpass reports a runtime error as HTTP 200, and believing it wipes the
  map.** A query that times out or runs out of memory upstream — what a
  throttled or overloaded instance returns — comes back as a perfectly valid
  JSON body with an empty `elements` list and a `remark`. Treating that as an
  answer is not a lost fetch, it is *cache poisoning*: `replace_cell_pois`
  deletes the cell's real POIs, `fetched_at` gets stamped, and the place reads
  as fully covered — so the frontend shows no warning at all — for the whole
  `CELL_TTL_DAYS` window. `check_payload` in `services/osm_poi.py` is the
  guard, and revision `0055` clears `fetched_at` on the cells that were
  already blanked. Anything that parses an Overpass response must go through
  it; success is never just a 2xx.

- **Every Overpass query now leaves from one server IP, so our own concurrency
  is the rate limit.** That is the flip side of moving the fetch off the
  browser: overpass-api.de rations per IP (a couple of concurrent slots plus a
  rolling quota), and the whole instance shares one. Hence `_query_gate` (one
  query in flight per process, and the read path takes it *non-blocking* —
  a request that cannot have the slot serves the cache and reports `partial`
  rather than queueing) and the circuit breaker, which parks the layer after
  `BREAKER_FAILURES` consecutive failures and immediately on a 429/504. The
  per-cell `RETRY_AFTER_FAILURE_MIN` window does not cover an outage, because
  every *new* cell is still a first attempt — that is exactly what turns a
  slow Overpass into a slow API. Don't add a code path that calls Overpass
  around the gate.

- **`GET /osm-poi` runs behind nginx's 60 s `proxy_read_timeout`, and the
  backend route is sync, so it burns a threadpool slot while it waits.** A
  cold fill is inline and sequential, so cells x endpoints x socket timeout is
  the number that matters, not one timeout — the original 4 x 2 x 90 s could
  reach twelve minutes, long enough to 504 the user and, with enough of them,
  exhaust the threadpool and stall the whole API rather than just the map.
  `READ_FILL_BUDGET_S` is a wall-clock deadline threaded down into each
  `requests.post`, so the read path stops trying endpoints once the budget is
  gone. Keep it comfortably under the nginx timeout in `frontend/nginx.conf`;
  background fills get the looser `BACKGROUND_FILL_BUDGET_S` because nobody
  is waiting on them.

If new gotchas turn up (a non-obvious break, a silent trap), add them
here — this is the highest-value section for avoiding a wrong change.

---

## Environment variables

See `.env.example` for the full list with defaults. Grouped by concern:

- **DB:** `DATABASE_URL`
- **Storage:** `STORAGE_TYPE` (`s3`/`minio`), `AWS_ENDPOINT_URL` (MinIO
  only), `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, bucket name
- **OTA service** (`ota-service/`, own process): `OTA_PORT` (default
  8081), `SAILFRAMES_BUCKET`, `SAILFRAMES_OTA_PREFIX`,
  `SAILFRAMES_S3_ENDPOINT`, `SAILFRAMES_S3_PUBLIC_ENDPOINT` (must be
  publicly reachable — presigned bundle URLs are signed against it, not
  the internal endpoint), plus `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD`
  reused verbatim from the backend's MinIO config by convention — don't
  invent separate OTA-specific credential var names.
- **Overpass** (`backend/services/osm_poi.py`): `OVERPASS_USER_AGENT`,
  `OVERPASS_ENDPOINTS` (comma/space-separated instance URLs, unset = the
  built-in defaults). The endpoint list is configuration precisely because it
  is what gets changed when Overpass misbehaves — see the gotcha above.
- **Track thumbnails** (`workers/process_upload/thumbnail.py`):
  `THUMBNAIL_TILE_URL` (OSM tile template, empty disables the map
  background), `THUMBNAIL_TILE_USER_AGENT` (sent on every tile request)
- **Auth/JWT:** JWT signing secret, token expiry
- **Weather APIs:** NOAA/METAR/Cumulus endpoints — optional, provider
  is skipped if unset
- **Frontend:** API base URL, map tile provider
- **App:** debug flag, environment name, frontend URL (CORS)

---

## Testing policy

- **Critical or bug-prone paths** (auth, migrations, ingestion,
  anything that broke before) get an automated, reusable test — part
  of the normal test run, not a one-off manual check.
- **Bug fixes get a regression test** reproducing the bug first, then
  passing once fixed. Default, not optional.
- **Migrations are gated in CI, not by pytest.** The pytest suite is
  database-free, so a migration that diverges from its ORM model can
  pass every test and still 500 in production (this happened — see the
  `test` job comment in `.github/workflows/docker-publish.yml`). The
  `test` job runs `upgrade head` from an empty Postgres, `alembic
  check` for drift, and a `downgrade base` round trip; `publish` and
  `deploy-ota` both `needs: test`. **Any change to `backend/db/models/`
  needs a matching migration, and vice versa** — run the three commands
  in "Commands" locally before pushing.

---

## Planning workflow

**Standing authorization:** the user of this repo has pre-authorized
subagent delegation as the default execution mode for the tasks
described below. Treat the workflow here as an explicit, already-given
request to use the `Agent` tool — it does not need to be asked for
again per task. Do not ask for confirmation before spawning; just
announce the split.

The workflow, in order:

1. **Plan before executing.** For anything multi-step, multi-file, or
   ambiguous, write a short plan first: what changes, in what order,
   why. Skip only for a genuinely small/obvious change (one file, no
   design decision) — do that inline.
2. **Split the plan into units** along two axes: logical boundary
   (a unit is independently verifiable and owns its own files) and
   difficulty (mechanical vs. requires judgment). Do not split below
   the point where handoff costs more than the work.
3. **Assign each unit a model + depth** — this is a required field of
   the plan, written out explicitly per unit, not implicit:
   - `haiku` — mechanical, fully specified: renames, moving files,
     applying one known pattern across N call sites, formatting.
   - `sonnet` — normal implementation work: a new endpoint following
     an existing playbook, a migration, tests for a known behaviour.
   - `opus` — design tradeoffs, cross-layer refactors, debugging
     something nobody has explained yet, anything touching a Gotcha.
   Reasoning depth is not a tool parameter: express it in the
   subagent's prompt ("think hard about X before writing", or
   conversely "this is fully specified, do not redesign it").
4. **Spawn one subagent per unit** via `Agent`, passing that unit's
   `model` explicitly. Use `subagent_type: "Explore"` for read-only
   investigation, `"Plan"` for design-only units, `"general-purpose"`
   for units that write code. Independent units go out in a single
   message so they run in parallel; dependent units wait for their
   predecessor's result.
5. **Each subagent prompt is self-contained** — it does not inherit
   this conversation. State the goal, the files in scope, the
   conventions from this file that apply, what must NOT be touched,
   and what "done" looks like (which command must pass).
6. **Integrate and verify yourself.** Subagent reports are not shown
   to the user and are not proof: re-read the diff, run the checks in
   "Operational notes", and report what actually passed.

Do not delegate when the whole task is one unit anyway, when it is
faster to do than to describe, or when it needs conversation context a
prompt cannot carry.

The same workflow is available as an explicit, project-agnostic
command — `/plan-and-delegate`, from `common/` in this template repo —
for when it should run for certain rather than by default.

---

## Documentation upkeep

- **Keep this file, the README, and other docs in sync with the
  codebase proactively — don't wait to be asked.** A task that changes
  what a doc describes (a command, a layer, an env var, a convention)
  updates that doc in the same task.
- Includes removing stale content, not just adding new — a doc
  describing something gone is misleading and gets fixed on sight,
  even if unrelated to the task at hand.

---

## Operational notes for Claude Code

- Don't modify the ingestion/import flow without re-reading
  `docs/device-protocol.md` and `docs/estimation-pipeline.md` — these
  are the source of truth for data contracts.
- Don't modify native auth, `ota-service/`, or `scripts/deploy-ota.sh`
  without reading `docs/native-apps.md` / `docs/ota-updates.md` first.
- Run `pytest` (from repo root) and `npm run typecheck` (in `frontend/`) before
  considering a task done.
