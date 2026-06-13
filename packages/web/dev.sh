#!/usr/bin/env bash
# Run all three isitme services locally:
#   - Core Brain   :8077  (packages/brain-core)
#   - Web API/BFF  :5050  (packages/web/api)
#   - Frontend     :4000  (packages/web/frontend)
#
# Prereqs (one-time): see packages/web/README.md
#   - python venv at packages/web/.venv with web-api + brain-core deps installed
#   - frontend deps installed (npm --prefix frontend install)
#   - repo-root .env present (OAUTH_CLIENT_JSON, OPENAI_API_KEY)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

VENV_PY="$HERE/.venv/bin/python"
BRAIN_SRC="$HERE/../brain-core/src"

if [[ ! -x "$VENV_PY" ]]; then
  echo "✗ venv not found at $VENV_PY — see packages/web/README.md (Setup)." >&2
  exit 1
fi

cleanup() {
  echo "\nShutting down…"
  kill 0 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "→ Core Brain  http://127.0.0.1:8077"
PYTHONPATH="$BRAIN_SRC" "$VENV_PY" -m brain_core serve --host 127.0.0.1 --port 8077 &

echo "→ Web API     http://127.0.0.1:5050"
"$VENV_PY" -m web_api --host 127.0.0.1 --port 5050 &

echo "→ Frontend    http://localhost:4000"
npm --prefix frontend run dev &

wait
