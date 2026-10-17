#!/usr/bin/env bash
# Build both images for a linux/amd64 server and save them to ONE archive.
# Use this when the target server cannot reach Docker Hub / PyPI / npm
# (or when you build on an Apple-Silicon Mac and the server is x86_64).
#
#   ./deploy/export-images.sh            -> crossfit-judge-images.tar.gz
#   scp crossfit-judge-images.tar.gz  <project zip>  user@server:~
#   (on the server)  docker load < crossfit-judge-images.tar.gz && docker compose up -d --no-build
set -euo pipefail
cd "$(dirname "$0")/.."
PLATFORM="${PLATFORM:-linux/amd64}"
docker buildx build --platform "$PLATFORM" --load -t crossfit-judge-engine:test ./mini-services/crossfit-judge
docker buildx build --platform "$PLATFORM" --load -t crossfit-judge-web:test .
docker pull --platform "$PLATFORM" caddy:2 >/dev/null 2>&1 || true   # only needed for the HTTPS option
docker save crossfit-judge-engine:test crossfit-judge-web:test | gzip > crossfit-judge-images.tar.gz
ls -lh crossfit-judge-images.tar.gz
