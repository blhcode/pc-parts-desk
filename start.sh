#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ ! -d backend/.venv ]]; then
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install -r backend/requirements.txt
fi

if [[ ! -d frontend/node_modules ]]; then
  (cd frontend && npm install)
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
fi

export PYTHONPATH="$ROOT/backend"
cd "$ROOT"

backend/.venv/bin/uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8765 &
BACK_PID=$!

cleanup() {
  kill "$BACK_PID" 2>/dev/null || true
}
trap cleanup EXIT

cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
