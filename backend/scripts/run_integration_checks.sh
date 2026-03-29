#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"

export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://fitness_user:111111@localhost:5432/fitness_db}"
export JWT_SECRET="${JWT_SECRET:-test-secret}"

"$PYTHON_BIN" -m unittest \
  tests.test_contract_compatibility \
  tests.test_api_integration
