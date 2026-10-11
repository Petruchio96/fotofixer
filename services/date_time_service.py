"""
Date & Time workflow logic: what a shift or set changes, and camera groups.

Why this file exists:
    The Date & Time tab has three ways to change dates:
    1. Shift: the camera's clock was off, so every selected photo moves by
       the same amount (the gaps between them stay right). The amount comes
       from the correct date and time of one reference photo.
    2. Set: every selected photo gets one exact date and time.
    3. Change time zone: the photos get another time zone. Normally the
       moment they were taken stays the same (the clock times change to
       show it in the new zone); optionally the clock times stay instead.
    All end as "these photos get these new dates (and zones)", written with
    write_date_tags. Every change works on the moment a photo was taken: a
    photo's time zone only says how that moment is written down. The Photo List also groups photos by camera in this
    mode. None of this needs Qt, so it lives here.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from core.models import PhotoInfo
from core.photo_dates import (
    ALL_DATE_TAGS,
    DATE_WRITE_TAGS,
    OFFSET_TAGS,
    UNKNOWN_CAMERA,
    format_exif_datetime,
)
from core.time_zones import Zone, format_offset, offset_at_local, to_zone


@dataclass
class DatePlan:
    """
    What a date change will do.

    new_dates:
        The photos to change and the date each one gets, in date order.
    unchanged:
        Photos whose new date would equal their current one (not written).
    skipped_undated:
        Shift only: photos without a date (nothing to shift from).
    new_offsets:
        When a time zone was chosen: the zone offset each changed photo
        gets (otherwise every photo keeps its own).
    """

    new_dates: dict[Path, datetime] = field(default_factory=dict)
    new_offsets: dict[Path, timedelta] = field(default_factory=dict)
    unchanged: list[Path] = field(default_factory=list)
    skipped_undated: list[Path] = field(default_factory=list)


def photos_by_date(
    infos: Mapping[Path, PhotoInfo],
    paths: Iterable[Path],
    *,
    exclude: Path | None = None,
) -> list[Path]:
    """The photos that have a date, earliest first (then by file name)."""
    dated = [
        path for path in paths
        if path != exclude and (info := infos.get(path)) is not None and info.date_taken is not None
    ]
    return sorted(dated, key=lambda path: (infos[path].date_taken, path.name.casefold()))


def shift_between(old: datetime, new: datetime) -> timedelta:
    """The shift that moves a photo from old to new."""
    return new - old


def photo_instant(info: PhotoInfo, zone: Zone | None = None) -> datetime | None:
    """
    When a photo was taken, in UTC (naive), from its clock time and its own
    time zone. A photo without one is taken to be in zone (its clock time is
    kept when it gets that zone), or, with no zone either, its clock time is
    used as is.
    """
    if info.date_taken is None:
        return None
    offset = info.time_offset
    if offset is None and zone is not None:
        offset = offset_at_local(zone, info.date_taken)
    return info.date_taken - (offset or timedelta(0))


def shifted_clock(
    info: PhotoInfo,
    shift: timedelta,
    zone: Zone | None = None,
) -> tuple[datetime, timedelta | None]:
    """
    A photo's new clock time and time zone after a shift.

    shift moves the moment the photo was taken. Without a zone the photo
    keeps its own time zone, so its clock moves by the same amount. With a
    zone, the new moment is shown in that zone (same moment, different
    clock; daylight saving is worked out for each photo's date).
    """
    if zone is None:
        return info.date_taken + shift, info.time_offset
    clock, offset = to_zone(photo_instant(info, zone) + shift, zone)
    return clock, offset


def plan_shift(
    infos: Mapping[Path, PhotoInfo],
    paths: Iterable[Path],
    shift: timedelta,
    *,
    exclude: Path | None = None,
    zone: Zone | None = None,
) -> DatePlan:
    """
    Move every photo with a date by the same amount. exclude is the photo
    the correct time was copied from: it is never changed. With a zone,
    every photo also gets that time zone (see shifted_clock).
    """
    path_list = [path for path in paths if path != exclude]
    plan = DatePlan()
    for path in photos_by_date(infos, path_list):
        info = infos[path]
        new, offset = shifted_clock(info, shift, zone)
        if new != info.date_taken or (zone is not None and offset != info.time_offset):
            plan.new_dates[path] = new
            if zone is not None:
                plan.new_offsets[path] = offset
        else:
            plan.unchanged.append(path)
    plan.skipped_undated = [
        path for path in path_list
        if (info := infos.get(path)) is None or info.date_taken is None
    ]
    return plan


def plan_set(
    infos: Mapping[Path, PhotoInfo],
    paths: Iterable[Path],
    value: datetime,
    *,
    zone: Zone | None = None,
) -> DatePlan:
    """
    Give every photo the same date and time (photos without one too). With
    a zone, the time is in that zone and every photo gets the zone.
    """
    plan = DatePlan()
    offset = offset_at_local(zone, value) if zone is not None else None
    for path in paths:
        info = infos.get(path)
        same_time = info is not None and info.date_taken == value
        same_zone = zone is None or (info is not None and info.time_offset == offset)
        if same_time and same_zone:
            plan.unchanged.append(path)
        else:
            plan.new_dates[path] = value
            if zone is not None:
                plan.new_offsets[path] = offset
    return plan


def plan_zone_change(
    infos: Mapping[Path, PhotoInfo],
    paths: Iterable[Path],
    zone: Zone,
    *,
    keep_clock: bool = False,
) -> DatePlan:
    """
    Give every photo with a date the time zone zone.

    keep_clock False (the default): the moment stays the same and the clock
    time changes to show it in the new zone (10:05 MDT -> 11:05 CDT).
    keep_clock True: the clock time stays and only the zone changes (11:16
    MDT -> 11:16 CDT), which moves the moment; for photos whose times were
    right but whose zone was wrong. A photo without a zone has no known
    moment either way, so it keeps its clock time and just gets the zone.
    Daylight saving is worked out for each photo's own date.
    """
    path_list = list(paths)
    if not keep_clock:
        # The same moment in another zone is a shift of nothing in that zone.
        return plan_shift(infos, path_list, timedelta(0), zone=zone)

    plan = DatePlan()
    for path in photos_by_date(infos, path_list):
        info = infos[path]
        offset = offset_at_local(zone, info.date_taken)
        if offset == info.time_offset:
            plan.unchanged.append(path)
        else:
            plan.new_dates[path] = info.date_taken
            plan.new_offsets[path] = offset
    plan.skipped_undated = [
        path for path in path_list
        if (info := infos.get(path)) is None or info.date_taken is None
    ]
    return plan


def date_tag_values(value: datetime, offset: timedelta | None = None) -> dict[str, str]:
    """
    The tag values a change writes: every date tag set to the new date, and
    the time zone tags when a zone was chosen (otherwise they stay as is).
    """
    text = format_exif_datetime(value)
    values = {tag: text for tag in DATE_WRITE_TAGS}
    if offset is not None:
        values.update({tag: format_offset(offset) for tag in OFFSET_TAGS})
    return values


def saved_date_tags(info: PhotoInfo | None) -> dict[str, str | None]:
    """A photo's date tags as read, for undo (missing tags are None)."""
    tags = info.date_tags if info is not None else {}
    return {tag: tags.get(tag) for tag in ALL_DATE_TAGS}


def camera_of(info: PhotoInfo | None) -> str:
    return (info.camera if info is not None else None) or UNKNOWN_CAMERA


def cameras_in(infos: Mapping[Path, PhotoInfo], paths: Iterable[Path]) -> list[str]:
    """The cameras of these photos, sorted by name, Unknown Camera last."""
    return sorted({camera_of(infos.get(path)) for path in paths}, key=_camera_sort_key)


def group_by_camera(
    infos: Mapping[Path, PhotoInfo],
    paths: Iterable[Path],
) -> list[tuple[str, list[Path]]]:
    """
    The Photo List's groups in Date & Time mode: one per camera (sorted by
    name, Unknown Camera last). Inside a group, photos are in date order
    (then by file name), and photos without a date come last.
    """
    groups: dict[str, list[Path]] = {}
    for path in paths:
        groups.setdefault(camera_of(infos.get(path)), []).append(path)

    def photo_key(path: Path):
        info = infos.get(path)
        date = info.date_taken if info is not None else None
        return (date is None, date or datetime.min, path.name.casefold())

    return [
        (camera, sorted(groups[camera], key=photo_key))
        for camera in sorted(groups, key=_camera_sort_key)
    ]


def _camera_sort_key(camera: str):
    return (camera == UNKNOWN_CAMERA, camera.casefold())
