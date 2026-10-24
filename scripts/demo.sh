#!/usr/bin/env bash
# Start driftline on a fresh demo project, separate from your real data.
#
#   scripts/demo.sh            # rebuild the demo project and start on http://127.0.0.1:8051
#   scripts/demo.sh --keep     # start without rebuilding (keeps changes you made)
#
# Data lives in ~/.driftline-demo (override with DRIFTLINE_DEMO_DIR); ~/.driftline is never touched.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ROOT}/.venv/bin/python"
[ -x "$PYTHON" ] || PYTHON=python
DEMO_DIR="${DRIFTLINE_DEMO_DIR:-$HOME/.driftline-demo}"
PORT="${DRIFTLINE_PORT:-8051}"

mkdir -p "$DEMO_DIR"
if [ "${1:-}" != "--keep" ] || [ ! -f "$DEMO_DIR/driftline.db" ]; then
    "$PYTHON" "$ROOT/scripts/seed_demo.py" --db "$DEMO_DIR/driftline.db" --force
fi

echo "Demo running on http://127.0.0.1:${PORT}  (Ctrl+C to stop)"
DRIFTLINE_DATA_DIR="$DEMO_DIR" DRIFTLINE_PORT="$PORT" exec "$PYTHON" -m driftline
