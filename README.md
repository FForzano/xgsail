# XGSail

Open sailing analytics platform for race analysis, session replay, and fleet performance — self-hostable, hardware-agnostic, and built for extensibility.

> **XGSail is a fork of SailFrames (originally released as "SailFrames One").**
> It keeps the original's Apache 2.0 license and general purpose — sailing
> session analytics — but is **not a drop-in copy**: the data model, API
> surface, and frontend have been substantially redesigned rather than
> incrementally patched (see "Structural differences from upstream" below).
> The name change reflects that divergence and matches the domain this fork
> is hosted under.

XGSail is a software-first evolution of the original SailFrames project. It focuses on the application layer: user management, authentication, roles, data ingestion, storage, analytics, and web-based workflows for sailors, coaches, and teams.

## What XGSail Is

XGSail is a platform for collecting, storing, and analyzing sailing session data.

It provides:

- Self-hosted deployment (Postgres + MinIO + backend + frontend + workers, one `docker compose up`)
- User authentication and role-based access (clubs, groups, boats, per-resource ownership)
- Database-backed storage for users, boats, clubs, groups, devices, sessions, races and regattas
- Session and race analysis workflows (legs, maneuvers, VMG, polar performance)
- Replay and coaching-oriented review tools (track playback, session photos)
- Hardware-agnostic ingestion through a defined protocol (`docs/device-protocol.md`) — devices claim themselves, then upload data with a per-device key

The goal is to provide an open platform for sailing analytics that can work with dedicated devices, custom integrations, or external data sources, without tying the application to one specific hardware stack.

## What XGSail Is Not

XGSail is **not** the hardware, firmware, or embedded edge stack from the original SailFrames repository.

Those components may integrate with XGSail through the device protocol, but this repository is focused on the software platform and its data contract.

## Project Scope

This repository contains:

- Backend API (`backend/`)
- Frontend application (`frontend/`)
- Database models and Alembic migrations (`backend/db/`)
- Authentication and authorization (`backend/auth/`)
- Storage and ingestion services (`backend/storage/`, `backend/services/`)
- Processing workers (`workers/`)
- Protocol and integration documentation (`docs/`)
- Self-hosted deployment configuration (`deploy/`, `docker-compose.yml`)

## Architecture Direction

XGSail follows a software-platform approach:

1. Devices or external tools produce sailing data.
2. Data is uploaded using a stable ingestion contract.
3. The backend validates, stores, and processes session data.
4. The web application exposes analysis, replay, and management features.

This separation allows the platform to evolve independently from any one hardware implementation.

## Repository Status

XGSail is under active development. The core platform is implemented and usable end to end:

- Users, authentication, and scoped RBAC (superadmin / club admin / race officer) plus per-resource ownership for boats and groups
- Clubs, groups, boats, and devices, with a claim-flow device protocol for ingestion
- Session import and processing (legs, maneuvers, VMG, polar targets), crew tracking, and photo attachments
- Races, regattas, and race-day management, with a leaderboard
- Multi-language frontend (English/Italian) covering all of the above

Ongoing work is on usability and polish of the existing frontend, and rounding out edge cases in the ingestion and analysis pipeline — not on building the core feature set from scratch.

## Relationship to SailFrames Core

XGSail is derived from the broader SailFrames effort, but it intentionally narrows the scope to the software application layer.

Where the original project includes hardware, firmware, edge devices, and AWS-oriented infrastructure, XGSail aims to become a cleaner, self-hostable analytics platform with a stable integration surface for present and future devices.

### Structural differences from upstream

This is a fork in lineage and license, not a rebrand of the same codebase. Concretely:

- **Data model**: the users/auth/roles/clubs/groups/devices/sessions schema was redesigned from scratch (see `docs/er-project.md`), not incrementally extended from the original tables.
- **API surface**: routes, permission model, and ingestion contract were rebuilt around that new schema (`docs/api-project.md`), including a hardware-agnostic device-claim + device-key ingestion flow (`docs/device-protocol.md`) replacing the original's device-specific upload path.
- **Frontend**: rebuilt on a simplified page structure and data-fetching approach (`docs/frontend-project.md`) rather than carried over as-is.
- **Scope boundary**: firmware, PCB design, and embedded-device internals are excluded entirely — they remain in the upstream hardware repository, not mirrored here even partially.

The four docs above are the source of truth for how far the schema/API/frontend have moved from upstream.

## Principles

- **Open** — users can inspect, run, and extend the platform
- **Self-hostable** — no mandatory vendor lock-in
- **Hardware-agnostic** — devices integrate through protocols, not tight coupling
- **Maintainable** — clear boundaries between frontend, backend, storage, and processing
- **Extensible** — new integrations should not require rewriting the core platform

## Quick start (self-host)

Everything runs as containers. From the repo root:

```bash
docker compose up --build
```

Then open **http://localhost:8080**. That's the whole stack:

| Service | Port | What it is |
|---|---|---|
| `frontend` | 8080 | The SPA (nginx). Serves the app and proxies `/api` → backend, so it's all one origin. |
| `backend` | 8000 | The REST API (FastAPI). Also reachable directly for debugging. |
| `postgres` | 5432 | Metadata (users, boats, sessions, races, RBAC). |
| `minio` | 9000 / 9001 | S3-compatible blob storage (sensor data, video, manifests) + console. |
| `process_upload`, `video` | — | Heavy-processing workers (see below). |

No `.env` is required — every value has a dev default. Copy `.env.example` to
`.env` to override secrets for a real deployment.

## Architecture

- **One API.** The FastAPI `backend/` is the only API surface. Metadata lives in
  Postgres; large files (CSV sensor data, video, JSON results) live in S3/MinIO.
- **Auth.** Native email/password (Argon2id) → JWT access cookie + rotating
  refresh token, with double-submit CSRF and per-club RBAC.
- **Workers as microservices.** `workers/process_upload` (GPS tracks + analysis)
  and `workers/video` (MP4 → HLS via ffmpeg) are built on the AWS Lambda base
  image. The **same image** runs on AWS Lambda and locally: in compose it runs
  via the Lambda Runtime Interface Emulator that ships in the base image, and the
  backend invokes it over HTTP on a MinIO upload event (`/hooks/minio`). On AWS
  the identical image sits behind an S3 → Lambda trigger. No code changes to move
  between the two.

Repo layout: `backend/` · `frontend/` · `workers/{process_upload,video}/` ·
`deploy/` (Dockerfile + MinIO init) · `scripts/` (migrations, image build) ·
`docs/device-protocol.md` (device integration contract).

## License

Apache 2.0, consistent with the original upstream project unless stated otherwise.
