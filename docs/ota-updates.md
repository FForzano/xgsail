# OTA updates (native app)

`ota-service/` is a standalone Node/Express service that serves
self-hosted OTA updates for the Capacitor native app via
[`@capgo/capacitor-updater`](https://github.com/Cap-go/capacitor-updater)
— the **open-source plugin**, not Capgo's paid cloud dashboard/CLI. It has
no dependency on the FastAPI `backend/` or Postgres; it only talks to
MinIO.

## Architecture

```
frontend/dist (JS/HTML/CSS/assets only)
        │  scripts/deploy-ota.sh: zip + checksum + upload
        ▼
MinIO  {SAILFRAMES_BUCKET}/app-updates/
          manifest.json            { version, checksum }
          bundles/{version}.zip

        ▲  reads
        │
ota-service (Node/Express, :8081)
  GET/POST /manifest.json  → compares client version to manifest.json,
                              returns {version, url, checksum} (url is a
                              freshly minted presigned MinIO GET, or {} if
                              the client is already current)
  GET      /bundle/:version → 302 to a presigned MinIO GET for that bundle

        ▲  fetches manifest, then bundle
        │
Native app (@capgo/capacitor-updater, configured in
  frontend/capacitor.config.ts with updateUrl pointing at ota-service)
```

No auth on either endpoint — public, read-only, same trust level as the
existing `firmware/*` anonymous-read prefix in `deploy/minio-init.sh`
(devices already download unauthenticated firmware bundles that way).

> **Verify before shipping**: `@capgo/capacitor-updater`'s self-hosted
> request/response contract has changed across plugin versions. Before
> relying on `ota-service/src/routes/manifest.ts` in production, check the
> live docs at capgo.app/docs/plugins/updater/self-hosted against the
> exact plugin version pinned in `frontend/package.json`, and adjust field
> names there if they've drifted.

## App Store compliance

Apple allows JS/HTML/CSS/asset-only OTA updates for hybrid apps (the same
rule CodePush/Expo updates rely on) but **not** native code, plugins,
permissions, or `capacitor.config.ts` changes. This is enforced entirely
at the deploy-script level:

- `scripts/deploy-ota.sh` only ever zips `frontend/dist` (the Vite build
  output) — it never touches `frontend/android/`, `frontend/ios/`, or
  `frontend/capacitor.config.ts`.
- Any change to native code, plugins, or `capacitor.config.ts` requires a
  full native rebuild + App Store/Play Store submission — it can never
  ship as an OTA update.
- `capacitor.config.ts`'s `CapacitorUpdater.autoUpdate: true` checks for
  updates on launch (not silently mid-session), keeping update behavior
  visible/predictable if App Store review asks about it.

## Deploying a new update

```bash
OTA_API_BASE=https://api.xgsail.com/api \
SAILFRAMES_S3_ENDPOINT=http://localhost:9000 \
MINIO_ROOT_USER=... MINIO_ROOT_PASSWORD=... \
SAILFRAMES_BUCKET=sailframes-fleet-data-prod \
scripts/deploy-ota.sh [VERSION]
```

**Retention**: after each publish, the script prunes MinIO down to the
`OTA_KEEP_VERSIONS` (default 5) most recently uploaded bundles — old
versions are never referenced by `manifest.json` (which only ever points
at the latest) and aren't needed for `@capgo/capacitor-updater`'s
crash-rollback (that keeps a copy of the previous bundle on-device, not on
the server), so pruning aggressively is safe; the retained few are purely
for manual debugging.

`VERSION` defaults to `git describe --tags --always` in `frontend/`. The
script builds the frontend with `VITE_API_BASE` set to the real backend
origin (required — see `docs/native-apps.md`), zips `dist/`, computes a
sha256 checksum, and uploads both the bundle and a refreshed
`manifest.json` to MinIO via `mc`.

## Running `ota-service`

Via `docker compose up` — it's wired automatically (`ota-service` in
`docker-compose.yml`), sharing the same MinIO instance/credentials as the
rest of the stack via the `SAILFRAMES_BUCKET`/`MINIO_ROOT_USER`/
`MINIO_ROOT_PASSWORD`/`SAILFRAMES_S3_ENDPOINT` env vars (see
`ota-service/.env.example`) — only `SAILFRAMES_OTA_PREFIX` (default
`app-updates`) and `OTA_PORT` (default `8081`) are new.

Standalone (outside compose):

```bash
cd ota-service
npm install
cp .env.example .env   # then: set -a && source .env && set +a
npm run dev
```
