#!/bin/bash
# Build "Clip Radar.app" for this Mac's chip, and the files a release carries:
#   dist/Clip Radar.app
#   dist/ClipRadar-macOS-<arm64|x86_64>.dmg   drag-to-Applications disk image
#   dist/ClipRadar-macOS-<arm64|x86_64>.zip   the same app zipped (what the in-app updater downloads)
#
#   scripts/build_app.sh               build, using the Python in .venv (made if missing)
#   scripts/build_app.sh --no-tools    don't bundle FFmpeg, yt-dlp and TwitchDownloaderCLI
#
# Signing: with CODESIGN_IDENTITY set ("Developer ID Application: ...") the app is signed with it and the
# hardened runtime; with NOTARY_PROFILE set too (xcrun notarytool store-credentials), the DMG is notarized
# and stapled. Without them the app is signed ad hoc, which runs on this Mac; on another Mac it opens
# after System Settings › Privacy & Security › Open Anyway.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"

TOOLS=1
for a in "$@"; do
  case "$a" in
    --no-tools) TOOLS=0 ;;
    *) echo "unknown option $a"; exit 2 ;;
  esac
done

ARCH="$(uname -m)"                       # arm64 or x86_64
VER="$(sed -n 's/^VERSION = "\(.*\)"/\1/p' src/version.py)"
APP_NAME="Clip Radar"
NAME="ClipRadar-macOS-$ARCH"
echo
echo "  Building $APP_NAME $VER for $ARCH"
echo "  ---------------------------------"

# ---------- build environment ----------
if [ ! -x .venv/bin/python ]; then
  PY="$(command -v python3.12 || command -v python3)"
  "$PY" -m venv .venv
fi
VPY=.venv/bin/python
echo "  [1/6] Installing build packages..."
"$VPY" -m pip install --upgrade pip --disable-pip-version-check -q
"$VPY" -m pip install -U --disable-pip-version-check -q -r requirements.txt pywebview pyinstaller pillow

# ---------- helper tools (shipped inside the app) ----------
if [ "$TOOLS" = 1 ]; then
  echo "  [2/6] Getting FFmpeg, TwitchDownloaderCLI and yt-dlp..."
  NEED="ytdlp"
  { [ -x tools/ffmpeg ] && [ -x tools/ffprobe ]; } || NEED="$NEED ffmpeg"
  [ -x tools/TwitchDownloaderCLI ] || NEED="$NEED twitchdownloader"
  "$VPY" src/tools_setup.py --dest tools $NEED || echo "  Note: some tools didn't download; the app offers them on first launch."
else
  echo "  [2/6] Skipping the bundled tools."
fi

# ---------- laughter detector ----------
"$VPY" src/audio_events.py --download src/models >/dev/null 2>&1 || mkdir -p src/models
[ -f src/models/audio_events.onnx ] || echo "  Note: the laughter detector didn't download. The app can get it later."

# ---------- React UI (web/ builds into src/web) ----------
WEBDATA=()
if [ -f web/package.json ]; then
  echo "  [3/6] Building the interface..."
  command -v npm >/dev/null || { echo "  The interface needs Node.js 22 (nodejs.org or brew install node@22)."; exit 1; }
  (cd web && npm ci --silent && npm run build --silent)
fi
if [ -f src/web/index.html ]; then WEBDATA=(--add-data "src/web:web"); fi

# ---------- PyInstaller ----------
echo "  [4/6] Packaging (this is the slow part)..."
rm -rf build "dist/ClipRadar.app" "dist/$APP_NAME.app" dist/ClipRadar
# src/stubs/av stands in for PyAV (Clip Radar decodes audio with FFmpeg; see that file)
PYTHONPATH=src/stubs "$VPY" -m PyInstaller --noconfirm --clean --log-level WARN --onedir --windowed \
  --name ClipRadar --icon src/ui/icon.icns --osx-bundle-identifier com.clipradar.app \
  --add-data "src/ui:ui" --add-data "src/models:models" ${WEBDATA[@]+"${WEBDATA[@]}"} \
  --paths src --paths src/stubs --exclude-module hf_xet --exclude-module tkinter \
  --collect-all faster_whisper --collect-all ctranslate2 --collect-all onnxruntime \
  --collect-all webview --collect-submodules yt_dlp --collect-data certifi \
  --hidden-import av --hidden-import routes \
  src/app.py
