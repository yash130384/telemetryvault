#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check / activate virtual environment
if [ ! -d ".venv" ]; then
    echo "[TelemetryVault] Creating virtual environment .venv..."
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -r requirements.txt
fi

source .venv/bin/activate

# Default port configuration
HTTP_PORT="${HTTP_PORT:-8000}"
HTTP_HOST="${HTTP_HOST:-0.0.0.0}"
UDP_PORT="${UDP_PORT:-20000}"

echo "========================================================="
echo "  🏁 TelemetryVault - ACC Race Telemetry Engine"
echo "  Web UI:       http://localhost:${HTTP_PORT}"
echo "  UDP Listener: 0.0.0.0:${UDP_PORT}"
echo "========================================================="

exec uvicorn server.main:app --host "$HTTP_HOST" --port "$HTTP_PORT"
