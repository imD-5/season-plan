#!/bin/bash
# Build ~/Applications/Season.app from main.swift + icon.swift.
set -euo pipefail
cd "$(dirname "$0")"

APP="$HOME/Applications/Season.app"
# Identifiers. Override with env vars if you want your own reverse-DNS names;
# the label must match the one app/macos/install-server.sh used.
BUNDLE_ID="${SEASON_BUNDLE_ID:-local.season.app}"
SERVER_LABEL="${SEASON_SERVER_LABEL:-local.season.server}"
BUILD="$(mktemp -d)"
trap 'rm -rf "$BUILD"' EXIT

# icon
swift icon.swift "$BUILD/icon.png" >/dev/null
mkdir -p "$BUILD/Season.iconset"
for s in 16 32 128 256 512; do
  sips -z $s $s "$BUILD/icon.png" --out "$BUILD/Season.iconset/icon_${s}x${s}.png" >/dev/null
  d=$((s * 2))
  sips -z $d $d "$BUILD/icon.png" --out "$BUILD/Season.iconset/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$BUILD/Season.iconset" -o "$BUILD/Season.icns"

# binary
swiftc -O -o "$BUILD/Season" main.swift -framework Cocoa -framework WebKit

# bundle
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BUILD/Season" "$APP/Contents/MacOS/Season"
cp "$BUILD/Season.icns" "$APP/Contents/Resources/Season.icns"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Season</string>
  <key>CFBundleDisplayName</key><string>Season</string>
  <key>CFBundleIdentifier</key><string>${BUNDLE_ID}</string>
  <key>SeasonServerLabel</key><string>${SERVER_LABEL}</string>
  <key>CFBundleExecutable</key><string>Season</string>
  <key>CFBundleIconFile</key><string>Season</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSAppTransportSecurity</key>
  <dict><key>NSAllowsLocalNetworking</key><true/></dict>
</dict>
</plist>
PLIST

codesign --force --deep -s - "$APP" >/dev/null 2>&1
touch "$APP"
echo "built $APP"
