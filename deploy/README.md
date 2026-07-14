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

## Production deploy (VM + Docker Hub + Cloudflare Tunnel)

`deploy/docker-compose.prod.yml` runs the same stack pulling prebuilt
images from Docker Hub (`fforzano99/xgsail`, pushed by
`.github/workflows/docker-publish.yml` on every push to `main`) instead of
building locally, plus `watchtower` and `cloudflared`:

```bash
cp .env.example .env   # fill in real production secrets, incl.
                        # CLOUDFLARE_TUNNEL_TOKEN and SAILFRAMES_S3_PUBLIC_ENDPOINT
docker compose -f deploy/docker-compose.prod.yml --env-file .env up -d
```

Once that's up, deploys are hands-off: pushing to `main` publishes new
`*-latest` images, and `watchtower` polls Docker Hub every 5 minutes and
redeploys the changed containers on its own — no SSH/manual pull needed.
`cloudflared` opens an outbound tunnel with TLS terminated at Cloudflare's
edge, so the VM needs no inbound ports open. Old image tags are pruned
weekly by `.github/workflows/docker-cleanup.yml`
(`scripts/dockerhub-prune-tags.sh`), keeping the newest 10 per service.

The tunnel token is created once in the Cloudflare Zero Trust dashboard
(Networks > Tunnels), and both public hostnames are routed there — not in
this repo, since a token-based tunnel's routing lives in the dashboard:

| Public hostname | Origin service |
|---|---|
| `xgsail.com` | `http://frontend:80` |
| `minio.xgsail.com` | `http://minio:9000` |
| `api.xgsail.com` | `http://backend:8000` |
| `ssh.xgsail.com` (type **SSH**, not HTTP) | `host.docker.internal:22` |

`minio.xgsail.com` is what browsers use for presigned upload/download URLs
(`SAILFRAMES_S3_PUBLIC_ENDPOINT` in `.env`) — safe to expose publicly since
presigned URLs are self-authenticating, same as real S3.

`api.xgsail.com` gives native apps (mobile/desktop) a stable base URL that
hits the backend directly — bypassing the frontend's nginx proxy (and its
10 MB `client_max_body_size` cap on `/api/`, see `frontend/nginx.conf`).
The web SPA keeps using its same-origin `/api` (via `frontend`), so this
hostname is additive, not a replacement. If a browser-based client (not
just native apps) ever calls `api.xgsail.com` directly, add its origin to
`SAILFRAMES_CORS_ORIGINS` (CSV, see `backend/main.py`) — native HTTP
clients aren't subject to CORS, so no change is needed for them.

### Reaching the VM (private network, no public IP)

The VM sits on a private network, so `ssh.xgsail.com` — routed to the
host's sshd via the `cloudflared` service's `extra_hosts` entry — is the
only way in, not just a hardening option. Put a **Cloudflare Access**
policy on that hostname (Zero Trust > Access > Applications), since it's
now the sole front door: without one, anything reachable from
`ssh.xgsail.com` is reachable by anyone who finds the hostname, protected
only by your SSH key.

Connect from a client with `cloudflared` installed locally:

```bash
ssh -o ProxyCommand='cloudflared access ssh --hostname ssh.xgsail.com' <user>@ssh.xgsail.com
```

(or the equivalent `ProxyCommand` entry in `~/.ssh/config`). Once
connected, ordinary `-L` port forwarding works the same as any SSH
session — e.g. for Postgres, add `-L 5432:localhost:5432` to reach
`postgres:5432` from a local client without exposing it on any tunnel
hostname.

## Notes / gotchas

- numpy/pandas need the Debian `python:3.12-slim` base (precompiled wheels).
  Do not switch to alpine/musl — pip would compile them from source.
- The MinIO event filter is `--suffix .csv` on `raw/`, and the webhook also
  re-checks `raw/…*.csv`, so the `_sd_health.json` the pipeline writes back
  into `raw/` cannot trigger a processing loop.
- `.env` is gitignored — never commit real secrets.
