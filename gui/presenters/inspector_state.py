"""
Presenter for the inspector panel (the right side of the window).

Why this file exists:
    The inspector shows what is selected in the photo grid and what can be done
    with it. Working that out (labels, counts, which buttons are enabled, and
    why not) is plain logic, kept here without any Qt code so it is easy to
    test and can be reused by a future web interface.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from core.models import GpsCoordinates, PhotoInfo
from services.coordinate_service import parse_manual_coordinates


@dataclass(frozen=True)
class InspectorState:
    # Selection summary
    title: str
    selected_count: int
    gps_summary: str
    # Set only when exactly one photo is selected and it has GPS.
    single_photo_coordinates: GpsCoordinates | None
    can_use_location: bool

    # New location fields
    new_location: GpsCoordinates | None

    # Apply
    can_apply: bool
    apply_label: str
    # Shown above the Apply button: why it is disabled, or a heads-up.
    apply_hint: str
    apply_hint_tone: str
    overwrite_count: int

    # Remove GPS
    can_remove_gps: bool
    remove_gps_label: str
    remove_gps_count: int


def _photos(count: int) -> str:
    return f"{count} Photo" if count == 1 else f"{count} Photos"


def _gps_of(info: PhotoInfo | None) -> GpsCoordinates | None:
    if info is None or info.current_latitude is None or info.current_longitude is None:
        return None
    return GpsCoordinates(info.current_latitude, info.current_longitude)


def format_coordinates(coordinates: GpsCoordinates) -> str:
    return f"{coordinates.latitude:.6f}, {coordinates.longitude:.6f}"


def build_inspector_state(
    *,
    selected_paths: list[Path],
    photo_infos: Mapping[Path, PhotoInfo],
    latitude_text: str,
    longitude_text: str,
    source_path: Path | None = None,
) -> InspectorState:
    """
    Work out everything the inspector panel shows for the current selection.

    Args:
        selected_paths:
            Photos selected in the grid. These are the photos Apply and
            Remove GPS act on.
        photo_infos:
            Loaded metadata for the photos, keyed by path.
        latitude_text / longitude_text:
            Contents of the New location fields.
        source_path:
            The photo the New location was copied from, if any. Apply never
            writes to it (it already has that location), even when selected.
    """
    count = len(selected_paths)
    gps_by_path = {path: _gps_of(photo_infos.get(path)) for path in selected_paths}
    with_gps = [path for path in selected_paths if gps_by_path[path] is not None]

    # Selection summary
    single_coordinates = None
    if count == 0:
        title = "No Photos Selected"
        gps_summary = "Click photos in the Photo List to select them."
    elif count == 1:
        title = "1 Photo Selected"
        single_coordinates = gps_by_path[selected_paths[0]]
        gps_summary = (
            f"{selected_paths[0].name} · GPS: {format_coordinates(single_coordinates)}"
            if single_coordinates is not None
            else f"{selected_paths[0].name} · No GPS"
        )
    else:
        title = f"{count} Photos Selected"
        gps_summary = f"{count - len(with_gps)} without GPS · {len(with_gps)} with GPS"

    # New location
    parsed = parse_manual_coordinates(latitude_text, longitude_text)
    new_location = GpsCoordinates(*parsed) if parsed is not None else None
    fields_empty = not latitude_text.strip() and not longitude_text.strip()

    # Apply: every selected photo except the source photo.
    source_selected = source_path is not None and source_path in gps_by_path
    targets = [path for path in selected_paths if path != source_path]
    target_count = len(targets)
    can_apply = target_count > 0 and new_location is not None
    apply_label = (
        f"Apply Location to {_photos(target_count)}"
        if target_count
        else "Apply Location to Selected Photos"
    )
    overwrite_count = (
        sum(1 for path in targets if gps_by_path[path] is not None) if can_apply else 0
    )
    if count == 0:
        apply_hint, apply_hint_tone = "Select the photos to change in the Photo List.", "info"
    elif target_count == 0:
        apply_hint = (
            "The selected photo is the source of the new location, so it isn't changed. "
            "Select the photos to give its location to."
        )
        apply_hint_tone = "info"
    elif new_location is None and fields_empty:
        apply_hint = "Set a new location above: copy it from a photo, type, or paste one."
        apply_hint_tone = "info"
    elif new_location is None:
        apply_hint = "The new location isn't valid. Check the latitude and longitude."
        apply_hint_tone = "error"
    elif overwrite_count:
        apply_hint = (
            f"{_photos(overwrite_count).lower()} already "
            f"{'has' if overwrite_count == 1 else 'have'} GPS, which will be replaced."
        )
        apply_hint_tone = "warning"
    elif source_selected:
        apply_hint, apply_hint_tone = "The source photo isn't changed.", "info"
    else:
        apply_hint, apply_hint_tone = "", "info"

    # Remove GPS: counts only the selected photos that have GPS to remove.
    remove_count = len(with_gps)
    remove_label = (
        f"Remove GPS from Selected {_photos(remove_count)}"
        if remove_count
        else "Remove GPS from Selected Photos"
    )

    return InspectorState(
        title=title,
        selected_count=count,
        gps_summary=gps_summary,
        single_photo_coordinates=single_coordinates,
        can_use_location=single_coordinates is not None,
        new_location=new_location,
        can_apply=can_apply,
        apply_label=apply_label,
        apply_hint=apply_hint,
        apply_hint_tone=apply_hint_tone,
        overwrite_count=overwrite_count,
        can_remove_gps=remove_count > 0,
        remove_gps_label=remove_label,
        remove_gps_count=remove_count,
    )