mv dist/ClipRadar.app "dist/$APP_NAME.app"
APP="dist/$APP_NAME.app"

echo "  [5/6] Finishing the app..."
PLIST="$APP/Contents/Info.plist"
plutil -replace CFBundleName -string "$APP_NAME" "$PLIST"
plutil -replace CFBundleDisplayName -string "$APP_NAME" "$PLIST"
plutil -replace CFBundleShortVersionString -string "$VER" "$PLIST"
plutil -replace CFBundleVersion -string "$VER" "$PLIST"
plutil -replace LSMinimumSystemVersion -string "11.0" "$PLIST"
plutil -replace NSHighResolutionCapable -bool YES "$PLIST"
plutil -replace LSApplicationCategoryType -string "public.app-category.video" "$PLIST"
plutil -replace NSHumanReadableCopyright -string "Clip Radar" "$PLIST"
if [ "$TOOLS" = 1 ] && [ -d tools ]; then
  mkdir -p "$APP/Contents/MacOS/tools"
  for t in ffmpeg ffprobe yt-dlp TwitchDownloaderCLI; do
    if [ -f "tools/$t" ]; then cp "tools/$t" "$APP/Contents/MacOS/tools/"; chmod +x "$APP/Contents/MacOS/tools/$t"; fi
  done
fi
cp docs/user-guide.txt "$APP/Contents/Resources/README.txt"
xattr -cr "$APP"

IDENTITY="${CODESIGN_IDENTITY:--}"
if [ "$IDENTITY" = "-" ]; then
  codesign --force --deep --sign - "$APP"
else
  # inside out: the helper tools, every library and binary, then the app itself
  ENT="$ROOT/scripts/entitlements.plist"
  find "$APP/Contents" -type f \( -perm -u+x -o -name "*.dylib" -o -name "*.so" \) -print0 |
    xargs -0 -n 1 codesign --force --timestamp --options runtime --entitlements "$ENT" --sign "$IDENTITY" 2>/dev/null || true
  codesign --force --timestamp --options runtime --entitlements "$ENT" --sign "$IDENTITY" "$APP"
fi
codesign --verify --deep --strict "$APP"

# ---------- disk image and zip ----------
echo "  [6/6] Making $NAME.dmg and $NAME.zip..."
rm -f "dist/$NAME.dmg" "dist/$NAME.zip"
STAGE="$(mktemp -d)"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -quiet -volname "$APP_NAME" -srcfolder "$STAGE" -ov -format UDZO "dist/$NAME.dmg"
rm -rf "$STAGE"
ditto -c -k --keepParent "$APP" "dist/$NAME.zip"
if [ "$IDENTITY" != "-" ]; then
  codesign --force --timestamp --sign "$IDENTITY" "dist/$NAME.dmg"
  if [ -n "${NOTARY_PROFILE:-}" ]; then
    xcrun notarytool submit "dist/$NAME.dmg" --keychain-profile "$NOTARY_PROFILE" --wait
    xcrun stapler staple "dist/$NAME.dmg"
    xcrun stapler staple "$APP" && rm -f "dist/$NAME.zip" && ditto -c -k --keepParent "$APP" "dist/$NAME.zip"
  fi
fi

echo
echo "  Done!"
echo "    $ROOT/$APP"
echo "    $ROOT/dist/$NAME.dmg"
echo "    $ROOT/dist/$NAME.zip"
echo
