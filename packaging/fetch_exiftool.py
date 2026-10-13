"""
Download ExifTool into tools/<platform>/ so PyInstaller can bundle it.

Usage (from the repository root):
    python packaging/fetch_exiftool.py windows
    python packaging/fetch_exiftool.py macos
    python packaging/fetch_exiftool.py linux

Why this file exists:
    Every build bundles its own ExifTool, so all three run the same version.
    This script downloads a pinned ExifTool version, checks it against the published SHA-256 checksum,
    and unpacks it into the layout fotofixer.spec expects:

        windows -> tools/windows/exiftool.exe
                   tools/windows/exiftool_files/
        macos   -> tools/macos/exiftool
                   tools/macos/lib/
        linux   -> tools/linux/exiftool
                   tools/linux/lib/

    macOS and Linux both use ExifTool's platform-independent Perl
    distribution (the same Image-ExifTool archive), run by the system Perl.

Updating ExifTool:
    Change EXIFTOOL_VERSION and both checksums (macOS and Linux share one). The checksums are listed at
    https://exiftool.org/checksums-<version>.txt
"""

from __future__ import annotations

import hashlib
import io
import shutil
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

EXIFTOOL_VERSION = "13.59"

# Archive name and SHA-256 checksum for each platform.
DOWNLOADS = {
    "windows": (
        f"exiftool-{EXIFTOOL_VERSION}_64.zip",
        "44b512b25af500724ba579d0a53c8fc5851628b692dd5e5d94ae4a15c2cba9ec",
    ),
    "macos": (
        f"Image-ExifTool-{EXIFTOOL_VERSION}.tar.gz",
        "668ea3acececb7235fbd0f4900e72d5f12c9b07e5c778fd36cb1e9b5828fd65a",
    ),
}
# Linux uses the same Perl distribution as macOS.
DOWNLOADS["linux"] = DOWNLOADS["macos"]

# exiftool.org currently hosts its downloads on SourceForge.
DOWNLOAD_URL = "https://sourceforge.net/projects/exiftool/files/{name}/download"

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def download(name: str, expected_sha256: str) -> bytes:
    """
    Download an ExifTool archive and verify its checksum.
    """
    request = urllib.request.Request(
        DOWNLOAD_URL.format(name=name),
        # SourceForge serves an HTML download page to browsers; a command-line
        # user agent gets redirected straight to the file.
        headers={"User-Agent": "Wget/1.21"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read()

    actual_sha256 = hashlib.sha256(data).hexdigest()
    if actual_sha256 != expected_sha256:
        raise SystemExit(
            f"Checksum mismatch for {name}:\n"
            f"  expected {expected_sha256}\n"
            f"  got      {actual_sha256}"
        )

    return data


def safe_relative_path(name: str) -> PurePosixPath:
    """
    Reject archive entries that would write outside the destination folder.
    """
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise SystemExit(f"Unsafe path in archive: {name}")
    return path


def install_windows(data: bytes, destination: Path) -> None:
    """
    Copy exiftool(-k).exe (renamed to exiftool.exe) and exiftool_files/.
    """
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        exe_entries = [
            entry for entry in archive.namelist()
            if PurePosixPath(entry).name == "exiftool(-k).exe"
        ]
        if len(exe_entries) != 1:
            raise SystemExit("Could not find exiftool(-k).exe in the Windows archive.")

        base = PurePosixPath(exe_entries[0]).parent
        files_prefix = base / "exiftool_files"

        destination.mkdir(parents=True, exist_ok=True)
        (destination / "exiftool.exe").write_bytes(archive.read(exe_entries[0]))

        copied = 0
        for entry in archive.infolist():
            path = safe_relative_path(entry.filename)
            if entry.is_dir() or files_prefix not in path.parents:
                continue

            target = destination / path.relative_to(base)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(entry))
            copied += 1

        if copied == 0:
            raise SystemExit("Could not find exiftool_files/ in the Windows archive.")


def install_perl_distribution(data: bytes, destination: Path) -> None:
    """
    Copy the exiftool Perl script and its lib/ folder (macOS and Linux).
    """
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        members = archive.getmembers()
        script_members = [
            member for member in members
            if member.isfile() and len(PurePosixPath(member.name).parts) == 2
            and PurePosixPath(member.name).name == "exiftool"
        ]
        if len(script_members) != 1:
            raise SystemExit("Could not find the exiftool script in the Perl archive.")

        base = PurePosixPath(script_members[0].name).parent
        lib_prefix = base / "lib"

        destination.mkdir(parents=True, exist_ok=True)
        script_target = destination / "exiftool"
        script_target.write_bytes(archive.extractfile(script_members[0]).read())
        script_target.chmod(0o755)

        copied = 0
        for member in members:
            path = safe_relative_path(member.name)
            if not member.isfile() or lib_prefix not in path.parents:
                continue

            target = destination / path.relative_to(base)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.extractfile(member).read())
            copied += 1

        if copied == 0:
            raise SystemExit("Could not find lib/ in the Perl archive.")


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in DOWNLOADS:
        print(__doc__)
        return 2

    platform_name = argv[1]
    name, expected_sha256 = DOWNLOADS[platform_name]
    destination = PROJECT_ROOT / "tools" / platform_name

    print(f"Downloading {name}...")
    data = download(name, expected_sha256)

    # Remove a previous download so old files never mix with new ones.
    for old_item in ("exiftool.exe", "exiftool_files", "exiftool", "lib"):
        old_path = destination / old_item
        if old_path.is_dir():
            shutil.rmtree(old_path)
        elif old_path.exists():
            old_path.unlink()

    if platform_name == "windows":
        install_windows(data, destination)
    else:
        install_perl_distribution(data, destination)

    print(f"Installed ExifTool {EXIFTOOL_VERSION} into {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
