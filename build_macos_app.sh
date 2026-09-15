#!/bin/bash
# Build "Fetch by Fisola.app" — a Dock-able launcher for the local server.
# The bundle is a wrapper, not a freeze: it runs this checkout, so updating
# the code updates the app. Rebuild after moving the project.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="Fetch by Fisola"
APP="$ROOT/dist/$APP_NAME.app"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>$APP_NAME</string>
  <key>CFBundleDisplayName</key><string>$APP_NAME</string>
  <key>CFBundleIdentifier</key><string>com.fisola.fetch</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>fetch-launcher</string>
  <key>CFBundleIconFile</key><string>fetch.icns</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
</dict>
</plist>
PLIST

cat > "$APP/Contents/MacOS/fetch-launcher" <<LAUNCHER
#!/bin/bash
PROJECT="$ROOT"
LAUNCHER
cat >> "$APP/Contents/MacOS/fetch-launcher" <<'LAUNCHER'
URL="http://127.0.0.1:8765"
LOG="$HOME/Library/Logs/FetchByFisola.log"
CHROME_APP="/Applications/Google Chrome.app"

say() { echo "[launcher $(date '+%H:%M:%S')] $1" >>"$LOG"; }
fail() { say "FAILED: $1"; osascript -e "display alert \"Fetch by Fisola\" message \"$1\"" >/dev/null 2>&1; exit 1; }

# An interpreter that can actually run the server.
PY=""
for candidate in "$PROJECT/.venv/bin/python" "$(command -v python3 || true)"; do
  [ -n "$candidate" ] && [ -x "$candidate" ] || continue
  if "$candidate" -c "import flask" >/dev/null 2>&1; then PY="$candidate"; break; fi
done
[ -n "$PY" ] || fail "No Python with Flask found. In $PROJECT run: .venv/bin/pip install -r requirements.txt"

open_window() {
  # Plain "open" is the only invocation that reliably loads the page from a
  # bundle launched by Finder. Chrome's --app mode looks nicer but silently
  # opened a window that never loaded anything, which is worse than a tab.
  if [ -d "$CHROME_APP" ]; then
    open -a "$CHROME_APP" "$URL" || open "$URL"
  else
    open "$URL"
  fi
  say "opened $URL in the browser"
}

say "launching, python=$PY"

# Already running, or another copy launching at the same moment? Check the
# port itself: an HTTP probe can fail while the port is very much taken, and
# starting a second server then loses the bind race and kills both launches.
if lsof -nP -iTCP:8765 -sTCP:LISTEN >/dev/null 2>&1; then
  say "port 8765 already serving — opening window only"
  open_window
  exit 0
fi

cd "$PROJECT" || fail "Project folder not found: $PROJECT"
# Start the server detached and let this script exit. A bundle whose
# executable keeps running has no Cocoa event loop, so macOS reports "the
# application is not responding" on the next launch and refuses to open it.
nohup env FETCH_NO_BROWSER=1 "$PY" ui_app.py >>"$LOG" 2>&1 &
SERVER=$!
disown 2>/dev/null || true

READY=0
for _ in $(seq 1 80); do
  if curl -sf -o /dev/null --max-time 3 "$URL/api/ping"; then READY=1; break; fi
  if ! kill -0 $SERVER 2>/dev/null; then
    if lsof -nP -iTCP:8765 -sTCP:LISTEN >/dev/null 2>&1; then
      say "another copy won the port — opening window only"
      open_window; exit 0
    fi
    fail "The server stopped during launch. See $LOG"
  fi
  sleep 0.25
done
if [ "$READY" = "1" ]; then
  say "server ready (pid $SERVER)"
else
  # The probe can fail for reasons that have nothing to do with the server
  # (a restricted network context, for one). The server process is alive, so
  # open the window regardless and let the browser do the retrying.
  say "probe never answered but server pid $SERVER is alive — opening anyway"
fi
open_window
say "window opened; server pid $SERVER left running"
exit 0
LAUNCHER
chmod +x "$APP/Contents/MacOS/fetch-launcher"

# Icon: rendered from build/icon.html when Chrome is available.
if [ -x "$CHROME" ]; then
  WORK="$(mktemp -d)"
  "$CHROME" --headless --disable-gpu --window-size=1024,1024 \
    --default-background-color=00000000 --screenshot="$WORK/icon.png" \
    "file://$ROOT/build/icon.html" >/dev/null 2>&1 || true
  if [ -f "$WORK/icon.png" ]; then
    mkdir -p "$WORK/fetch.iconset"
    for size in 16 32 128 256 512; do
      sips -z $size $size "$WORK/icon.png" --out "$WORK/fetch.iconset/icon_${size}x${size}.png" >/dev/null
      sips -z $((size*2)) $((size*2)) "$WORK/icon.png" \
        --out "$WORK/fetch.iconset/icon_${size}x${size}@2x.png" >/dev/null
    done
    iconutil -c icns "$WORK/fetch.iconset" -o "$APP/Contents/Resources/fetch.icns"
  fi
  rm -rf "$WORK"
else
  echo "note: Chrome not found, building without a custom icon"
fi

# Ad-hoc signature: unsigned bundles are rejected by Gatekeeper and get a new
# identity on every change, so macOS cannot remember permissions granted to it.
codesign --force --deep --sign - "$APP" 2>/dev/null \
  && echo "signed (ad-hoc)" || echo "note: could not sign; Gatekeeper may block it"

touch "$APP"   # nudge Finder to re-read the bundle
echo "Built: $APP"
