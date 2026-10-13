"""
Update checks against GitHub Releases.

Pure Python (no Qt), so it is unit-testable and the web version on the NAS
can reuse it. It knows:

    - how to read the "latest release" answer from GitHub's API and compare
      its version with the app's;
    - which download fits the running copy (the install kind): the Windows
      installer, the macOS zip, the Linux AppImage, or the Linux tarball;
    - whether that copy can replace itself in place (one click) or should
      open the release page instead;
    - how to verify a download (size and SHA-256 from the API), and how to
      hand over to the installer: the Inno Setup command on Windows, or a
      small shell script on Linux and macOS that waits for the app to quit,
      swaps the file, folder, or bundle, and reopens the app.

The network, the window, and the settings live in gui/update_checker.py.
"""

from __future__ import annotations

import hashlib
import os
import shlex
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from urllib.parse import urlsplit

REPO = "Petruchio96/fotofixer"
LATEST_RELEASE_API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE_URL = f"https://github.com/{REPO}/releases"

# The release files, by name. CI uploads exactly these names
# (.github/workflows/build.yml) and the Windows installer script produces the
# first one (packaging/windows_installer.iss); a test ties the three together.
# The checker finds its download by name, so a rename must keep the old
# names for one release (or teach the checker both).
WINDOWS_SETUP_ASSET = "fotofixer-windows-x86_64-setup.exe"
MACOS_ZIP_ASSET = "fotofixer-macos-arm64.zip"
LINUX_TARBALL_ASSET = "fotofixer-linux-x86_64.tar.gz"
LINUX_APPIMAGE_ASSET = "FotoFixer-x86_64.AppImage"
RELEASE_ASSETS = (LINUX_APPIMAGE_ASSET, LINUX_TARBALL_ASSET, WINDOWS_SETUP_ASSET, MACOS_ZIP_ASSET)

# Where the API and the downloads may come from, redirects included. GitHub
# answers a download with a redirect to its file host (as of 2026-10:
# release-assets.githubusercontent.com; objects.githubusercontent.com before).
TRUSTED_HOSTS = frozenset({
    "github.com",
    "api.github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
})

# Set this to a version like 1.0.0 to make the app think it is older than it
# is, so the update path can be tried against the real latest release.
PRETEND_VERSION_ENV = "FOTOFIXER_PRETEND_VERSION"
# Exported by the Docker image (the future web version): no self-update there.
CONTAINER_ENV = "FOTOFIXER_CONTAINER"

# Names inside the downloads (see fotofixer.spec and build.yml).
FOLDER_NAME = "FotoFixer"
BUNDLE_NAME = "FotoFixer.app"
POSIX_EXE_NAME = "FotoFixer"
# Inno Setup's uninstaller, next to the exe of an installed copy.
WINDOWS_UNINSTALLER = "unins000.exe"

Version = tuple[int, int, int]


# --- Versions ----------------------------------------------------------------

def parse_version(text: str | None) -> Version | None:
    """
    "v1.10.0" -> (1, 10, 0). A missing patch (or minor) number counts as 0.
    Anything that isn't one to three plain numbers (a pre-release tag, an
    empty string) is None.
    """
    if not text:
        return None
    text = text.strip()
    if text[:1] in ("v", "V"):
        text = text[1:]
    parts = text.split(".")
    if not 1 <= len(parts) <= 3 or not all(part.isdigit() for part in parts):
        return None
    numbers = [int(part) for part in parts] + [0, 0]
    return (numbers[0], numbers[1], numbers[2])


def format_version(version: Version) -> str:
    return ".".join(str(number) for number in version)


def is_newer(latest: Version, current: Version) -> bool:
    """Numeric: (1, 10, 0) is newer than (1, 9, 2)."""
    return latest > current


def current_version(app_version: str, environ: Mapping[str, str] = os.environ) -> Version:
    """
    The version the checker compares against: the app's, unless the
    pretend-version variable overrides it (for trying the update path).
    """
    pretended = parse_version(environ.get(PRETEND_VERSION_ENV))
    if pretended is not None:
        return pretended
    parsed = parse_version(app_version)
    return parsed if parsed is not None else (0, 0, 0)


# --- The release ---------------------------------------------------------------

@dataclass(frozen=True)
class Asset:
    name: str
    url: str
    size: int
    # The SHA-256 from the API's "digest" ("sha256:<hex>"), lower-case hex,
    # or None when the API didn't give one (then no one-click update).
    sha256: str | None


