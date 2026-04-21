#!/usr/bin/env bash
# CUA Collector V2 — macOS launcher
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -x "$SCRIPT_DIR/.venv/bin/python3" ]]; then
    PYTHON=("$SCRIPT_DIR/.venv/bin/python3")
elif command -v python3 >/dev/null 2>&1; then
    PYTHON=("$(command -v python3)")
elif command -v python >/dev/null 2>&1; then
    PYTHON=("$(command -v python)")
else
    echo "❌ Python not found. Create a venv first: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

case "$(uname -s)" in
    Darwin*) ;;
    *)
        echo "⚠️  run_mac.sh is intended for macOS."
        ;;
esac

export CUA_CAPTURE_BACKEND=python
export CUA_SESSION_TYPE=macos

exec "${PYTHON[@]}" "$SCRIPT_DIR/collector.py" "$@"
