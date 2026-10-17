from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


@dataclass
class GpsCoordinates:
    latitude: float
    longitude: float
    # Copied with the coordinates when the location comes from a photo that
    # has one (Apply Location); None leaves the targets' altitude alone.
    altitude: Optional[float] = None


@dataclass
class PhotoInfo:
    path: Path
    file_type: str
    current_latitude: Optional[float] = None
    current_longitude: Optional[float] = None
    # Metres above sea level (negative below), None without one. Only a
    # geotag from a GPS track writes it; it is read so undo can restore it.
    current_altitude: Optional[float] = None
    gps_error: Optional[str] = None
    # When the photo was taken (DateTimeOriginal, or CreateDate without it).
    date_taken: Optional[datetime] = None
    # The photo's time zone offset (OffsetTimeOriginal), None if it has none.
    time_offset: Optional[timedelta] = None
    # Readable camera name from Make and Model (see core/photo_dates.py).
    camera: Optional[str] = None
    # The date tags exactly as read (tag -> ExifTool text, None if missing),
    # so undo can put back precisely what was there.
    date_tags: dict[str, Optional[str]] = field(default_factory=dict)


@dataclass
class WriteResult:
    path: Path
    success: bool
    message: str


@dataclass(frozen=True)
class EmbeddedPreview:
    """
    A JPEG preview stored inside a RAW file, used for thumbnails.

    jpeg_bytes:
        The preview image, stored unrotated.
    orientation:
        EXIF orientation of the photo, 1-8 (1 = upright). Apply it to the
        preview for display.
    image_width / image_height:
        Size of the full photo before rotation, if known. Some cameras pad
        small previews with black bars (Canon CR3 thumbnails are 4:3 while the
        photo is 3:2); cropping the preview to this shape removes them.
    """

    jpeg_bytes: bytes
    orientation: int = 1
    image_width: int | None = None
    image_height: int | None = None

