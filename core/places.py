"""
Folders and places for the Add Photos picker.

Why this file exists:
    The picker shows a folder tree (the user's folders, bookmarks, drives and
    network shares) and, for the chosen folder, only its photos. Finding
    those places and listing folders is plain file-system work, kept here
    without any Qt code so it is easy to test.
"""

from __future__ import annotations

import os
import stat
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

from core.file_types import is_supported_file

# File systems that are network shares (Linux and macOS names).
NETWORK_FILE_SYSTEMS = {
    "cifs",
    "smb3",
    "smbfs",
    "nfs",
    "nfs4",
    "afpfs",
    "webdav",
    "davfs",
    "fuse.sshfs",
    "sshfs",
    "fuse.rclone",
}

# GNOME/Cinnamon put shares opened in the file manager (smb://...) here,
# one folder per share, as ordinary folders.
GVFS_FILE_SYSTEM = "fuse.gvfsd-fuse"

# Mount points that are system plumbing, not places to find photos. The
# last two are macOS's own system volumes (/System/Volumes/Data, Preboot, ...).
_SYSTEM_MOUNT_PREFIXES = (
    "/snap",
    "/boot",
    "/run",
    "/dev",
    "/sys",
    "/proc",
    "/var",
    "/tmp",
    "/System",
    "/private",
)
_SYSTEM_FILE_SYSTEMS = {
    "tmpfs",
    "devtmpfs",
    "squashfs",
    "overlay",
    "efivarfs",
    "proc",
    "sysfs",
    "fuse.portal",
    "autofs",
    "devfs",
}


@dataclass(frozen=True)
class Place:
    """A named folder shown in the picker's tree."""

    name: str
    path: Path


def parse_gtk_bookmarks(text: str) -> list[Place]:
    """
    Read a GTK bookmarks file (~/.config/gtk-3.0/bookmarks), the list the
    Linux file manager shows under Bookmarks.

    Each line is "URI [name]". Only local folders (file://) are kept; other
    URIs (smb://, sftp://) need the file manager to connect first.
    """
    places = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        uri, _, name = line.partition(" ")
        parsed = urlparse(uri)
        if parsed.scheme != "file":
            continue
        path = Path(unquote(parsed.path))
        places.append(Place(name.strip() or path.name or str(path), path))
    return places


def network_share_name(device: str, mount_path: Path) -> str:
    """
    A readable name for a mounted network share.

    "//nas.local/photo" (Windows-style share) -> "photo on nas.local"
    "//matt@nas.local/photo" (macOS adds the user) -> "photo on nas.local"
    "nas.local:/volume1/photo" (NFS) -> "photo on nas.local"
    Anything else falls back to the mount folder's name.
    """
    device = device.strip()
    if device.startswith("//"):
        server, _, share = device[2:].partition("/")
        # Drop a "user@" or "DOMAIN;user@" in front of the server.
        server = server.rpartition("@")[2]
        share = share.strip("/")
        if server and share:
            return f"{share} on {server}"
    if ":/" in device:
        server, _, share_path = device.partition(":")
        share = Path(share_path).name
        if server and share:
            return f"{share} on {server}"
    return mount_path.name or str(mount_path)


def gvfs_share_name(folder_name: str) -> str:
    """
    A readable name for a share in the GVFS folder.

    "smb-share:server=nas.local,share=photo" -> "photo on nas.local"
    """
    _, _, settings = folder_name.partition(":")
    values = dict(
        part.split("=", 1) for part in settings.split(",") if "=" in part
    )
    share = values.get("share")
    server = values.get("server") or values.get("host")
    if share and server:
        return f"{share} on {server}"
    if server:
        return server
    return folder_name


def is_network_file_system(file_system: str) -> bool:
    return file_system.lower() in NETWORK_FILE_SYSTEMS


def is_system_mount(mount_path: str, file_system: str) -> bool:
    """
    True for mounts that hold system files rather than photos (snap
    packages, the boot partition, memory file systems).
    """
    if file_system.lower() in _SYSTEM_FILE_SYSTEMS:
        return True
    if mount_path == "/":
        return False
    return any(
        mount_path == prefix or mount_path.startswith(prefix + "/")
        for prefix in _SYSTEM_MOUNT_PREFIXES
    )


# Windows "hidden" attribute (AppData, desktop.ini). File Explorer hides
# these by default; "system" alone is not hidden (Windows sets it on some
# ordinary folders, for example ones with a custom icon).
_WINDOWS_HIDDEN = getattr(stat, "FILE_ATTRIBUTE_HIDDEN", 0x2)
# macOS "hidden" flag (Finder hides ~/Library this way).
_MAC_HIDDEN = getattr(stat, "UF_HIDDEN", 0x8000)


