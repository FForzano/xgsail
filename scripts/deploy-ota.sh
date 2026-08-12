#!/usr/bin/env bash
# Publish a new OTA update for the XGSail native app: build the frontend for
# the native target, zip it, upload to MinIO, and refresh the manifest that
# ota-service/ serves.
#
# Only ever ships JS/HTML/CSS/assets (the `frontend/dist` build output) —
# never android/, ios/, or capacitor.config.ts. That split is what keeps
# these updates App-Store-compliant; see docs/ota-updates.md.
#
# Usage:
#   OTA_API_BASE=https://api.xgsail.com/api \
#   VITE_PUBLIC_WEB_ORIGIN=https://xgsail.com \
#   SAILFRAMES_S3_ENDPOINT=http://localhost:9000 \
#   MINIO_ROOT_USER=sailframes MINIO_ROOT_PASSWORD=... \
#   SAILFRAMES_BUCKET=sailframes-fleet-data-prod \
#   scripts/deploy-ota.sh [VERSION]
#
# VERSION defaults to `git describe --tags --always` in frontend/.
#
# Retention: after publishing, prunes MinIO down to the OTA_KEEP_VERSIONS
# (default 5) most recently uploaded bundles. Safe to prune aggressively —
# manifest.json only ever points at the latest version (no incremental
# diffs), and @capgo/capacitor-updater's crash-rollback keeps a copy of the
# previous bundle on-device, not on the server — so old bundles here are
# only useful for manual debugging, never for the update flow itself.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${OTA_API_BASE:?set OTA_API_BASE to the deployed backend origin, e.g. https://api.xgsail.com/api}"
# Same purpose as .env.native.example's VITE_PUBLIC_WEB_ORIGIN (see
# config/platform.ts): the WebView's own origin is the virtual app.xgsail.com,
# so any shareable link (e.g. a regatta join link) built without this env
# resolves to nothing outside the app. Required, not defaulted, so a missing
# value fails the deploy instead of silently shipping broken links to every
# already-installed app on its next OTA update.
: "${VITE_PUBLIC_WEB_ORIGIN:?set VITE_PUBLIC_WEB_ORIGIN to the public web origin, e.g. https://xgsail.com}"
: "${SAILFRAMES_S3_ENDPOINT:?set SAILFRAMES_S3_ENDPOINT, e.g. http://localhost:9000}"
: "${MINIO_ROOT_USER:?set MINIO_ROOT_USER}"
: "${MINIO_ROOT_PASSWORD:?set MINIO_ROOT_PASSWORD}"
BUCKET="${SAILFRAMES_BUCKET:-sailframes-fleet-data-prod}"
OTA_PREFIX="${SAILFRAMES_OTA_PREFIX:-app-updates}"
KEEP_VERSIONS="${OTA_KEEP_VERSIONS:-5}"
VERSION="${1:-$(cd "$ROOT/frontend" && git describe --tags --always)}"

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

echo "==> building frontend (native target, VITE_API_BASE=$OTA_API_BASE) for version $VERSION"
# VITE_APP_MODE=native is required here, not just VITE_API_BASE — without it
# this ships a *web* bundle (marketing landing page, no native-only gating)
# as the native app's OTA update. See config/platform.ts / .env.native.example.
( cd "$ROOT/frontend" && VITE_API_BASE="$OTA_API_BASE" VITE_APP_MODE=native \
  VITE_PUBLIC_WEB_ORIGIN="$VITE_PUBLIC_WEB_ORIGIN" npm run build )

echo "==> zipping dist/"
( cd "$ROOT/frontend/dist" && zip -qr "$WORKDIR/bundle.zip" . )

CHECKSUM="$(shasum -a 256 "$WORKDIR/bundle.zip" | cut -d' ' -f1)"
cat > "$WORKDIR/manifest.json" <<EOF
{"version": "$VERSION", "checksum": "$CHECKSUM"}
EOF

echo "==> uploading bundle + manifest to MinIO (local/$BUCKET/$OTA_PREFIX)"
mc alias set ota-deploy "$SAILFRAMES_S3_ENDPOINT" "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null

# `mc cp` intermittently fails against the public (Cloudflare-tunneled) MinIO
# endpoint with "You must provide the Content-Length HTTP header" — seen on
# both a multi-MB bundle and a tiny manifest.json, so it's a transient
# tunnel/proxy hiccup rather than anything about the payload. Retry a few
# times with backoff instead of failing the whole deploy on a blip.
mc_cp_retry() {
  local src="$1" dst="$2" attempt
  for attempt in 1 2 3 4 5; do
    if mc cp "$src" "$dst"; then
      return 0
    fi
    echo "  mc cp failed (attempt $attempt/5), retrying in $((attempt * 3))s..." >&2
    sleep "$((attempt * 3))"
  done
  return 1
}

mc_cp_retry "$WORKDIR/bundle.zip" "ota-deploy/$BUCKET/$OTA_PREFIX/bundles/$VERSION.zip"
mc_cp_retry "$WORKDIR/manifest.json" "ota-deploy/$BUCKET/$OTA_PREFIX/manifest.json"

echo "==> pruning old bundles (keeping newest $KEEP_VERSIONS)"
# Best-effort: the publish above already succeeded, so a prune failure (seen
# in practice when the public/tunneled S3 endpoint rejects the HEAD a `mc rm`
# does internally, even though GET/PUT through the same endpoint are fine —
# looks like a Cloudflare-side method restriction, not a MinIO permissions
# issue) must not fail the whole deploy over what's just server-side cleanup.
mc ls --json "ota-deploy/$BUCKET/$OTA_PREFIX/bundles/" \
  | jq -r '[.lastModified, .key] | @tsv' \
  | sort -r \
  | tail -n +"$((KEEP_VERSIONS + 1))" \
  | cut -f2 \
  | while IFS= read -r old; do
      [ -z "$old" ] && continue
      echo "  removing bundles/$old"
      mc rm "ota-deploy/$BUCKET/$OTA_PREFIX/bundles/$old" \
        || echo "  warning: failed to remove bundles/$old, leaving it in place"
    done

echo "==> done: version $VERSION published (checksum $CHECKSUM)"
