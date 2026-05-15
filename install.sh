#!/usr/bin/env bash
set -euo pipefail

VENV="$HOME/.local/share/bluefin-changelog-venv"
BIN="$HOME/.local/bin"

python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet rich

mkdir -p "$BIN"
sed "1s|.*|#!$VENV/bin/python3|" \
  "$(dirname "$0")/bluefin-changelog" > "$BIN/bluefin-changelog"
chmod +x "$BIN/bluefin-changelog"

echo "Installed to $BIN/bluefin-changelog"
echo "Make sure $BIN is in your PATH."
