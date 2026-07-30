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
cd frontend && npm test   # frontend

# DB migrations (Alembic)
cd backend && alembic revision --autogenerate -m "description"
cd backend && alembic upgrade head
cd backend && alembic downgrade -1

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
geo, gpx, wind estimation, import processing, maneuver reconciliation).

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
   access, no centralized permission check.

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
│   ├── services/                # Business logic: course, geo, gpx, wind, import, maneuvers
│   ├── repositories/           # Data-access layer (base.py + sql/ implementation)
│   ├── auth/                   # Passwords, tokens (cookie + Bearer), permissions, RBAC seed
│   ├── db/                     # SQLAlchemy models + base
│   ├── storage/                # Object-store abstraction (S3/MinIO)
│   ├── schemas/                # Pydantic request/response DTOs
│   ├── alembic/                # DB migrations
│   ├── legal.py                # Legal-doc version tracking (copy lives in frontend)
│   ├── onboarding.py           # Guided-tour ID tracking (copy lives in frontend)
│   └── support.py              # Support-prompt cadence (copy lives in frontend)
├── frontend/                   # Vite + React + TS SPA, wrapped via Capacitor
│   ├── src/                    # pages/, components/, hooks/, styles/ (see below)
│   └── ios/App/XGSailWatch     # Native watchOS companion (hand-added Xcode target)
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
`integrations`, `activities`, `sessions`, `polars`, `regattas`,
`racedays`, `races`, `device_api`, `imports`, `ingest`, `uploads`,
`download`, `wind`, `system`, `video`.

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
backend, same-origin), plus the `process_upload`/`video`/`train_maneuver`
workers invoked by the backend on MinIO upload events. `ota-service`
(Express, :8081) is not part of this base stack — bring it up
separately if serving native-app OTA updates. See `deploy/README.md`
for the full request-flow diagram and how the self-hosted (MinIO) path
differs from the AWS (S3/Lambda) path — same code, env-gated.

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
  Station selection/aggregation and the estimation algorithms that turn
  raw observations into a usable wind signal are documented in
  `docs/estimation-pipeline.md`; the underlying fusion/calibration math
  lives in `libs/xgsail_windfusion`, shared with `workers/process_upload`.

---

## Gotchas

- **The native watchOS app doesn't rebuild from the React frontend.**
  It's a hand-added Xcode target at `frontend/ios/App/XGSailWatch`,
  maintained separately — editing `frontend/src` has no effect on it.
- **Devices have no separate upload path in the router layer.** All
  device data flows through the same presigned-upload + webhook
  pipeline as manual imports; don't add a device-specific endpoint,
  extend the claim + device-key flow in `docs/device-protocol.md` instead.
- **Native auth is Bearer, not cookie.** Adding an endpoint that reads
  auth state directly from the request cookie (instead of going
  through `current_user()`) silently breaks it for the native apps —
  see "Native apps" above.
- **`ota-service/` is a separate deployable with its own env vars and
  no backend/DB dependency.** It reuses the backend's MinIO credential
  var names by convention (see "Environment variables"), but running
  `docker compose up` alone does not start it — a missing OTA update
  is not a backend bug.
- **Repo-root `pyproject.toml` only configures pytest.** It is not a
  package manifest for the backend, a worker, or `libs/
  xgsail_windfusion` — each of those has its own build setup; don't
  add dependencies to the root file expecting them to reach any
  deployable.

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

---

## Planning workflow

- **Plan before executing, except for small/obvious changes** — a
  short plan (what changes, in what order, why) for anything
  multi-step, multi-file, or ambiguous; skip it for a one-line fix.
- **Size each plan step to the reasoning depth it needs** (a mechanical
  step vs. a design tradeoff differ a lot), not uniformly to the
  hardest part.

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
- Run `pytest` (from repo root) and `npm test` (in `frontend/`) before
  considering a task done.
