"""
The shared thumbnail cache Linux file managers use (~/.cache/thumbnails).

Why this file exists:
    Nemo, Nautilus, and other Linux file managers save a small thumbnail for
    every photo they show, so a folder opens instantly the next time. Reading
    those (a few kilobytes each, on the local disk) is far faster than reading
    the photos themselves, which can be tens of megabytes each on a network
    share. Thumbnails this app makes are saved there too, so both the app and
    the file manager benefit.

    This follows the freedesktop.org thumbnail specification: one PNG per
    photo, named by the MD5 of the photo's file URI, tagged with the photo's
    URI and modification time so out-of-date thumbnails are ignored.

    Other systems keep their thumbnail caches private, so this does nothing
    on Windows and macOS.
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import zlib
from pathlib import Path

from PySide6.QtCore import QSize, QUrl, Qt
from PySide6.QtGui import QImage, QImageReader

# "normal" thumbnails are up to 128 pixels, "large" up to 256.
_READ_FOLDERS = ("normal", "large")
_WRITE_FOLDER = "normal"
_NORMAL_SIZE = 128


def is_supported() -> bool:
    return sys.platform.startswith(("linux", "freebsd", "openbsd", "netbsd"))


def cache_root() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "thumbnails"


def file_uri(path: Path) -> str:
    """The photo's URI as file managers write it (spaces as %20, and so on)."""
    return QUrl.fromLocalFile(str(path)).toString(QUrl.FullyEncoded)


def thumbnail_name(path: Path) -> str:
    return hashlib.md5(file_uri(path).encode("utf-8")).hexdigest() + ".png"


def _modified_time(path: Path) -> int | None:
    try:
        return int(path.stat().st_mtime)
    except OSError:
        return None


_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def png_text(png: Path) -> dict[str, str]:
    """
    The text labels in a PNG file (tEXt, zTXt, and iTXt chunks), such as
    Thumb::MTime.

    Read directly because Qt splits labels at ":", so it can't read
    "Thumb::MTime". Stops at the image data, where labels are normally done.
    """
    labels: dict[str, str] = {}
    try:
        with open(png, "rb") as handle:
            if handle.read(8) != _PNG_SIGNATURE:
                return labels
            while True:
                header = handle.read(8)
                if len(header) < 8:
                    break
                length = int.from_bytes(header[:4], "big")
                kind = header[4:]
                if kind in (b"IDAT", b"IEND"):
                    break
                data = handle.read(length)
                handle.read(4)  # checksum
                if b"\0" not in data:
                    continue
                key, _, rest = data.partition(b"\0")
                if kind == b"tEXt":
                    value = rest.decode("latin-1")
                elif kind == b"zTXt":
                    # Compressed text (Qt writes long labels this way).
                    value = zlib.decompress(rest[1:]).decode("latin-1")
                elif kind == b"iTXt":
                    # International text: flags, then language and
                    # translated keyword, then the (maybe compressed) text.
                    compressed = rest[:1] == b"\1"
                    text = rest[2:].split(b"\0", 2)[-1]
                    value = (zlib.decompress(text) if compressed else text).decode("utf-8")
                else:
                    continue
                labels[key.decode("latin-1")] = value
    except (OSError, zlib.error, UnicodeDecodeError):
        pass
    return labels


def read(path: Path, size: int, root: Path | None = None) -> QImage | None:
    """
    The cached thumbnail for a photo, scaled to fit size x size, or None if
    there is none or it is out of date (the photo changed since).

    Safe to call on a background thread (QImage only).
    """
    modified = _modified_time(path)
    if modified is None:
        return None
    root = root or cache_root()
    name = thumbnail_name(path)
    for folder in _READ_FOLDERS:
        thumbnail = root / folder / name
        if not thumbnail.is_file():
            continue
        if png_text(thumbnail).get("Thumb::MTime") != str(modified):
            continue
        reader = QImageReader(str(thumbnail))
        source_size = reader.size()
        if source_size.isValid() and (source_size.width() > size or source_size.height() > size):
            scaled = QSize(source_size)
            scaled.scale(size, size, Qt.KeepAspectRatio)
            reader.setScaledSize(scaled)
        image = reader.read()
        if not image.isNull():
            return image
    return None


def write(path: Path, image: QImage, root: Path | None = None) -> None:
    """
    Save a thumbnail for a photo, so the next visit (in this app or the file
    manager) is fast. Failures are ignored: the cache is only a speed-up.

    Safe to call on a background thread (QImage only).
    """
    modified = _modified_time(path)
    if modified is None or image.isNull():
        return
    folder = (root or cache_root()) / _WRITE_FOLDER
    try:
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        thumbnail = QImage(image)
        if thumbnail.width() > _NORMAL_SIZE or thumbnail.height() > _NORMAL_SIZE:
            thumbnail = thumbnail.scaled(
                _NORMAL_SIZE, _NORMAL_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
        thumbnail.setText("Thumb::URI", file_uri(path))
        thumbnail.setText("Thumb::MTime", str(modified))
        thumbnail.setText("Software", "FotoFixer")
        # Write to a temporary file first, then rename, so a file manager
        # reading at the same moment never sees a half-written thumbnail.
        handle, temporary = tempfile.mkstemp(dir=folder, suffix=".png")
        os.close(handle)
        if thumbnail.save(temporary, "PNG"):
            os.chmod(temporary, 0o600)
            os.replace(temporary, folder / thumbnail_name(path))
        else:
            os.remove(temporary)
    except OSError:
        return
