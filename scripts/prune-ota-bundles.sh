#!/usr/bin/env bash
# Manually prune old OTA bundles from MinIO. Run this over SSH on the
# deploy server itself — it talks to MinIO over the Docker network
# (localhost:9000 from inside the container), not through the public
# Cloudflare-tunneled endpoint.
#
# Why this exists instead of relying on deploy-ota.sh's own prune step: that
# step goes through the public endpoint (it has to — it runs on a
# GitHub-hosted CI runner with no access to this server's Docker network),
# and `mc rm`/`mc stat` there intermittently fail with SignatureDoesNotMatch
# — traced to mc's `x-amz-checksum-mode` header not surviving the Cloudflare
# tunnel, not a MinIO permissions problem (see deploy-ota.sh's prune comment
# and git history around 2026-08-12). deploy-ota.sh's prune is best-effort
# and just warns on failure, so bundles pile up until pruned by hand — that's
# what this script is for.
#
# Usage (on the server):
#   scripts/prune-ota-bundles.sh [KEEP_VERSIONS]
set -euo pipefail

KEEP_VERSIONS="${1:-${OTA_KEEP_VERSIONS:-5}}"
BUCKET="${SAILFRAMES_BUCKET:-sailframes-fleet-data-prod}"
OTA_PREFIX="${SAILFRAMES_OTA_PREFIX:-app-updates}"

# Found by compose service label rather than a hardcoded container name, so
# this keeps working regardless of which compose project name is in use.
MINIO_CONTAINER="${MINIO_CONTAINER:-$(docker ps --filter "label=com.docker.compose.service=minio" --format '{{.Names}}' | head -1)}"
if [ -z "$MINIO_CONTAINER" ]; then
  echo "Could not find a running MinIO container (looked for a container with" >&2
  echo "label com.docker.compose.service=minio). Set MINIO_CONTAINER=<name> and retry." >&2
  exit 1
fi

echo "==> container: $MINIO_CONTAINER   bucket: $BUCKET/$OTA_PREFIX   keeping newest: $KEEP_VERSIONS"

# Everything below runs *inside* the MinIO container over localhost:9000 —
# port 9000 isn't published to the host in the prod compose file, and
# MINIO_ROOT_USER/PASSWORD are already the container's own env, so nothing
# needs to be passed in from out here.
docker exec -i "$MINIO_CONTAINER" sh -s -- "$BUCKET" "$OTA_PREFIX" "$KEEP_VERSIONS" <<'SCRIPT'
set -eu
BUCKET="$1"
OTA_PREFIX="$2"
KEEP="$3"

mc alias set prune-local http://localhost:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null

# Prefer jq if this image happens to have it; fall back to sed, since the
# minio/minio base image isn't guaranteed to bundle jq (unlike the CI
# runner, where deploy-ota.sh can rely on it).
extract() {
  if command -v jq >/dev/null 2>&1; then
    jq -r '[.lastModified, .key] | @tsv'
  else
    sed -n 's/.*"lastModified":"\([^"]*\)".*"key":"\([^"]*\)".*/\1\t\2/p'
  fi
}

mc ls --json "prune-local/$BUCKET/$OTA_PREFIX/bundles/" \
  | extract \
  | sort -r \
  | tail -n +"$((KEEP + 1))" \
  | cut -f2 \
  | while IFS= read -r old; do
      [ -z "$old" ] && continue
      echo "  removing bundles/$old"
      mc rm "prune-local/$BUCKET/$OTA_PREFIX/bundles/$old"
    done
SCRIPT

echo "==> done"
