#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
CLOUDFLARED_BIN="${CLOUDFLARED_BIN:-$HOME/programs/cloudflared/cloudflared}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:$BACKEND_PORT}"

cd "$ROOT_DIR"
exec "$CLOUDFLARED_BIN" tunnel --url "$BACKEND_URL"