@dataclass(frozen=True)
class ReleaseInfo:
    version: Version
    tag: str
    title: str
    # The release notes, Markdown.
    notes: str
    page_url: str
    assets: tuple[Asset, ...]

    def asset_named(self, name: str) -> Asset | None:
        for asset in self.assets:
            if asset.name == name:
                return asset
        return None


def _parse_digest(digest: object) -> str | None:
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        return None
    hex_digest = digest[len("sha256:"):].strip().lower()
    if len(hex_digest) != 64 or any(char not in "0123456789abcdef" for char in hex_digest):
        return None
    return hex_digest


def parse_release(data: Mapping[str, object]) -> ReleaseInfo:
    """
    Read GitHub's "latest release" JSON (already decoded). Raises ValueError
    when it isn't a release with a version tag. Missing notes, title, or
    assets are tolerated.
    """
    tag = data.get("tag_name")
    version = parse_version(tag if isinstance(tag, str) else None)
    if version is None:
        raise ValueError(f"Not a release with a version tag: {tag!r}")
    assets = []
    raw_assets = data.get("assets")
    for raw in raw_assets if isinstance(raw_assets, list) else []:
        if not isinstance(raw, Mapping):
            continue
        name = raw.get("name")
        url = raw.get("browser_download_url")
        if not isinstance(name, str) or not isinstance(url, str):
            continue
        size = raw.get("size")
        assets.append(Asset(
            name=name,
            url=url,
            size=size if isinstance(size, int) else 0,
            sha256=_parse_digest(raw.get("digest")),
        ))
    title = data.get("name")
    notes = data.get("body")
    page_url = data.get("html_url")
    return ReleaseInfo(
        version=version,
        tag=tag,
        title=title if isinstance(title, str) and title.strip() else tag,
        notes=notes if isinstance(notes, str) else "",
        page_url=page_url if isinstance(page_url, str) and is_trusted_page_url(page_url) else RELEASES_PAGE_URL,
        assets=tuple(assets),
    )


# --- The running copy ----------------------------------------------------------

class InstallKind(Enum):
    """How this copy of the app was installed, which decides how it updates."""

    WINDOWS_INSTALLED = "windows_installed"    # by Setup: unins000.exe next to the exe
    WINDOWS_PORTABLE = "windows_portable"      # an old zip, unpacked by hand
    MAC_APP = "mac_app"                        # FotoFixer.app
    MAC_TRANSLOCATED = "mac_translocated"      # the .app run from a read-only copy macOS made
    LINUX_APPIMAGE = "linux_appimage"
    LINUX_FOLDER = "linux_folder"              # the tarball's folder
    SOURCE = "source"                          # python app.py
    CONTAINER = "container"                    # the web version in Docker


def detect_install_kind(
    *, frozen: bool, platform: str, executable: Path, environ: Mapping[str, str]
) -> InstallKind:
    """
    Work out the install kind from facts the caller passes in (so tests can
    try every combination): whether this is a PyInstaller build, the
    sys.platform name, the running executable, and the environment.
    """
    if environ.get(CONTAINER_ENV):
        return InstallKind.CONTAINER
    if not frozen:
        return InstallKind.SOURCE
    if platform == "win32":
        if (executable.parent / WINDOWS_UNINSTALLER).exists():
            return InstallKind.WINDOWS_INSTALLED
        return InstallKind.WINDOWS_PORTABLE
    if platform == "darwin":
        if "/AppTranslocation/" in executable.as_posix():
            return InstallKind.MAC_TRANSLOCATED
        return InstallKind.MAC_APP
    if environ.get("APPIMAGE"):
        return InstallKind.LINUX_APPIMAGE
    return InstallKind.LINUX_FOLDER


def install_target(kind: InstallKind, executable: Path, environ: Mapping[str, str]) -> Path | None:
    """
    What an in-place update replaces: the AppImage file, the app's folder,
    the .app bundle, or (Windows) the exe Setup upgrades. None when the
    layout isn't the expected one, or the kind never updates in place.
    """
    if kind == InstallKind.WINDOWS_INSTALLED:
        return executable
    if kind == InstallKind.LINUX_APPIMAGE:
        appimage = environ.get("APPIMAGE")
        return Path(appimage) if appimage else None
    if kind == InstallKind.LINUX_FOLDER:
        # The one-folder build: the exe with its _internal folder beside it.
        folder = executable.parent
        return folder if (folder / "_internal").is_dir() else None
    if kind == InstallKind.MAC_APP:
        for ancestor in executable.parents:
            if ancestor.suffix == ".app":
                return ancestor
        return None
    return None


class UpdateMode(Enum):
    INSTALL = "install"      # one click: download, verify, install, reopen
    DOWNLOAD = "download"    # open the release page in the browser
    NOTICE = "notice"        # say a version exists; nothing to click


