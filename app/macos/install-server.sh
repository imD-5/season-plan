#!/bin/bash
# Run the board server in the background at login (macOS launchd).
#
#   app/macos/install-server.sh            install or update, then start
#   app/macos/install-server.sh --remove   stop and uninstall
#
# The label must match the one app/macos/build.sh puts in Season.app, so the app can
# restart the server if it isn't answering. Override both with SEASON_SERVER_LABEL.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LABEL="${SEASON_SERVER_LABEL:-local.season.server}"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

stop() { launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true; }

if [[ "${1:-}" == "--remove" ]]; then
  stop
  rm -f "$PLIST"
  echo "removed $LABEL"
  exit 0
fi

PYTHON="$ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "No .venv yet. Run \`uv sync\` in $ROOT first." >&2
  exit 1
fi

mkdir -p "$(dirname "$PLIST")"
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>$ROOT/serve.py</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$ROOT</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardErrorPath</key>
  <string>$ROOT/server.log</string>
</dict>
</plist>
PLIST

stop
sleep 0.5
launchctl bootstrap "$DOMAIN" "$PLIST"
echo "running $LABEL from $ROOT"
