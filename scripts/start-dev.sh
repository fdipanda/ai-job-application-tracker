#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  if [[ -n "${BACKEND_PID}" ]] && kill -0 "${BACKEND_PID}" 2>/dev/null; then
    kill "${BACKEND_PID}" 2>/dev/null || true
  fi

  if [[ -n "${FRONTEND_PID}" ]] && kill -0 "${FRONTEND_PID}" 2>/dev/null; then
    kill "${FRONTEND_PID}" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

if [[ ! -x "${ROOT_DIR}/venv/bin/uvicorn" ]]; then
  echo "Missing backend virtual environment. Expected ${ROOT_DIR}/venv/bin/uvicorn"
  exit 1
fi

if [[ ! -d "${ROOT_DIR}/frontend/node_modules" ]]; then
  echo "Missing frontend dependencies. Run 'cd frontend && npm install' first."
  exit 1
fi

echo "Starting FastAPI backend on http://localhost:8000"
"${ROOT_DIR}/venv/bin/uvicorn" app.main:app --reload --app-dir "${ROOT_DIR}/backend" &
BACKEND_PID=$!

echo "Starting Next.js frontend on http://localhost:3000"
(
  cd "${ROOT_DIR}/frontend"
  npm run dev
) &
FRONTEND_PID=$!

echo
echo "Development environment is starting."
echo "Frontend: http://localhost:3000"
echo "Backend:  http://localhost:8000"
echo "Press Ctrl+C to stop both services."
echo

wait "${BACKEND_PID}" "${FRONTEND_PID}"
