#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$PROJECT_ROOT/dist"
PYINSTALLER_APP_DIR="$DIST_DIR/FotoFixer"
APPDIR="$PROJECT_ROOT/build/appimage/PhotoGPSEditor.AppDir"
APPIMAGE_OUTPUT="$DIST_DIR/FotoFixer-x86_64.AppImage"
APPIMAGETOOL="${APPIMAGETOOL:-appimagetool}"

if [[ ! -x "$PYINSTALLER_APP_DIR/FotoFixer" ]]; then
    echo "Missing PyInstaller app at: $PYINSTALLER_APP_DIR" >&2
    echo "Build it first with: .venv/bin/python -m PyInstaller fotofixer.spec --noconfirm" >&2
    exit 1
fi

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/128x128/apps"

cp -a "$PYINSTALLER_APP_DIR" "$APPDIR/usr/bin/FotoFixer"
cp "$PROJECT_ROOT/assets/app_icon_128.png" "$APPDIR/fotofixer.png"
cp "$PROJECT_ROOT/assets/app_icon_128.png" "$APPDIR/usr/share/icons/hicolor/128x128/apps/fotofixer.png"

cat > "$APPDIR/AppRun" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

APPDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$APPDIR/usr/bin/FotoFixer/FotoFixer" "$@"
EOF
chmod +x "$APPDIR/AppRun"

# Desktop entries split Exec on spaces, so use a space-free command name.
# AppRun is what actually launches the app inside the AppImage.
cat > "$APPDIR/fotofixer.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=FotoFixer
Comment=View, copy, apply, and clear GPS metadata in photo files
Exec=fotofixer
Icon=fotofixer
Categories=Graphics;Photography;
Terminal=false
EOF
cp "$APPDIR/fotofixer.desktop" "$APPDIR/usr/share/applications/fotofixer.desktop"

"$APPIMAGETOOL" "$APPDIR" "$APPIMAGE_OUTPUT"
chmod +x "$APPIMAGE_OUTPUT"

echo "Built AppImage: $APPIMAGE_OUTPUT"
