# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys
import tomllib


project_root = Path(SPECPATH)
# Windows gets the multi-size .ico (made by packaging/make_windows_icon.py):
# the exe, the taskbar, and the installer's shortcuts then have real 16, 32,
# and 48 px images. Elsewhere PyInstaller converts the PNG itself.
if sys.platform == "win32":
    app_icon = str(project_root / "assets" / "app_icon.ico")
else:
    app_icon = str(project_root / "assets" / "app_icon_128.png")

# pyproject.toml is the single source of truth for the app version.
with open(project_root / "pyproject.toml", "rb") as pyproject_file:
    app_version = tomllib.load(pyproject_file)["project"]["version"]


def existing_datas():
    datas = [
        (str(project_root / "assets"), "assets"),
    ]

    # Linux uses the same pinned Perl distribution as macOS (downloaded by
    # packaging/fetch_exiftool.py linux), run by the system Perl.
    linux_exiftool = project_root / "tools" / "linux" / "exiftool"
    linux_exiftool_lib = project_root / "tools" / "linux" / "lib"
    if sys.platform.startswith("linux"):
        if not linux_exiftool.exists():
            raise SystemExit(
                "Missing tools/linux/exiftool. Run: python packaging/fetch_exiftool.py linux"
            )
        datas.append((str(linux_exiftool), "tools/linux"))
        datas.append((str(linux_exiftool_lib), "tools/linux/lib"))

    windows_exiftool = project_root / "tools" / "windows" / "exiftool.exe"
    if windows_exiftool.exists():
        datas.append((str(windows_exiftool), "tools/windows"))

    # Current Windows ExifTool releases need their exiftool_files folder (Perl runtime)
    # next to exiftool.exe, so bundle it alongside the executable.
    windows_exiftool_files = project_root / "tools" / "windows" / "exiftool_files"
    if windows_exiftool_files.exists():
        datas.append((str(windows_exiftool_files), "tools/windows/exiftool_files"))

    # macOS uses ExifTool's platform-independent Perl distribution: the
    # exiftool script plus its lib folder, run by the system Perl.
    macos_exiftool = project_root / "tools" / "macos" / "exiftool"
    macos_exiftool_lib = project_root / "tools" / "macos" / "lib"
    if macos_exiftool.exists():
        datas.append((str(macos_exiftool), "tools/macos"))
    if macos_exiftool_lib.exists():
        datas.append((str(macos_exiftool_lib), "tools/macos/lib"))

    return datas


a = Analysis(
    ["app.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=existing_datas(),
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FotoFixer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # The .ico on Windows; PyInstaller converts the PNG to .icns with Pillow on
    # macOS; Linux ignores it (the AppImage sets its own icon).
    icon=app_icon,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="FotoFixer",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="FotoFixer.app",
        icon=app_icon,
        bundle_identifier="io.github.petruchio96.photogpseditor",
        version=app_version,
        info_plist={
            "CFBundleDisplayName": "FotoFixer",
            "CFBundleShortVersionString": app_version,
            "NSHighResolutionCapable": True,
        },
    )
