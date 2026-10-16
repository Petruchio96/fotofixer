"""
Use-case services for applying GPS coordinates to target files.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from core.models import PhotoInfo
from services.target_paths_service import get_overwrite_entries, get_target_paths
from services.models import ApplyExecutionResult, ApplyPreparation, SourceResolution

# on_progress(done, total): called after each file a write goes through.
Progress = Callable[[int, int], None]


def prepare_apply_gps(
    *,
    selected_paths: list[Path],
    using_photo_source: bool,
    source_photo_path: Path | None,
    source_resolution: SourceResolution,
    photo_info_by_path: Mapping[Path, PhotoInfo],
) -> ApplyPreparation:
    """
    Validate the current workflow state before attempting to write metadata.
    """
    target_paths = get_target_paths(
        selected_paths,
        using_photo_source,
        source_photo_path,
    )

    if not target_paths:
        return ApplyPreparation(
            target_paths=[],
            error_message="Select one or more photos before applying GPS.",
        )

    if source_resolution.coordinates is None:
        return ApplyPreparation(
            target_paths=target_paths,
            error_message=source_resolution.error_message,
        )

    return ApplyPreparation(
        target_paths=target_paths,
        overwrite_entries=get_overwrite_entries(photo_info_by_path, target_paths),
        coordinates=source_resolution.coordinates,
    )


def apply_gps_to_paths(
    target_paths: list[Path],
    *,
    latitude: float,
    longitude: float,
    writer,
    on_progress: Progress | None = None,
) -> ApplyExecutionResult:
    """
    Write GPS metadata to each target path and collect failures.
    """
    return _write_each(
        target_paths,
        lambda path: writer.write_gps(path, latitude, longitude),
        on_progress,
    )


def clear_gps_from_paths(
    target_paths: list[Path],
    *,
    writer,
    on_progress: Progress | None = None,
) -> ApplyExecutionResult:
    """
    Remove GPS metadata from each target path and collect failures.
    """
    return _write_each(target_paths, writer.clear_gps, on_progress)


def restore_gps_states(
    states: Mapping[Path, tuple[float | None, float | None]],
    *,
    writer,
    on_progress: Progress | None = None,
) -> ApplyExecutionResult:
    """
    Write each file back to a remembered GPS state (used by undo and redo).

    (None, None) means the file had no GPS, so its GPS is cleared. A third
    value is an altitude (a geotag from a GPS track), written with the rest.
    """
    def restore(path: Path) -> None:
        latitude, longitude, *rest = states[path]
        altitude = rest[0] if rest else None
        if latitude is None or longitude is None:
            writer.clear_gps(path)
        elif altitude is None:
            writer.write_gps(path, latitude, longitude)
        else:
            writer.write_gps(path, latitude, longitude, altitude)

    return _write_each(list(states), restore, on_progress)


def write_gps_values(
    values: Mapping[Path, tuple[float, float, float | None]],
    *,
    writer,
    on_progress: Progress | None = None,
) -> ApplyExecutionResult:
    """
    Write each file its own position (geotagging from a GPS track):
    {path: (latitude, longitude, altitude or None)}. Every file is
    attempted; failures are in the result.
    """
    def write(path: Path) -> None:
        latitude, longitude, altitude = values[path]
        if altitude is None:
            writer.write_gps(path, latitude, longitude)
        else:
            writer.write_gps(path, latitude, longitude, altitude)

    return _write_each(list(values), write, on_progress)


def write_date_tags_to_paths(
    values_by_path: Mapping[Path, Mapping[str, str | None]],
    *,
    writer,
    on_progress: Progress | None = None,
) -> ApplyExecutionResult:
    """
    Write date tags to each file (a date change, or its undo/redo) and
    collect failures. Every file is attempted.
    """
    return _write_each(
        list(values_by_path),
        lambda path: writer.write_date_tags(path, dict(values_by_path[path])),
        on_progress,
    )


def _write_each(paths: list[Path], write, on_progress: Progress | None = None) -> ApplyExecutionResult:
    """
    Run one write per file. A failure on one file never stops the others;
    every failure is reported in the result. on_progress(done, total) is
    called after each file (for a progress bar).
    """
    successful_paths: list[Path] = []
    failed_paths: list[str] = []

    for index, path in enumerate(paths, start=1):
        try:
            write(path)
            successful_paths.append(path)
        except Exception as exc:
            failed_paths.append(f"{path.name}: {exc}")
        if on_progress is not None:
            on_progress(index, len(paths))

    return ApplyExecutionResult(
        success_count=len(successful_paths),
        successful_paths=successful_paths,
        failed_paths=failed_paths,
    )
