# SailFrames self-hosted stack (Docker + MinIO)

Run the SailFrames web dashboard **and** the data-ingest pipeline without
AWS. Storage is provided by [MinIO](https://min.io) (S3-compatible), so the
existing boto3 code paths stay live — only the endpoint changes.

```
firmware / curl  ──PUT raw/{boat}/{date}/*.csv──►  MinIO (S3 API, :9000)
                                                      │ bucket notification
                                                      ▼
browser ──GET / , /api/... ──►  FastAPI (api, :8000)  POST /hooks/minio
                                  serves dashboard       └► process CSV → JSON
```

## What's in scope

- Web dashboard (race replay, fleet, battery, sessions) served by uvicorn.
- Read/write API (sessions, races, data, analysis, boats, NOAA buoys).
- Upload ingest: MinIO notifies the API on each new CSV, which downsamples
  it to JSON exactly like the AWS `process_upload` Lambda.

**Out of scope (v1):** AI coach/chat (Anthropic) and Google OAuth — those
pages degrade gracefully. Video transcode (MediaConvert) is also AWS-only.

## Bring it up

```bash
cp .env.example .env          # then edit the self-hosted section
docker compose up -d --build
```

- Dashboard: <http://localhost:8000>
- MinIO console: <http://localhost:9001> (login = `MINIO_ROOT_USER` / `…PASSWORD`)

The `minio-init` container runs once to create the bucket, apply the
anonymous-access policy (PUT `raw/*`, GET `config/*` + `firmware/*`), and
register the `ObjectCreated → webhook` event on `raw/*.csv`.

## Test the pipeline without a boat

Simulate a firmware upload — path-style URL, anonymous PUT:

```bash
B=sailframes-fleet-data-prod
curl -X PUT --data-binary @E1_20260629_120000_nav.csv \
  "http://localhost:9000/$B/raw/E1/2026-06-29/E1_20260629_120000_nav.csv"
```

Within a second the webhook fires and `processed/E1/2026-06-29-120000/`
gains `gps.json`, `gps_10hz.json`, `manifest.json`. Confirm:

```bash
curl http://localhost:8000/api/sessions
```

## How it differs from the cloud build (no code forks)

Everything is env-gated, so the **same code** still deploys to AWS:

| Concern | Cloud (AWS) | Self-hosted (this stack) |
|---|---|---|
| S3 client | `boto3.client("s3")` | `SAILFRAMES_S3_ENDPOINT` → MinIO, path-style |
| Ingest trigger | S3 ObjectCreated → Lambda | MinIO notification → `POST /hooks/minio` |
| Download links | S3 presigned URL | `/api/download/{key}` proxy (MinIO stays private) |
| Fleet/battery files | browser reads bucket | `/api/fleet/*` proxy (set by `SAILFRAMES_FLEET_VIA_API`) |
| Admin auth | Cloudflare Access cookie | `SAILFRAMES_ADMIN_BYPASS=1` |
| Frontend config | `web/config.js` (API Gateway URL) | `deploy/config.docker.js` baked into image |

## Pointing real E1 boats at MinIO

The firmware currently hardcodes the S3 host as
`{bucket}.s3.{region}.amazonaws.com` (virtual-host style) and does not parse
`s3_bucket`/`s3_region` from `config.txt`. To upload to MinIO it needs a
firmware change adding an `s3_host` config field and switching to **path-style**
URLs (`http://{s3_host}/{bucket}/raw/...`). MinIO does not serve virtual-host
buckets without DNS wildcard config. This is tracked separately from the
compose stack — until then, use the `curl` simulation above.

## Notes / gotchas

- numpy/pandas need the Debian `python:3.12-slim` base (precompiled wheels).
  Do not switch to alpine/musl — pip would compile them from source.
- The MinIO event filter is `--suffix .csv` on `raw/`, and the webhook also
  re-checks `raw/…*.csv`, so the `_sd_health.json` the pipeline writes back
  into `raw/` cannot trigger a processing loop.
- `.env` is gitignored — never commit real secrets.
