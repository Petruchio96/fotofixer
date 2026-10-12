"""
Photo dates and camera names.

Why this file exists:
    Photos store their dates as EXIF text ("2026:10:03 09:14:02") in several
    tags, and their camera as separate Make and Model tags. Turning those into
    values the app can sort, show, and write back is plain text work, kept
    here without Qt so the desktop app and a later web version can share it.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta

from core.time_zones import parse_offset

# The photo's own dates, all written together by a date change (ExifTool's
# "AllDates"): when it was taken, digitized, and last modified.
DATE_TAKEN_TAGS = ("DateTimeOriginal", "CreateDate", "ModifyDate")
# The file's own "modified" date, set to match so apps that sort by file date
# agree. ExifTool reads it with a time zone ("...-06:00") and can write it back.
FILE_DATE_TAG = "FileModifyDate"
# The tags a date change writes.
DATE_WRITE_TAGS = (*DATE_TAKEN_TAGS, FILE_DATE_TAG)
# The photo's time zone ("-06:00"), one per date tag. Written only when the
# time zone is changed on purpose.
OFFSET_TAGS = ("OffsetTimeOriginal", "OffsetTimeDigitized", "OffsetTime")
# Everything read and remembered for undo.
ALL_DATE_TAGS = (*DATE_WRITE_TAGS, *OFFSET_TAGS)

EXIF_DATETIME_FORMAT = "%Y:%m:%d %H:%M:%S"

# The group name for photos without Make/Model tags (scans, edited copies).
UNKNOWN_CAMERA = "Unknown Camera"


def parse_exif_datetime(text) -> datetime | None:
    """
    "2026:10:03 09:14:02" -> datetime. Sub-seconds and a time zone after
    the seconds are ignored; empty or invalid dates ("0000:00:00 ...") give
    None.
    """
    if not isinstance(text, str) or len(text) < 19:
        return None
    try:
        return datetime.strptime(text[:19], EXIF_DATETIME_FORMAT)
    except ValueError:
        return None


def format_exif_datetime(value: datetime) -> str:
    """datetime -> "2026:10:03 09:14:02", the form ExifTool writes."""
    return value.strftime(EXIF_DATETIME_FORMAT)


def format_display_datetime(value: datetime | None) -> str:
    """
    The app's date format: "10/03/2026 9:14:02am" (month first, 12-hour
    clock, no leading zero on the hour). None -> "No date".
    """
    if value is None:
        return "No date"
    hour = value.hour % 12 or 12
    suffix = "am" if value.hour < 12 else "pm"
    return f"{value:%m/%d/%Y} {hour}:{value:%M:%S}{suffix}"


def date_taken_from_tags(tags: Mapping[str, str | None]) -> datetime | None:
    """When the photo was taken: DateTimeOriginal, or CreateDate without it."""
    return parse_exif_datetime(tags.get("DateTimeOriginal")) or parse_exif_datetime(
        tags.get("CreateDate")
    )


def time_offset_from_tags(tags: Mapping[str, str | None]) -> timedelta | None:
    """
    The photo's time zone offset, or None if no tag holds one.

    OffsetTimeOriginal goes with the date taken, so it comes first. Without
    it, OffsetTimeDigitized is the better fallback: it goes with the digitized
    date, which cameras set to the moment taken. OffsetTime goes with the
    "last changed" date, so it can hold an editing program's zone instead.
    """
    for tag in ("OffsetTimeOriginal", "OffsetTimeDigitized", "OffsetTime"):
        offset = parse_offset(tags.get(tag))
        if offset is not None:
            return offset
    return None


def camera_name(make, model) -> str | None:
    """
    A readable camera name from the Make and Model tags:
    ("Canon", "Canon EOS R6") -> "Canon EOS R6" (the make isn't repeated),
    ("Apple", "iPhone 15 Pro") -> "Apple iPhone 15 Pro",
    ("NIKON CORPORATION", "NIKON D850") -> "NIKON D850".
    None when the photo has neither tag.
    """
    make_text = str(make).strip() if make is not None else ""
    model_text = str(model).strip() if model is not None else ""
    if not model_text:
        return make_text or None
    if not make_text:
        return model_text
    # Many cameras put the brand in the model too; compare its first word
    # ("NIKON CORPORATION" -> "NIKON").
    brand = make_text.split()[0].casefold()
    if model_text.casefold().startswith(brand):
        return model_text
    return f"{make_text} {model_text}"
