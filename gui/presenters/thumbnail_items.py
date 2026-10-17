"""
Helpers for thumbnail list item presentation and selection restore.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget

from core.models import PhotoInfo
from services.geotag_service import format_altitude
from services.models import ThumbnailItemData


def build_thumbnail_item_data(photo_info: PhotoInfo, *, feet: bool = True) -> ThumbnailItemData:
    """
    Build the display fields the desktop thumbnail list needs for one photo.
    feet: altitudes in feet (the Units setting), else metres.
    """
    return ThumbnailItemData(
        path=photo_info.path,
        filename=photo_info.path.name,
        has_gps=(
            photo_info.current_latitude is not None
            and photo_info.current_longitude is not None
        ),
        latitude=photo_info.current_latitude,
        longitude=photo_info.current_longitude,
        tooltip=build_tooltip_text(
            photo_info.path.name,
            photo_info.current_latitude,
            photo_info.current_longitude,
            photo_info.current_altitude,
            feet=feet,
        ),
    )


def build_thumbnail_item_data_list(
    photo_infos: list[PhotoInfo],
    *,
    feet: bool = True,
) -> list[ThumbnailItemData]:
    """
    Build thumbnail presentation data for the current selected-photo workspace.
    """
    return sorted(
        (build_thumbnail_item_data(photo_info, feet=feet) for photo_info in photo_infos),
        key=lambda item: (item.has_gps, item.filename.lower(), item.filename),
    )


def build_tooltip_text(
    filename: str,
    latitude: float | None,
    longitude: float | None,
    altitude: float | None = None,
    *,
    feet: bool = True,
) -> str:
    """
    The hover hint of a thumbnail: the file name, its GPS coordinates (or
    "No GPS"), and its altitude on a third line when it has one.
    """
    if latitude is None or longitude is None:
        return f"{filename}\nNo GPS"
    text = f"{filename}\nGPS: {latitude:.6f}, {longitude:.6f}"
    if altitude is not None:
        text += f"\nAltitude: {format_altitude(altitude, feet)}"
    return text


def reselect_paths(
    list_widget: QListWidget,
    paths_to_select: list[Path],
) -> None:
    """
    Re-select items in the thumbnail grid after the list has been rebuilt.
    """
    wanted = {str(path) for path in paths_to_select}

    for index in range(list_widget.count()):
        item = list_widget.item(index)
        item_path = item.data(Qt.UserRole)
        item.setSelected(item_path in wanted)