def is_hidden(entry: os.DirEntry, platform: str = sys.platform) -> bool:
    """
    True for files and folders the system's file manager hides: names
    starting with "." everywhere, plus Windows' hidden attribute and macOS's
    hidden flag.
    """
    if entry.name.startswith("."):
        return True
    try:
        if platform == "win32":
            # Free on Windows: scandir already read the attributes.
            attributes = entry.stat(follow_symlinks=False).st_file_attributes
            return bool(attributes & _WINDOWS_HIDDEN)
        if platform == "darwin":
            return bool(entry.stat(follow_symlinks=False).st_flags & _MAC_HIDDEN)
    except (OSError, AttributeError):
        return False
    return False


def _visible_entries(folder: Path) -> list[os.DirEntry]:
    try:
        with os.scandir(folder) as entries:
            return [entry for entry in entries if not is_hidden(entry)]
    except OSError:
        # Unreadable, missing, or a disconnected share: show nothing.
        return []


def _is_dir(entry: os.DirEntry) -> bool:
    try:
        return entry.is_dir()
    except OSError:
        return False


def _is_file(entry: os.DirEntry) -> bool:
    try:
        return entry.is_file()
    except OSError:
        return False


def list_subfolders(folder: Path) -> list[Path]:
    """
    The folders inside a folder, hidden ones left out (see is_hidden),
    sorted by name ignoring case.
    """
    folders = [Path(entry.path) for entry in _visible_entries(folder) if _is_dir(entry)]
    return sorted(folders, key=lambda path: path.name.casefold())


def has_subfolders(folder: Path) -> bool:
    """
    True if a folder has at least one visible folder inside. Stops at the
    first one, so it stays quick for folders holding many photos.
    """
    try:
        with os.scandir(folder) as entries:
            return any(_is_dir(entry) and not is_hidden(entry) for entry in entries)
    except OSError:
        return False


def list_photos(folder: Path) -> list[Path]:
    """
    The photos the app can open in a folder (not its subfolders), sorted by
    name ignoring case.
    """
    photos = [
        Path(entry.path)
        for entry in _visible_entries(folder)
        if is_supported_file(Path(entry.name)) and _is_file(entry)
    ]
    return sorted(photos, key=lambda path: path.name.casefold())


def _is_real_dir(entry: os.DirEntry) -> bool:
    """
    A folder that is not a link to somewhere else (a symlink, or a junction
    on Windows). Walking into links could loop forever (a link to a parent
    folder) or wander off into another drive.
    """
    try:
        if entry.is_symlink() or getattr(entry, "is_junction", lambda: False)():
            return False
        return entry.is_dir(follow_symlinks=False)
    except OSError:
        return False


def _folder_tree(folder: Path, cancelled: Callable[[], bool] | None) -> Iterator[Path]:
    """
    A folder, then every folder inside it at any depth (hidden and linked
    folders left out), each folder before its subfolders, siblings by name.
    """
    stack = [folder]
    while stack:
        if cancelled is not None and cancelled():
            return
        current = stack.pop()
        yield current
        subfolders = sorted(
            (Path(entry.path) for entry in _visible_entries(current) if _is_real_dir(entry)),
            key=lambda path: path.name.casefold(),
        )
        # Reversed, so the first one by name comes off the stack first.
        stack.extend(reversed(subfolders))


def photos_in_folders(
    folders: list[Path],
    *,
    recursive: bool,
    cancelled: Callable[[], bool] | None = None,
) -> list[Path]:
    """
    The photos in folders chosen in the picker: only those directly inside
    each folder, or also those in every folder inside it when recursive is
    True. Each folder's photos are sorted as in list_photos; a photo found
    twice (a folder chosen along with a folder inside it) is listed once.
    Stops early, returning what it found so far, once cancelled() is True.
    """
    found: list[Path] = []
    seen: set[Path] = set()
    for folder in folders:
        tree = _folder_tree(Path(folder), cancelled) if recursive else [Path(folder)]
        for current in tree:
            if cancelled is not None and cancelled():
                return found
            for photo in list_photos(current):
                if photo not in seen:
                    seen.add(photo)
                    found.append(photo)
    return found


def folder_contents_summary(folder: Path) -> tuple[int, int]:
    """
    How many photos and how many (visible) folders are directly inside a
    folder, for the picker's folder tiles. Does not look into subfolders.
    """
    photos = 0
    subfolders = 0
    for entry in _visible_entries(folder):
        if _is_dir(entry):
            subfolders += 1
        elif is_supported_file(Path(entry.name)) and _is_file(entry):
            photos += 1
    return photos, subfolders
