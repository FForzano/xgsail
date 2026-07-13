#!/usr/bin/env bash
# Build the XGSail container images.
#
# Local dev uses `docker compose up --build`. This script builds/tags the images
# standalone — handy for pushing the worker images to a registry (ECR) so they
# can also be deployed to AWS Lambda as container images (same image, either
# runtime).
#
# Usage:
#   scripts/build-images.sh [TAG]           # build all, tag :TAG (default: latest)
#   REGISTRY=123.dkr.ecr.us-east-1.amazonaws.com scripts/build-images.sh v1  # + prefix
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TAG="${1:-latest}"
PREFIX="${REGISTRY:+${REGISTRY}/}"

build() {
  local name="$1" context="$2" dockerfile="$3"
  echo "==> building ${PREFIX}xgsail-${name}:${TAG}"
  docker build -t "${PREFIX}xgsail-${name}:${TAG}" -f "$dockerfile" "$context"
}

build backend        "$ROOT"                        "$ROOT/deploy/Dockerfile.backend"
build frontend       "$ROOT/frontend"               "$ROOT/frontend/Dockerfile"
# process-upload builds from the repo root so it can reach libs/xgsail_windfusion.
build process-upload "$ROOT"                        "$ROOT/workers/process_upload/Dockerfile"
build video          "$ROOT/workers/video"          "$ROOT/workers/video/Dockerfile"

echo "done."