@dataclass(frozen=True)
class UpdatePlan:
    mode: UpdateMode
    # Why it isn't INSTALL, for the button's hover hint ("" when it is).
    reason: str = ""


def _parent_is_writable(path: Path) -> bool:
    # Replacing a file, folder, or bundle is a rename in its parent folder.
    return os.access(path.parent, os.W_OK)


def update_plan(
    kind: InstallKind,
    target: Path | None,
    asset: Asset | None,
    *,
    writable: Callable[[Path], bool] = _parent_is_writable,
) -> UpdatePlan:
    """
    Whether this copy updates itself, opens the release page, or only
    mentions the new version.
    """
    if kind in (InstallKind.SOURCE, InstallKind.CONTAINER):
        return UpdatePlan(UpdateMode.NOTICE)
    if kind == InstallKind.WINDOWS_PORTABLE:
        return UpdatePlan(UpdateMode.DOWNLOAD, "this copy wasn't installed with Setup; run the new Setup to install it")
    if kind == InstallKind.MAC_TRANSLOCATED:
        return UpdatePlan(UpdateMode.DOWNLOAD, "move the app to Applications first, then it can update itself")
    if asset is None:
        return UpdatePlan(UpdateMode.DOWNLOAD, "this release has no download for this system")
    if asset.sha256 is None or asset.size <= 0:
        return UpdatePlan(UpdateMode.DOWNLOAD, "this release has no checksum to verify a download with")
    if kind == InstallKind.WINDOWS_INSTALLED:
        # Setup installs per user; it needs no write access from here.
        return UpdatePlan(UpdateMode.INSTALL)
    if target is None:
        return UpdatePlan(UpdateMode.DOWNLOAD, "this copy isn't laid out the way the download is")
    if not writable(target):
        return UpdatePlan(UpdateMode.DOWNLOAD, "the app's folder isn't writable")
    return UpdatePlan(UpdateMode.INSTALL)


_ASSET_FOR_KIND = {
    InstallKind.WINDOWS_INSTALLED: WINDOWS_SETUP_ASSET,
    InstallKind.WINDOWS_PORTABLE: WINDOWS_SETUP_ASSET,
    InstallKind.MAC_APP: MACOS_ZIP_ASSET,
    InstallKind.MAC_TRANSLOCATED: MACOS_ZIP_ASSET,
    InstallKind.LINUX_APPIMAGE: LINUX_APPIMAGE_ASSET,
    InstallKind.LINUX_FOLDER: LINUX_TARBALL_ASSET,
}


def pick_asset(release: ReleaseInfo, kind: InstallKind) -> Asset | None:
    """The release file for this install kind, if the release has it."""
    name = _ASSET_FOR_KIND.get(kind)
    return release.asset_named(name) if name else None


# --- Downloads -------------------------------------------------------------------

def is_trusted_download_url(url: str) -> bool:
    """
    Only HTTPS from GitHub's own hosts, with no user name hidden in the
    address (https://github.com@evil.example/ is evil.example).
    """
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.username is not None or parts.password is not None:
        return False
    host = (parts.hostname or "").lower()
    return host in TRUSTED_HOSTS


def is_trusted_page_url(url: str) -> bool:
    """A release page to open in the browser: HTTPS on github.com."""
    parts = urlsplit(url)
    return (
        parts.scheme == "https"
        and parts.username is None
        and (parts.hostname or "").lower() == "github.com"
    )


class DownloadVerifier:
    """
    Checks a download as it arrives: feed every chunk to update(), then
    matches() compares the byte count and SHA-256 with the API's. No
    second pass over an 80 MB file.
    """

    def __init__(self) -> None:
        self._hasher = hashlib.sha256()
        self.received = 0

    def update(self, chunk: bytes) -> None:
        self._hasher.update(chunk)
        self.received += len(chunk)

    def matches(self, size: int, sha256: str | None) -> bool:
        if sha256 is None:
            return False
        return self.received == size and self._hasher.hexdigest() == sha256.lower()


