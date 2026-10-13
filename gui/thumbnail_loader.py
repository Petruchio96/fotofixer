"""
Thumbnail loading helpers.

Why this file exists:
    The main window should not need to know the details of opening image files,
    resizing them, and converting them into Qt icons.

    This module keeps that logic in one place so the GUI code stays simpler.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Final

from PySide6.QtCore import QPointF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QIcon,
    QImage,
    QImageReader,
    QPainter,
    QPixmap,
    QTransform,
)

from core.file_types import JPEG_EXTENSIONS, is_heif_file, may_hold_preview
from gui import system_thumbnails
from core.models import EmbeddedPreview
from gui.widgets.icons import draw_location_pin

# The GPS badge's color: the app's blue, for what already exists (this photo
# has GPS). The map's New Location pin is the same pin in orange (new).
BADGE_COLOR = QColor("#1f6feb")

# Reads embedded RAW previews: list of paths -> {path: EmbeddedPreview}.
type PreviewReader = Callable[[list[Path]], dict[Path, EmbeddedPreview]]


class ThumbnailLoader:
    """
    Create thumbnail icons for files selected in the app.

    Current behavior:
    1. JPG / JPEG files:
       We decode a scaled-down copy of the image with Qt.
    2. RAW files (CR2, CR3, DNG):
       We use the JPEG preview the camera stored inside the file, read through
       ExifTool, rotated to match the photo's orientation.
    3. Anything else, or if the above fails:
       We return a simple fallback icon.
    """

    # GPS badge pin size and its gap from the corner, for a 128-pixel thumbnail.
    BADGE_PIN_WIDTH: Final[float] = 20.0
    BADGE_PIN_HEIGHT: Final[float] = 28.0
    BADGE_MARGIN: Final[float] = 5.0
    MAX_CACHE_ENTRIES: Final[int] = 512

    def __init__(
        self,
        thumbnail_size: int = 128,
        preview_reader: PreviewReader | None = None,
        small_preview_reader: PreviewReader | None = None,
        use_system_cache: bool = False,
    ) -> None:
        """
        Store the target thumbnail size in pixels.

        Args:
            thumbnail_size:
                Maximum width and height for generated thumbnails.
            preview_reader:
                Reads embedded previews from RAW files. Without one, RAW files
                get the fallback icon.
            small_preview_reader:
                Reads the small thumbnails stored at the start of JPEG files,
                so a whole (possibly large, possibly network) photo doesn't
                have to be read. Without one, JPEGs are read in full.
            use_system_cache:
                Use and fill the Linux file managers' shared thumbnail cache
                (see system_thumbnails.py). Off by default so tests never touch
                the user's real cache.
        """
        self.thumbnail_size = thumbnail_size
        self.preview_reader = preview_reader
        self.small_preview_reader = small_preview_reader
        self.use_system_cache = use_system_cache and system_thumbnails.is_supported()
        self._icon_cache: dict[tuple[str, int | None, bool], QIcon] = {}

        self._fallback_icon = self._build_fallback_icon()
        self._gps_fallback_icon = self._build_badged_icon(self._fallback_icon)

    def load_icon(self, path: Path, has_gps: bool = False) -> QIcon:
        """
        Return a QIcon for the given file, building it right away if needed.

        JPEGs and RAW files get a real thumbnail; anything else, or a file
        that cannot be read, gets a fallback icon. Files with GPS metadata get
        a small badge in the top-right corner.

        This reads the file on the calling thread. For many files, use
        load_images() on a background thread and icon_from_image() instead.

        Args:
            path:
                Path to the file we want to represent in the UI.
            has_gps:
                True when the file has GPS metadata and should receive a badge.

        Returns:
            A QIcon that can be shown in a QListWidget or similar Qt widget.
        """
        cached_icon = self.cached_icon(path, has_gps)
        if cached_icon is not None:
            return cached_icon

        image = self.load_images([path]).get(path)
        return self.icon_from_image(path, has_gps, image)

    def cached_icon(self, path: Path, has_gps: bool = False) -> QIcon | None:
        """
        Return the icon if it was already built for this version of the file.
        """
        return self._icon_cache.get(self._build_cache_key(path, has_gps))

    def load_images(self, paths: list[Path]) -> dict[Path, QImage | None]:
        """
        Read thumbnail-sized images for many files, cheapest source first:

        1. The system thumbnail cache (Linux), a small local file.
        2. The preview stored inside the photo: for RAW files the embedded
           JPEG previews, for JPEGs their small EXIF thumbnail near the start
           of the file.
        3. The whole JPEG (only when it has no thumbnail inside).

        Thumbnails made from 2 or 3 are saved to the system cache.

        Safe to call on a background thread: it only uses QImage, never
        QPixmap or widgets, and does not touch the icon cache. Embedded
        previews for the whole list are read in one batch.

        Returns:
            {path: image} for every path; None where no image could be made.
        """
        images: dict[Path, QImage | None] = {}
        if self.use_system_cache:
            for path in paths:
                cached = system_thumbnails.read(path, self.thumbnail_size)
                if cached is not None:
                    images[path] = cached
        remaining = [path for path in paths if path not in images]

        raw_paths = [path for path in remaining if may_hold_preview(path)]
        jpeg_paths = [path for path in remaining if path.suffix.lower() in JPEG_EXTENSIONS]
        previews: dict[Path, EmbeddedPreview] = {}
        for reader, reader_paths in (
            (self.preview_reader, raw_paths),
            (self.small_preview_reader, jpeg_paths),
        ):
            if reader_paths and reader is not None:
                try:
                    previews.update(reader(reader_paths))
                except Exception:
                    # Thumbnails are a convenience; fall back on any failure.
                    pass

        for path in remaining:
            image = None
            if path in previews:
                image = self._preview_to_image(previews[path])
            if image is None and path.suffix.lower() in JPEG_EXTENSIONS:
                image = self._read_jpeg_image(path)
            elif image is None and is_heif_file(path):
                image = self._read_heif_image(path)
            images[path] = image
            if image is not None and self.use_system_cache:
                system_thumbnails.write(path, image)
        return images

    def icon_from_image(self, path: Path, has_gps: bool, image: QImage | None) -> QIcon:
        """
        Turn an image from load_images() into a cached icon. GUI thread only.

        A missing image gives the fallback icon.
        """
        cache_key = self._build_cache_key(path, has_gps)

        if image is None or image.isNull():
            icon = self._gps_fallback_icon if has_gps else self._fallback_icon
        else:
            pixmap = QPixmap.fromImage(image)
            if pixmap.isNull():
                icon = self._gps_fallback_icon if has_gps else self._fallback_icon
            else:
                icon = self._build_badged_icon(QIcon(pixmap)) if has_gps else QIcon(pixmap)

        self._cache_icon(cache_key, icon)
        return icon

    def fallback_icon_for(self, has_gps: bool) -> QIcon:
        """
        The plain icon used when no thumbnail is available. Not cached per
        file, so a later load tries the real thumbnail again.
        """
        return self._gps_fallback_icon if has_gps else self._fallback_icon

    def _preview_to_image(self, preview: EmbeddedPreview) -> QImage | None:
        """
        Decode an embedded preview at thumbnail size, trim any padding, and
        rotate it upright.
        """
        # Decoded straight from the bytes: a QBuffer (a QObject) must not be
        # created on the background thread this runs on. Previews are small,
        # so decoding at full size and then scaling is cheap. The RAW file's
        # orientation is applied below, not any tag inside the preview.
        image = QImage.fromData(preview.jpeg_bytes)
        if image.isNull():
            return None
        image = image.scaled(
            self.thumbnail_size,
            self.thumbnail_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )

        if preview.image_width and preview.image_height:
            image = _crop_to_aspect(image, preview.image_width, preview.image_height)
        return _apply_exif_orientation(image, preview.orientation)

    def _cache_icon(self, cache_key: tuple[str, int | None, bool], icon: QIcon) -> None:
        """
        Keep thumbnail caching bounded so long sessions do not grow memory forever.
        """
        if len(self._icon_cache) >= self.MAX_CACHE_ENTRIES:
            self._icon_cache.clear()
        self._icon_cache[cache_key] = icon

    def _build_cache_key(self, path: Path, has_gps: bool) -> tuple[str, int | None, bool]:
        """
        Cache thumbnails by path, timestamp, and GPS badge state.
        """
        try:
            modified_at = path.stat().st_mtime_ns
        except OSError:
            modified_at = None

        return (str(path), modified_at, has_gps)

    def _read_jpeg_image(self, path: Path) -> QImage | None:
        """
        Read a JPEG at thumbnail size, rotated upright using its own EXIF tag.

        Args:
            path:
                Path to a JPG/JPEG image.

        Returns:
            A QImage if reading succeeds, otherwise None.
        """
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)

        size = reader.size()
        if size.isValid():
            scaled_size = QSize(size)
            scaled_size.scale(
                self.thumbnail_size,
                self.thumbnail_size,
                Qt.KeepAspectRatio,
            )
            reader.setScaledSize(scaled_size)

        image = reader.read()
        return None if image.isNull() else image

    def _read_heif_image(self, path: Path) -> QImage | None:
        """
        Read a HEIC/HEIF at thumbnail size with pillow-heif: Qt can't decode
        HEIF on Linux or Windows. Uses the smallest thumbnail stored in the
        file that is still big enough (iPhones store one), so the full photo
        is decoded only when there is none. libheif applies the file's own
        rotation, so the image comes out upright.

        Returns:
            A QImage, or None if pillow-heif is missing or the file can't be
            read (the file then gets the plain icon).
        """
        try:
            import pillow_heif
        except ImportError:
            return None
        try:
            heif = pillow_heif.open_heif(str(path), convert_hdr_to_8bit=True)
            primary = heif[heif.primary_index]
            thumbnails = [primary.get_thumbnail(index) for index in range(len(primary.info.get("thumbnails", [])))]
            big_enough = [
                thumbnail for thumbnail in thumbnails if min(thumbnail.size) >= self.thumbnail_size // 2
            ]
            source = min(big_enough, key=lambda image: image.size[0] * image.size[1]) if big_enough else primary
            image = _heif_to_qimage(source)
        except Exception:
            # Thumbnails are a convenience: an unreadable file gets the icon.
            return None
        if image is None:
            return None
        return image.scaled(
            self.thumbnail_size,
            self.thumbnail_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )

    def _build_badged_icon(self, icon: QIcon) -> QIcon:
        """
        Draw the GPS badge in the upper-right corner of an existing icon: an
        orange teardrop pin (the map pin's shape) with a white border and dot.

        Args:
            icon:
                The base icon that represents the thumbnail.

        Returns:
            A new QIcon with the GPS badge drawn on top.
        """
        base_pixmap = icon.pixmap(self.thumbnail_size, self.thumbnail_size)

        # If Qt fails to render the thumbnail pixmap, return the original icon
        # instead of trying to draw on an invalid surface.
        if base_pixmap.isNull():
            return icon

        # Sized for a 128-pixel thumbnail, scaled for other sizes.
        scale = self.thumbnail_size / 128
        width = self.BADGE_PIN_WIDTH * scale
        height = self.BADGE_PIN_HEIGHT * scale
        margin = self.BADGE_MARGIN * scale

        # Use the actual pixmap width, not the requested thumbnail size:
        # thumbnails keep their aspect ratio, so they may be narrower.
        tip = QPointF(base_pixmap.width() - margin - width / 2, margin + height)
        painter = QPainter(base_pixmap)
        draw_location_pin(
            painter,
            tip,
            width=width,
            height=height,
            fill=BADGE_COLOR,
            outline=2 * scale,
            dot_radius=3.6 * scale,
            shadow=True,
        )
        painter.end()

        return QIcon(base_pixmap)

    def _create_fallback_icon(self) -> QIcon:
        return self._fallback_icon

    def _build_fallback_icon(self) -> QIcon:
        """
        Create a simple placeholder icon for files that do not have a real
        thumbnail yet.

        For version 1, this is good enough for RAW files and any image that
        fails thumbnail generation.

        Returns:
            A basic square QIcon.
        """
        pixmap = QPixmap(self.thumbnail_size, self.thumbnail_size)
        pixmap.fill(Qt.lightGray)
        return QIcon(pixmap)


def _apply_exif_orientation(image: QImage, orientation: int) -> QImage:
    """
    Rotate and/or mirror an image according to an EXIF orientation value.

    EXIF orientations: 1 normal, 2 mirrored, 3 rotated 180, 4 flipped
    vertically, 5 mirrored + rotated 270, 6 rotated 90, 7 mirrored + rotated
    90, 8 rotated 270 (all rotations clockwise).
    """
    mirror = orientation in (2, 4, 5, 7)
    rotation = {3: 180, 4: 180, 5: 270, 6: 90, 7: 90, 8: 270}.get(orientation, 0)

    if mirror:
        image = image.transformed(QTransform().scale(-1, 1))
    if rotation:
        image = image.transformed(QTransform().rotate(rotation))
    return image


def _heif_to_qimage(heif_image) -> QImage | None:
    """A decoded pillow-heif image (8-bit RGB or RGBA) as a QImage."""
    formats = {"RGB": QImage.Format_RGB888, "RGBA": QImage.Format_RGBA8888}
    image_format = formats.get(heif_image.mode)
    if image_format is None:
        return None
    width, height = heif_image.size
    data = bytes(heif_image.data)
    # copy(): the QImage must own its pixels once data goes away.
    return QImage(data, width, height, heif_image.stride, image_format).copy()


def _crop_to_aspect(image: QImage, width: int, height: int) -> QImage:
    """
    Crop an image, centered, to the width:height shape of the full photo.

    Removes the black bars some cameras add to small previews (Canon CR3
    thumbnails are 4:3 while the photo is 3:2). Images already within 2% of
    the right shape are returned unchanged.
    """
    target_ratio = width / height
    image_ratio = image.width() / image.height()
    if abs(image_ratio / target_ratio - 1) < 0.02:
        return image

    if image_ratio < target_ratio:
        # Too tall for the photo's shape: trim the top and bottom.
        new_height = max(1, round(image.width() / target_ratio))
        top = (image.height() - new_height) // 2
        return image.copy(0, top, image.width(), new_height)

    # Too wide: trim the left and right.
    new_width = max(1, round(image.height() * target_ratio))
    left = (image.width() - new_width) // 2
    return image.copy(left, 0, new_width, image.height())
