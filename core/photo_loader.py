"""
Load photo information from disk and convert it into our application's model objects.

Why this file exists:
    The ExifTool wrapper gives us raw GPS data in a simple dictionary format.
    The rest of the application should not have to know how ExifTool works.

    This module acts as a bridge between:
    1. a file on disk
    2. the ExifTool metadata reader
    3. the PhotoInfo dataclass used by the app

This keeps responsibilities clean:
    exiftool_wrapper.py -> talks to ExifTool
    photo_loader.py     -> builds PhotoInfo objects
"""

from __future__ import annotations

from pathlib import Path

from core.exiftool_wrapper import ExifToolWrapper
from core.file_types import is_supported_file
from core.models import PhotoInfo
from core.photo_dates import camera_name, date_taken_from_tags, time_offset_from_tags


class PhotoLoader:
    """
    Load metadata for a single photo and return it in our app's data model.

    This class hides the details of:
    1. checking supported file types
    2. calling the ExifTool wrapper
    3. handling missing GPS data
    4. handling read errors
    """

    def __init__(self, exiftool: ExifToolWrapper) -> None:
        """
        Store a reference to the ExifTool wrapper.

        Args:
            exiftool:
                An ExifToolWrapper instance used to read GPS metadata.
        """
        self.exiftool = exiftool

    def load_photo_info(self, path: Path) -> PhotoInfo:
        """
        Load one photo and convert its metadata into a PhotoInfo object.

        Args:
            path:
                Path to the photo file.

        Returns:
            A PhotoInfo object containing file type, GPS data, and any error
            message if something goes wrong.
        """
        info = PhotoInfo(
            path=path,
            file_type=path.suffix.upper().lstrip("."),
        )

        if not is_supported_file(path):
            info.gps_error = "Unsupported file type."
            return info

        try:
            _apply_metadata(info, self.exiftool.read_gps(path))
        except Exception as exc:
            info.gps_error = str(exc)

        return info

    def load_photo_infos(self, paths: list[Path]) -> list[PhotoInfo]:
        """
        Load many photos, using bulk metadata reads where possible.
        """
        photo_infos_by_path = {
            path: PhotoInfo(
                path=path,
                file_type=path.suffix.upper().lstrip("."),
            )
            for path in paths
        }
        supported_paths: list[Path] = []

        for path, info in photo_infos_by_path.items():
            if is_supported_file(path):
                supported_paths.append(path)
            else:
                info.gps_error = "Unsupported file type."

        if not supported_paths:
            return [photo_infos_by_path[path] for path in paths]

        try:
            gps_by_path = self.exiftool.read_gps_many(supported_paths)
        except Exception:
            return [self.load_photo_info(path) for path in paths]

        missing_paths: list[Path] = []
        for path in supported_paths:
            gps_data = gps_by_path.get(path)
            if gps_data is None:
                missing_paths.append(path)
                continue

            _apply_metadata(photo_infos_by_path[path], gps_data)

        for path in missing_paths:
            photo_infos_by_path[path] = self.load_photo_info(path)

        return [photo_infos_by_path[path] for path in paths]


def _apply_metadata(info: PhotoInfo, metadata: dict) -> None:
    """Copy one file's metadata (GPS, dates, camera) into its PhotoInfo."""
    info.current_latitude = metadata.get("latitude")
    info.current_longitude = metadata.get("longitude")
    info.date_tags = dict(metadata.get("date_tags") or {})
    info.date_taken = date_taken_from_tags(info.date_tags)
    info.time_offset = time_offset_from_tags(info.date_tags)
    info.camera = camera_name(metadata.get("make"), metadata.get("model"))
