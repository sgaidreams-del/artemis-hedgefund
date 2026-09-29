#!/usr/bin/env bash
# Start the Artemis dashboard: FastAPI backend (:8000) + Vite frontend (:5173).
# Both bind to 127.0.0.1 only. Ctrl-C stops both.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

[[ -f .env && -x .venv/bin/python ]] || { echo "Artemis isn't installed yet — run ./install.sh first."; exit 1; }

.venv/bin/uvicorn dashboard_api.main:app --host 127.0.0.1 --port 8000 &
API_PID=$!
(cd dashboard && exec npm run dev -- --host 127.0.0.1 --port 5173 --strictPort) &
WEB_PID=$!
trap 'kill "$API_PID" "$WEB_PID" 2>/dev/null || true' EXIT INT TERM

echo
echo "  Artemis dashboard → http://localhost:5173   (Ctrl-C to stop)"
echo
wait
