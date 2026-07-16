# XGSail — Sailing Analytics Platform

## Project Context for Claude Code

This repository is **XGSail**: the software application layer only —
backend API, frontend SPA, ingestion/processing workers, and
self-hosted deployment. It is **not** the hardware/firmware repository.
Firmware, PCB design (KiCad), and embedded-device internals live in the
separate upstream project (SailFrames Core) and are out of scope here.

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
- Self-hosted first: `docker compose up --build` brings up the entire
  stack locally (Postgres + MinIO + backend + frontend + workers), with
  the same code deploying to AWS (S3/Lambda) via env-gated config — no
  code forks between the two targets.
- **Current focus (branch `feature/introduce-users-login-and-roles`):**
  a from-scratch redesign of the data model, API surface, and frontend
  around users/auth/roles/clubs/groups — actively specified in
  `docs/er-project.md`, `docs/api-project.md`, `docs/frontend-project.md`,
  and `docs/device-protocol.md`. Treat those four files as the source of
  truth for where the schema/API/frontend are heading; the existing
  `backend/db/models` and `backend/routers` reflect the current
  in-progress state, not necessarily the final shape.

---

## Code Style Guidelines

Applies across the whole repo (backend, frontend, workers) — not
project-specific:

- **Simple and readable over clever.** Optimize for the next person
  reading the code, not for fewest lines or cleverest trick.
- **Isolate responsibilities.** Each function/module does one thing.
  Router modules stay thin (HTTP concerns only); business logic lives in
  `services`/`repositories`; don't mix request parsing, DB access, and
  response shaping in one function just because they run back-to-back.
- **Reuse before writing.** Before adding a new helper, check if an
  existing function in the codebase (or a well-maintained library
  already in use — e.g. an existing repository method, a `services/`
  helper, a frontend hook) already does it. Prefer extending/
  parameterizing an existing function over writing a near-duplicate.
- **No duplicated logic.** If the same block of logic (even
  slightly-modified copy-paste) appears in two places, extract it into a
  shared function — favor small, composable, modular pieces over
  repeating inline logic. This matters especially for router modules
  (shared HTTP helpers belong in `routers/_common.py`, not copy-pasted
  per router) and for the frontend (shared chart/map/data-fetching logic
  belongs in a hook/util, not duplicated per page).

---

## Repository Structure

```
core/
├── CLAUDE.md              # This file
├── README.md               # Project scope: what XGSail is / isn't
├── docs/
│   ├── er-project.md        # New ER schema (users/roles/clubs/groups/devices/sessions)
│   ├── api-project.md        # API roles/permissions matrix + ingestion endpoints
│   ├── frontend-project.md    # Simplified frontend page structure
│   └── device-protocol.md      # Hardware-agnostic device integration protocol
├── backend/                # FastAPI REST API (API-only, no static mount)
│   ├── main.py               # Composition root: CORS, RBAC startup seed, routers
│   ├── routers/               # One module per resource (see below)
│   ├── services/                # Business logic (course, geo, gpx parsing/processing)
│   ├── repositories/              # Data-access layer (base.py + sql/ implementation)
│   ├── auth/                        # passwords, tokens, permissions, RBAC seed
│   ├── db/                            # SQLAlchemy models + base, Alembic-migrated
│   ├── storage/                        # Object-store abstraction (S3/MinIO)
│   ├── schemas/                          # Pydantic request/response models
│   └── alembic/                            # DB migrations
├── frontend/                # Vite + TypeScript SPA
│   └── src/                   # components, pages, contexts, hooks, services, stores,
│                                 i18n, styles, types, utils
├── workers/                 # Heavy-processing workers — same handler runs on AWS
│   ├── process_upload/        # Lambda (container image) and locally via the Lambda
│   └── video/                  # Runtime Interface Emulator shipped in the base image
├── deploy/                  # Self-hosted stack: Dockerfile.backend, minio-init.sh
├── scripts/                 # One-off/maintenance scripts (migrations, backfills)
└── docker-compose.yml       # One-command local stack (postgres/minio/backend/frontend/workers)
```

