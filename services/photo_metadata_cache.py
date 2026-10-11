"""
In-memory cache for loaded photo metadata.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from core.models import PhotoInfo


type PhotoCacheKey = tuple[Path, int, int]


class PhotoMetadataCache:
    """
    Cache PhotoInfo objects while the underlying file is unchanged.
    """

    def __init__(self) -> None:
        self._items: dict[PhotoCacheKey, PhotoInfo] = {}

    def get(self, path: Path) -> PhotoInfo | None:
        key = self._build_key(path)
        if key is None:
            return None

        info = self._items.get(key)
        return replace(info) if info is not None else None

    def set(self, info: PhotoInfo) -> None:
        key = self._build_key(info.path)
        if key is None:
            return

        self._items[key] = replace(info)

    def forget(self, paths: list[Path]) -> None:
        """
        Drop cached entries for files just written. A date change also sets
        the file's modified time, so after undo a file can come back to an
        earlier time and size that would otherwise find stale metadata.
        """
        targets = set(paths)
        for key in [key for key in self._items if key[0] in targets]:
            del self._items[key]

    def get_many(self, paths: list[Path]) -> dict[Path, PhotoInfo]:
        return {
            path: info
            for path in paths
            if (info := self.get(path)) is not None
        }

    def set_many(self, photo_infos: list[PhotoInfo]) -> None:
        for info in photo_infos:
            self.set(info)

    def _build_key(self, path: Path) -> PhotoCacheKey | None:
        try:
            stat = path.stat()
        except OSError:
            return None

        return (path, stat.st_mtime_ns, stat.st_size)
