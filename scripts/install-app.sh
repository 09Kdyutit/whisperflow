#!/bin/bash
# Build a Spotlight-launchable WhisperFlow.app that restarts the background
# service (same trusted identity → no permission re-prompt). Falls back to
# run.sh if the launch agent isn't installed. Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

APP="/Applications/WhisperFlow.app"
[ -w /Applications ] || APP="$HOME/Applications/WhisperFlow.app"
mkdir -p "$(dirname "$APP")"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cp "assets/AppIcon.icns" "$APP/Contents/Resources/AppIcon.icns"

cat > "$APP/Contents/MacOS/WhisperFlow" <<EOF
#!/bin/bash
UID_N="\$(id -u)"
if launchctl print "gui/\${UID_N}/com.whisperflow.agent" >/dev/null 2>&1; then
  exec launchctl kickstart -k "gui/\${UID_N}/com.whisperflow.agent"
else
  exec "$ROOT/run.sh"
fi
EOF
chmod +x "$APP/Contents/MacOS/WhisperFlow"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>WhisperFlow</string>
  <key>CFBundleDisplayName</key><string>WhisperFlow</string>
  <key>CFBundleIdentifier</key><string>com.whisperflow.launcher</string>
  <key>CFBundleVersion</key><string>1.0.0</string>
  <key>CFBundleShortVersionString</key><string>1.0.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>WhisperFlow</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>LSUIElement</key><true/>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
</dict>
</plist>
PLIST

# Refresh icon + Spotlight registration.
touch "$APP"
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
[ -x "$LSREGISTER" ] && "$LSREGISTER" -f "$APP" || true
/usr/bin/mdimport "$APP" 2>/dev/null || true

echo "Installed $APP"