### Backend routers (`backend/routers/`)

One module per resource: `auth`, `boats`, `clubs`, `groups`, `devices`,
`sessions`, `data`, `analysis`, `leaderboard`, `races`, `regattas`,
`racedays`, `uploads`, `ingest`, `download`, `video`, `buoys`, `fleet`.
Shared HTTP helpers live in `routers/_common.py` — put anything reused
across routers there, not copy-pasted.

`e1.py` and `fleet.py` are legacy-compatibility routes that keep the
existing physical E1 fleet hardware working (direct-to-storage upload
path, fleet health snapshot) while new ingestion moves toward the
hardware-agnostic contract in `docs/device-protocol.md`. Don't extend
`e1.py`-style patterns for new device types — use the claim + device-key
flow described there instead.

---

## Data Flow

```
[Device or manual import]
  → presigned upload URL (backend/storage) → PUT to S3/MinIO

[Object storage]
  ObjectCreated event → webhook (MinIO: /hooks/minio, or S3 notification)
  → backend invokes workers/process_upload (or workers/video for video
    files) over HTTP — same container image also runs as a Lambda in
    the AWS deployment, via the Lambda Runtime Interface Emulator
  → worker writes processed/normalized data back to storage + updates
    ingestion status in Postgres via the backend

[Frontend]
  SPA (frontend/) → REST API (backend/) → Postgres (metadata) +
  object storage (processed data, referenced by data_ref/raw_ref)
```

This mirrors the ingestion model being formalized in `docs/er-project.md`
(`session_uploads`, `session_streams`) and `docs/api-project.md`
("Caricamento file raw e grandi", "Registrazione device e ingestion
dati") — read those before changing anything upload-related.

---

## Self-Hosted Stack

```bash
cp .env.example .env   # edit secrets — never commit a real .env
docker compose up --build
```

Services (see `docker-compose.yml`): `postgres` (metadata), `minio`
(S3-compatible blob storage, console on :9001), `backend` (FastAPI,
:8000), `frontend` (nginx serving the SPA build + proxying `/api` →
backend, same-origin), plus the `process_upload`/`video` workers invoked
by the backend on MinIO upload events. See `deploy/README.md` for the
full request-flow diagram and how the self-hosted (MinIO) path differs
from the AWS (S3/Lambda) path — same code, env-gated.

---

## Weather Data Integration

- **NOAA NDBC buoys** and **METAR** stations, fetched via
  `backend/noaa_buoys.py` / `backend/routers/buoys.py`.
- The ER redesign in `docs/er-project.md` introduces `wind_stations` +
  `wind_observations` as a local cache of this external data (avoids
  re-fetching on every render, preserves history past whatever window
  the upstream API retains). Station selection/aggregation logic is
  runtime, not persisted as a per-regatta default (open design question,
  deliberately deferred).

---

## Auth & RBAC

Two authorization layers (see `docs/api-project.md`, "Ruoli e permessi
per classe di API", for the full matrix):

1. **Scoped RBAC** (`roles`/`permissions`/`role_permissions`/`user_roles`)
   for institutional roles (`superadmin`, `club_admin`, `race_officer`)
   scoped via `user_roles.scope_club_id`.
2. **Per-resource ownership** (`user_boats.role`, `user_groups.role`) for
   personal/boat-scoped resources — no centralized permission check, the
   relationship itself grants access.

`backend/auth/` implements passwords, JWT tokens, and the RBAC seed run
at startup (`seed_superadmin`, `seed_devices`, `seed_defaults` in
`main.py`).

---

*This file was realigned to reflect XGSail's actual scope (software
application only) — hardware/firmware/PCB content that previously
lived here belongs to the separate upstream SailFrames Core (hardware)
project and is no longer relevant to this repository.*