def verify_file(path: Path, size: int, sha256: str | None) -> bool:
    """Check a file on disk the same way (tests, and the web version)."""
    if sha256 is None:
        return False
    try:
        if path.stat().st_size != size:
            return False
        verifier = DownloadVerifier()
        with open(path, "rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                verifier.update(chunk)
    except OSError:
        return False
    return verifier.matches(size, sha256)


def cleanup_download_dir(path: Path) -> None:
    """Remove what an earlier update left behind. Never raises."""
    shutil.rmtree(path, ignore_errors=True)


# --- Handing over to the installer -----------------------------------------------

def windows_installer_command(setup_exe: Path, log_path: Path) -> list[str]:
    """
    Run Setup without questions: it upgrades in place and, because the
    install is silent, reopens the app itself (the [Run] entry with
    skipifnotsilent in packaging/windows_installer.iss). /NORESTART and
    /SUPPRESSMSGBOXES make sure nothing can wait on a prompt.
    """
    return [
        str(setup_exe),
        "/SILENT",
        "/SP-",
        "/NOCANCEL",
        "/NORESTART",
        "/SUPPRESSMSGBOXES",
        "/CLOSEAPPLICATIONS",
        f"/LOG={log_path}",
    ]


_SCRIPT_KINDS = (InstallKind.LINUX_APPIMAGE, InstallKind.LINUX_FOLDER, InstallKind.MAC_APP)


def posix_update_script(
    kind: InstallKind, *, downloaded: Path, target: Path, app_pid: int, log_path: Path
) -> str:
    """
    The /bin/sh script that finishes an update on Linux or macOS after the
    app quits: wait for the app's process to end, swap the file (AppImage),
    folder (tarball), or bundle (.app) for the downloaded one, remove what
    is left over, and reopen the app. Everything it does goes to log_path.

    The app can't replace itself while it runs, and nothing may hold the
    script's process group (see core/process_guard.py), so the GUI starts
    this detached and quits.
    """
    if kind not in _SCRIPT_KINDS:
        raise ValueError(f"No update script for {kind}")
    q = shlex.quote
    # POSIX paths whatever the test machine runs on.
    new = q(downloaded.as_posix())
    old = q(target.as_posix())
    stage = q((target.parent / ".fotofixer-update").as_posix())
    lines = [
        "#!/bin/sh",
        "# Written by FotoFixer to install an update. Safe to delete.",
        "set -u",
        f"exec >>{q(log_path.as_posix())} 2>&1",
        f'echo "== $(date) updating {old} from {new} (waiting for pid {int(app_pid)})"',
        "n=0",
        f"while kill -0 {int(app_pid)} 2>/dev/null; do",
        "  sleep 0.2",
        "  n=$((n + 1))",
        '  if [ "$n" -ge 300 ]; then echo "The app is still running after 60 s; giving up."; exit 1; fi',
        "done",
    ]
    if kind == InstallKind.LINUX_APPIMAGE:
        # Copy into the target's folder first, so the final move is a rename
        # on one filesystem (the old file is replaced in one step).
        lines += [
            f"staged={old}.new",
            f'cp -f {new} "$staged" && chmod +x "$staged" && mv -f "$staged" {old} || '
            '{ echo "Could not replace the AppImage."; rm -f "$staged"; exit 1; }',
            f"rm -f {new}",
            'echo "Installed. Reopening the app."',
            f"nohup {old} >/dev/null 2>&1 </dev/null &",
        ]
    else:
        if kind == InstallKind.LINUX_FOLDER:
            unpack = f'tar -xzf {new} -C "$stage"'
            unpacked = f'"$stage"/{q(FOLDER_NAME)}'
            check = f'test -x {unpacked}/{q(POSIX_EXE_NAME)}'
            relaunch = f"nohup {old}/{q(POSIX_EXE_NAME)} >/dev/null 2>&1 </dev/null &"
        else:
            # ditto, not Python's zipfile: a .app needs its symlinks and
            # execute bits kept.
            unpack = f'ditto -x -k {new} "$stage"'
            unpacked = f'"$stage"/{q(BUNDLE_NAME)}'
            check = f'test -x {unpacked}/Contents/MacOS/{q(POSIX_EXE_NAME)}'
            relaunch = f"open -n {old}"
        lines += [
            f"stage={stage}.$$",
            f"backup={old}.old",
            f'rm -rf "$stage" && mkdir "$stage" && {unpack} && {check} || '
            '{ echo "Could not unpack the update."; rm -rf "$stage"; exit 1; }',
        ]
        if kind == InstallKind.MAC_APP:
            # The app downloaded the zip itself, so there should be no
            # quarantine mark; make sure, or macOS would refuse to open it.
            lines.append(f'xattr -dr com.apple.quarantine {unpacked} 2>/dev/null || true')
        lines += [
            f'mv {old} "$backup" && mv {unpacked} {old} || '
            f'{{ echo "Could not swap in the new version."; mv "$backup" {old} 2>/dev/null; rm -rf "$stage"; exit 1; }}',
            f'rm -rf "$backup" "$stage" {new}',
            'echo "Installed. Reopening the app."',
            relaunch,
        ]
    lines.append("exit 0")
    return "\n".join(lines) + "\n"
