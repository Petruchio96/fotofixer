# Packaging Notes

The first release packaging target is a PyInstaller one-folder build. This is
easier to debug than a single-file executable and is the safest starting point
for a PySide6 desktop app.

## Automated Builds (GitHub Actions)

`.github/workflows/build.yml` builds all three platforms on GitHub's servers:

- Every push to any branch runs the tests on Linux, Windows, and macOS and
  builds each app. Open the run on the repository's Actions tab and download
  the builds from its Artifacts section. Each download is the release file
  itself (uploaded with `archive: false`), not a zip around it.
- Pushing a `v*` tag also attaches the builds to that tag's GitHub release,
  creating a draft release if one does not exist.

PyInstaller cannot cross-compile, so this is the easiest way to get Windows and
macOS builds without owning those machines. The manual steps below are still
useful for local testing.

## Linux

Build from the repository root:

```bash
.venv/bin/python -m pip install PyInstaller
.venv/bin/python packaging/fetch_exiftool.py linux
.venv/bin/python -m PyInstaller photo_gps_editor.spec --noconfirm
tar -C dist -czf dist/photo-gps-editor-linux-x86_64.tar.gz 'Photo GPS Editor'
```

The Linux output is:

```text
dist/Photo GPS Editor/
  Photo GPS Editor
  _internal/
dist/photo-gps-editor-linux-x86_64.tar.gz
```

The PyInstaller spec bundles:

- `assets/`
- `tools/linux/exiftool` and `tools/linux/lib/`: the same pinned ExifTool
  version as Windows and macOS (ExifTool's Perl distribution, the same archive
  macOS uses), downloaded and checksum-verified by `fetch_exiftool.py linux`

This gives the app its own ExifTool copy while still relying on the system Perl
runtime, which is present by default on many Linux desktop installs. In source
mode the app also prefers `tools/linux/exiftool` when it exists, and falls back
to the `exiftool` on PATH.

## Windows

Build on Windows rather than cross-compiling from Linux.

1. Install Python 3.12.
2. Create and activate a virtual environment.
3. Install runtime dependencies and PyInstaller.
4. Download ExifTool into `tools/windows/` (checksum-verified):
   `python packaging/fetch_exiftool.py windows`. See `tools/windows/README.md`
   to do this by hand instead.
5. Run:

```powershell
python -m PyInstaller photo_gps_editor.spec --noconfirm
```

The Windows output will be a one-folder app containing `Photo GPS Editor.exe`.
Release zips come from CI (see above); see `WINDOWS_BUILD_STEPS.md` for the
full Windows walkthrough.

### Windows installer

`packaging/windows_installer.iss` is an Inno Setup 6 script that wraps the
one-folder build as `photo-gps-editor-windows-x86_64-setup.exe`. CI builds it
next to the zip, which stays the portable option. The installer:

- installs per user to `%LOCALAPPDATA%\Programs\Photo GPS Editor`, with no
  admin prompt;
- adds a Start menu shortcut, an optional desktop shortcut, and an uninstaller
  (Settings > Apps);
- upgrades in place: running a newer setup replaces the old files (the old
  `_internal` folder is removed first, so nothing stale lingers) and closes a
  running copy first; its fixed `AppId` is what makes it the same program, so
  keep it even if the app is renamed;
- keeps the settings (registry `HKCU\Software\Photo GPS Editor`) and the
  error log (`%LOCALAPPDATA%\Photo GPS Editor`) on uninstall, as they are
  outside the install folder;
- after a silent install (`/SILENT /SP- /NOCANCEL /CLOSEAPPLICATIONS`, which
  the in-app update checker will use) reopens the app.

The exe and the shortcuts use `assets/app_icon.ico`, made from the 128 px PNG
by `packaging/make_windows_icon.py` (run it again if the PNG changes).

To build it locally, after the PyInstaller build:

```powershell
winget install --id JRSoftware.InnoSetup --scope user
$version = python -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])"
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" "/DAppVersion=$version" "/DSourceDir=$PWD\dist\Photo GPS Editor" /Odist packaging\windows_installer.iss
```

The output is `dist\photo-gps-editor-windows-x86_64-setup.exe`. The installer
is not code-signed, so a downloaded copy shows "Windows protected your PC" the
first time: More info > Run anyway. (A copy built on the same PC doesn't.)

## macOS

Build on a Mac (Apple Silicon builds run on Apple Silicon Macs only).

1. Install Python 3.12 and create a virtual environment.
2. Install runtime dependencies and PyInstaller.
3. Download ExifTool into `tools/macos/`: `python packaging/fetch_exiftool.py macos`.
   The app runs it with the Perl that ships with macOS.
4. Run:

```bash
python -m PyInstaller photo_gps_editor.spec --noconfirm
ditto -c -k --keepParent "dist/Photo GPS Editor.app" dist/photo-gps-editor-macos-arm64.zip
```

The app is not signed or notarized, so macOS blocks it the first time it is
opened. Users can allow it under System Settings > Privacy & Security
("Open Anyway").

## AppImage

An AppImage is the closest Linux equivalent to a downloadable Windows app. Build
it after the PyInstaller folder build launches and passes a manual smoke test:

```bash
packaging/build_appimage.sh
```

If `appimagetool` is not installed, download it and pass it explicitly:

```bash
APPIMAGETOOL=/tmp/appimagetool-x86_64.AppImage packaging/build_appimage.sh
```

The AppImage output is:

```text
dist/Photo_GPS_Editor-x86_64.AppImage
```

If a Linux system reports a FUSE error when running the AppImage, install or
enable FUSE for normal AppImage launching. For testing, this fallback avoids
FUSE by extracting first:

```bash
APPIMAGE_EXTRACT_AND_RUN=1 dist/Photo_GPS_Editor-x86_64.AppImage
```
