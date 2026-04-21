#!/usr/bin/env bash
# CUA Collector V2 — Linux Xorg/X11 launcher
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
    Linux*) ;;
    *)
        echo "⚠️  run_x11.sh is intended for Linux Xorg/X11."
        ;;
esac

export CUA_CAPTURE_BACKEND=python
export CUA_SESSION_TYPE=x11
export XDG_SESSION_TYPE=x11
export GDK_BACKEND="${GDK_BACKEND:-x11}"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"

exec "${PYTHON[@]}" "$SCRIPT_DIR/collector.py" "$@"
