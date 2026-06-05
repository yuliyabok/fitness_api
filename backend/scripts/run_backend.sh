#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
UVICORN_BIN="${UVICORN_BIN:-$ROOT_DIR/.venv/bin/uvicorn}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

LAN_IP="${LAN_IP:-}"
if [ -z "$LAN_IP" ]; then
    LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
fi
if [ -z "$LAN_IP" ] && command -v ip >/dev/null 2>&1; then
    LAN_IP="$(ip route get 1.1.1.1 2>/dev/null | awk '{for (i = 1; i <= NF; i++) if ($i == "src") {print $(i + 1); exit}}')"
fi

printf 'Backend bind: http://%s:%s\n' "$HOST" "$PORT"
if [ -n "$LAN_IP" ]; then
    printf 'Wi-Fi/LAN URL: http://%s:%s\n' "$LAN_IP" "$PORT"
    printf 'Health-check:  http://%s:%s/api/health\n' "$LAN_IP" "$PORT"
fi

cd "$ROOT_DIR"
exec "$UVICORN_BIN" app.main:app --host "$HOST" --port "$PORT" --reload
