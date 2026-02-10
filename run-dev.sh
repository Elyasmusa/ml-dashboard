#!/usr/bin/env bash
# Dev helper (POSIX): run backend and frontend concurrently in background
# Usage: ./run-dev.sh

set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo "Starting backend..."
( cd backend && python -m pip install -r requirements.txt 2>/dev/null || true; uvicorn main:app --reload --host 0.0.0.0 --port 8000 ) &

echo "Starting frontend..."
( cd frontend && npm install --silent 2>/dev/null || true; npm start ) &

wait
