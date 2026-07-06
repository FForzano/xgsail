#!/bin/sh
# One-shot MinIO bootstrap for the SailFrames self-hosted stack.
# Creates the bucket, applies the anonymous read policy for firmware/config
# (OTA), the CORS policy for direct browser<->MinIO presigned URLs, and
# registers the ObjectCreated -> webhook event that drives CSV processing.
# Safe to re-run (idempotent).
#
# Note: there is NO anonymous PUT policy anymore. Devices upload through the
# claim + DeviceKey protocol (docs/device-protocol.md): they PUT to presigned
# (or HMAC-signed proxy) URLs minted by POST /api/devices/me/session-uploads.
set -eu

BUCKET="${SAILFRAMES_BUCKET:-sailframes-fleet-data-prod}"
PUBLIC_ORIGIN="${SAILFRAMES_PUBLIC_ORIGIN:-http://localhost:8080}"

echo "[init] waiting for MinIO and setting alias..."
mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"

echo "[init] creating bucket $BUCKET..."
mc mb --ignore-existing "local/$BUCKET"

# Anonymous access policy — read-only, OTA surface only:
#   - anonymous GET to config/*    (firmware reads config/{boat}/latest.json)
#   - anonymous GET to firmware/*  (OTA manifest + binaries)
echo "[init] applying anonymous bucket policy..."
cat > /tmp/policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublicReadCloudConfig",
      "Effect": "Allow",
      "Principal": {"AWS": ["*"]},
      "Action": ["s3:GetObject"],
      "Resource": [
        "arn:aws:s3:::$BUCKET/config/*",
        "arn:aws:s3:::$BUCKET/firmware/*"
      ]
    }
  ]
}
EOF
mc anonymous set-json /tmp/policy.json "local/$BUCKET"

# CORS for direct browser<->MinIO presigned URLs (object_store.py
# SAILFRAMES_S3_PUBLIC_ENDPOINT): the frontend origin is cross-origin from
# MinIO's own host:port, so the presigned PUT/GET need CORS to not be blocked.
# Bucket-level CORS (`mc cors set`) isn't implemented server-side on this
# MinIO edition (always errors "not implemented") — use the server-wide `api`
# config subsystem instead, which IS honoured (and already defaults to `*`
# out of the box; we just scope it to the real origin). Needs a restart.
echo "[init] applying server-wide CORS for origin $PUBLIC_ORIGIN..."
mc admin config set local api cors_allow_origin="$PUBLIC_ORIGIN"
mc admin service restart local --wait >/dev/null 2>&1 || true

# Register the bucket-notification event. The webhook target (arn SF) is
# configured on the minio service via MINIO_NOTIFY_WEBHOOK_*_SF env, so it
# is already online; we only bind it to ObjectCreated on raw/*.csv (device
# bundles land under raw/uploads/{session_upload_id}/).
echo "[init] registering ObjectCreated webhook on raw/*.csv..."
mc event add "local/$BUCKET" arn:minio:sqs::SF:webhook \
    --event put --prefix raw/ --suffix .csv 2>/dev/null \
    || echo "[init] event already registered, skipping"

echo "[init] done."
