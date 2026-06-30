#!/bin/sh
# One-shot MinIO bootstrap for the SailFrames self-hosted stack.
# Creates the bucket, applies anonymous access policies mirroring the
# production S3 bucket, and registers the ObjectCreated -> webhook event
# that drives CSV processing. Safe to re-run (idempotent).
set -eu

BUCKET="${SAILFRAMES_BUCKET:-sailframes-fleet-data-prod}"

echo "[init] waiting for MinIO and setting alias..."
mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"

echo "[init] creating bucket $BUCKET..."
mc mb --ignore-existing "local/$BUCKET"

# Anonymous access policy — mirrors the production S3 bucket policy:
#   - anonymous PUT to raw/*       (firmware uploads, no auth)
#   - anonymous GET to config/*    (firmware reads config/{boat}/latest.json)
#   - anonymous GET to firmware/*  (OTA manifest + binaries)
# _health.json / _sd_health.json / _boot.log are served via the API proxy,
# so they need no public policy here.
echo "[init] applying anonymous bucket policy..."
cat > /tmp/policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "FleetDirectHTTPUpload",
      "Effect": "Allow",
      "Principal": {"AWS": ["*"]},
      "Action": ["s3:PutObject"],
      "Resource": ["arn:aws:s3:::$BUCKET/raw/*"]
    },
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

# Register the bucket-notification event. The webhook target (arn SF) is
# configured on the minio service via MINIO_NOTIFY_WEBHOOK_*_SF env, so it
# is already online; we only bind it to ObjectCreated on raw/*.csv.
echo "[init] registering ObjectCreated webhook on raw/*.csv..."
mc event add "local/$BUCKET" arn:minio:sqs::SF:webhook \
    --event put --prefix raw/ --suffix .csv 2>/dev/null \
    || echo "[init] event already registered, skipping"

echo "[init] done."
