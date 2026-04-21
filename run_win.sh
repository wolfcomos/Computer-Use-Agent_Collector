#!/usr/bin/env bash
# CUA Collector V2 — Windows launcher for Git Bash/MSYS/Cygwin
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -x "$SCRIPT_DIR/.venv/Scripts/python.exe" ]]; then
    PYTHON=("$SCRIPT_DIR/.venv/Scripts/python.exe")
elif [[ -x "$SCRIPT_DIR/.venv/bin/python3" ]]; then
    PYTHON=("$SCRIPT_DIR/.venv/bin/python3")
elif command -v python >/dev/null 2>&1; then
    PYTHON=("$(command -v python)")
elif command -v py >/dev/null 2>&1; then
    PYTHON=("$(command -v py)" "-3")
elif command -v python3 >/dev/null 2>&1; then
    PYTHON=("$(command -v python3)")
else
    echo "❌ Python not found. Create a venv first: python -m venv .venv && .venv\\Scripts\\python.exe -m pip install -r requirements.txt"
    exit 1
fi

case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) ;;
    *)
        echo "⚠️  run_win.sh is intended for Windows via Git Bash/MSYS/Cygwin."
        ;;
esac

export CUA_CAPTURE_BACKEND=python
export CUA_SESSION_TYPE=windows

exec "${PYTHON[@]}" "$SCRIPT_DIR/collector.py" "$@"
