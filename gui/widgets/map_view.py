"""
The map widget: map tiles drawn with QPainter, the New Location pin, and a dot
for each photo with GPS.

A plain QWidget instead of a web view or QML keeps the builds small and lets
the tests drive it with real mouse events. Tiles are downloaded with
QNetworkAccessManager on the GUI thread (no background thread involved) and
kept in a disk cache, so places seen before still show offline.

Mouse:
    - Click the map (a quick click): move the New Location pin there. A
      press held longer, or one that moves at all, grabs the map instead,
      so a sloppy click-and-hold doesn't move the pin by accident.
    - Drag the pin: move it; the new place is reported when it is dropped.
    - Drag anywhere else: pan. Wheel (or + and -): zoom.
    - Hold the space bar (as in Photoshop): an open hand; dragging then
      always pans (even from the pin or a photo dot) and a click does
      nothing, so the pin can't move by accident. Pointing at the map gives
      it the keyboard, so the space bar never presses a focused button.
    - Hover a photo dot: its file name. Click it: photo_pins_clicked.

Zoom levels can be in between whole levels (opening on the photos fits them
exactly); tiles come from the nearest whole level and are scaled.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QImage, QPainter, QPen, QPixmap
from PySide6.QtNetwork import (
    QNetworkAccessManager,
    QNetworkDiskCache,
    QNetworkReply,
    QNetworkRequest,
)
from PySide6.QtWidgets import QLabel, QToolTip, QWidget

from core.map_tiles import (
    MAX_ZOOM,
    MIN_ZOOM,
    STREET_MAP,
    TILE_SIZE,
    TileSource,
    clamp,
    lat_lon_to_world,
    visible_tiles,
    world_size,
    world_to_lat_lon,
    zoom_to_fit,
)
from gui.widgets.icons import draw_location_pin, location_pin_path

# Tile download results (TileFetcher.tile_finished).
TILE_LOADED = 0
TILE_MISSING = 1  # The server has no tile here (satellite outside the US).
TILE_FAILED = 2  # Network error, for example offline.
TILE_DENIED = 3  # The server refused the API key.

# HTTP statuses that mean the API key was refused (498/499 are ArcGIS's
# "invalid token" and "token required").
KEY_REFUSED_STATUSES = {401, 403, 498, 499}

# Wait this long before downloading a tile that failed again.
FAILED_TILE_RETRY_SECONDS = 15

# Tiles kept in memory; the disk cache holds many more.
MEMORY_TILE_LIMIT = 600

# Disk cache size for downloaded tiles.
DISK_CACHE_BYTES = 200 * 1024 * 1024

# A press that moves less than this is a click, not a drag (small, so a
# slight wiggle while holding pans instead of moving the pin).
DRAG_THRESHOLD = 2

# Only a press released within this many seconds counts as a click that
# moves the pin; holding longer means grabbing the map.
QUICK_CLICK_SECONDS = 0.30

# A click on the map while its window isn't the active one only brings the
# window back: it doesn't move the pin. As a backup (systems differ in the
# order they report things), neither does a click within this many seconds
# of the window becoming active. Tests set it to 0.
ACTIVATION_CLICK_SECONDS = 0.3

# Photos whose dots are this close on screen look like one dot, and share
# one preview ("1 of 2"); farther apart, each dot is its own.
SAME_SPOT_PIXELS = 2

# Photo dots: radius, white outline width, and how close the mouse must be
# to hover or click one.
PHOTO_DOT_RADIUS = 7
PHOTO_DOT_OUTLINE = 2.5
PHOTO_HIT_RADIUS = 10

# Colors: blue = what exists, orange = what is new or will change. The New
# Location pin is the GPS badge's pin in orange (the Apply button's); photos
# are the app's blue with a white outline; selected photos are orange
# (circles, not the pin's teardrop).
PIN_COLOR = QColor("#d97706")
PHOTO_COLOR = QColor("#1f6feb")
SELECTED_PHOTO_COLOR = QColor("#d97706")
BACKGROUND_COLOR = QColor("#e8edf2")
NOTE_TEXT_COLOR = QColor("#31445a")

# New Location pin size: the tip sits on the location.
PIN_WIDTH = 26
PIN_HEIGHT = 36

# Names listed in a dot's hover hint before "and N more".
TOOLTIP_NAME_LIMIT = 6

OFFLINE_NOTE = "Some map tiles could not be downloaded. Places viewed before still show offline."


def crosshair_cursor() -> QCursor:
    """
    The map's pointer: a crosshair with a small ring, dark with a white
    halo so it shows on light streets and dark aerial photos alike.

    Drawn at the screen's own scale, with the hot spot (the point clicks
    use) left for Qt to put in the middle: a 2x pixmap on a 1x Linux screen
    put the hot spot up and to the left of the crosshair's center.
    """
    screen = QGuiApplication.primaryScreen()
    scale = max(1, round(screen.devicePixelRatio())) if screen is not None else 1
    size = 33
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.setDevicePixelRatio(scale)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    middle = size / 2
    for color, width in ((QColor(255, 255, 255, 230), 4.0), (QColor("#102033"), 1.6)):
        pen = QPen(color, width)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(middle, middle), 6, 6)
        for start, end in ((3, 10), (size - 10, size - 3)):
            painter.drawLine(QPointF(start, middle), QPointF(end, middle))
            painter.drawLine(QPointF(middle, start), QPointF(middle, end))
    painter.end()
    # -1, -1: the hot spot is the middle of the pixmap.
    return QCursor(pixmap, -1, -1)


def _distance(a: QPointF, b: QPointF) -> float:
    offset = a - b
    return (offset.x() ** 2 + offset.y() ** 2) ** 0.5


def tile_key(source: TileSource, zoom: int, x: int, y: int) -> tuple[str, int, int, int]:
    return (source.key, zoom, x, y)


class TileFetcher(QObject):
    """
    Downloads tiles. Tests replace it with a fake that never uses the network.

    When a download ends, tile_finished(source key, zoom, x, y, result)
    fires, with result TILE_LOADED, TILE_MISSING, TILE_FAILED, or
    TILE_DENIED; a loaded tile's image is then collected with take_image().
    """

    tile_finished = Signal(str, int, int, int, int)

    def fetch(self, source: TileSource, zoom: int, x: int, y: int, api_key: str = "") -> None:
        """
        Start downloading a tile. api_key is the user's key for sources
        that need one (source.needs_key), or "".
        """
        raise NotImplementedError

    def take_image(self, key: tuple[str, int, int, int]) -> QImage | None:
        raise NotImplementedError

    def abort_except(self, keep: set[tuple[str, int, int, int]]) -> None:
        """
        Stop downloads no longer needed (the map moved on).
        """

    def is_pending(self, key: tuple[str, int, int, int]) -> bool:
        raise NotImplementedError


class NetworkTileFetcher(TileFetcher):
    """
    Downloads tiles over HTTPS with a disk cache that honors the servers'
    cache headers (OpenStreetMap's tile usage policy asks for both, and for
    a User-Agent that identifies the app).
    """

    def __init__(self, *, user_agent: str, cache_directory: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._user_agent = user_agent.encode("utf-8")
        self._manager = QNetworkAccessManager(self)
        cache = QNetworkDiskCache(self)
        cache.setCacheDirectory(str(cache_directory))
        cache.setMaximumCacheSize(DISK_CACHE_BYTES)
        self._manager.setCache(cache)
        self._replies: dict[tuple[str, int, int, int], QNetworkReply] = {}
        self._images: dict[tuple[str, int, int, int], QImage] = {}

    def fetch(self, source: TileSource, zoom: int, x: int, y: int, api_key: str = "") -> None:
        key = tile_key(source, zoom, x, y)
        if key in self._replies:
            return
        request = QNetworkRequest(QUrl(source.tile_url(zoom, x, y, api_key)))
        request.setRawHeader(b"User-Agent", self._user_agent)
        # Use a cached tile when there is one, even an old one; download otherwise.
        request.setAttribute(
            QNetworkRequest.Attribute.CacheLoadControlAttribute,
            QNetworkRequest.CacheLoadControl.PreferCache,
        )
        reply = self._manager.get(request)
        self._replies[key] = reply
        reply.finished.connect(lambda: self._finished(key, reply))

    def _finished(self, key: tuple[str, int, int, int], reply: QNetworkReply) -> None:
        if self._replies.get(key) is reply:
            del self._replies[key]
        reply.deleteLater()
        error = reply.error()
        if error == QNetworkReply.NetworkError.OperationCanceledError:
            # Aborted because the map moved on; nobody is waiting for it.
            return

        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if error == QNetworkReply.NetworkError.NoError:
            data = reply.readAll()
            image = QImage.fromData(data)
            if not image.isNull():
                self._images[key] = image
                result = TILE_LOADED
            elif b'"error"' in bytes(data):
                # ArcGIS answers a missing or bad key with "200 OK" and a
                # JSON error ("Token Required", "Invalid Token").
                result = TILE_DENIED
            else:
                result = TILE_MISSING
        elif status in KEY_REFUSED_STATUSES:
            result = TILE_DENIED
        elif status == 404 or error == QNetworkReply.NetworkError.ContentNotFoundError:
            result = TILE_MISSING
        else:
            result = TILE_FAILED
        self.tile_finished.emit(*key, result)

    def take_image(self, key: tuple[str, int, int, int]) -> QImage | None:
        return self._images.pop(key, None)

    def abort_except(self, keep: set[tuple[str, int, int, int]]) -> None:
        for key in [key for key in self._replies if key not in keep]:
            self._replies.pop(key).abort()

    def is_pending(self, key: tuple[str, int, int, int]) -> bool:
        return key in self._replies


@dataclass(frozen=True)
class PhotoPin:
    """
    A photo with GPS, shown as a dot on the map.
    """

    path: str
    latitude: float
    longitude: float
    selected: bool = False


class MapView(QWidget):
    """
    The map. The owner sets the pin and photo dots, and listens for:

    location_picked(latitude, longitude):
        The user clicked the map or dropped the pin.
    pointer_moved(latitude, longitude), pointer_left():
        Where the mouse is on the map, for the coordinate readout.
    tiles_changed():
        A tile finished downloading (or failed), or the view moved: check
        has_tile_problem().
    photo_pins_clicked(paths, global x, global y):
        The user clicked a photo dot; paths lists every photo under the
        mouse, nearest first (photos taken at one spot overlap).
    view_changed():
        The map was panned, zoomed, or switched to another style.
    """

    location_picked = Signal(float, float)
    pointer_moved = Signal(float, float)
    pointer_left = Signal()
    tiles_changed = Signal()
    photo_pins_clicked = Signal(list, int, int)
    view_changed = Signal()

    def __init__(self, fetcher: TileFetcher, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("mapView")
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(320, 240)
        self._crosshair = crosshair_cursor()
        self.setCursor(self._crosshair)

        self._fetcher = fetcher
        self._fetcher.tile_finished.connect(self._tile_finished)
        self._source = STREET_MAP
        self._zoom = 4.0
        # Center of the view in world coordinates (see core.map_tiles).
        self._center_x, self._center_y = lat_lon_to_world(39.5, -98.35)

        self._pin: tuple[float, float] | None = None
        self._photo_pins: list[PhotoPin] = []

        # Loaded tiles (most recently used last), and tiles the server
        # doesn't have or that failed to download (key -> when).
        self._tiles: OrderedDict[tuple[str, int, int, int], QPixmap] = OrderedDict()
        self._missing: set[tuple[str, int, int, int]] = set()
        self._failed: dict[tuple[str, int, int, int], float] = {}
        # Tiles refused because of the API key, and the user's keys by
        # source key (only for sources that need one).
        self._denied: set[tuple[str, int, int, int]] = set()
        self._api_keys: dict[str, str] = {}

        # Mouse state for the press in progress.
        self._press_pos: QPointF | None = None
        self._press_time = 0.0
        # When the window last became active, and whether it was active when
        # the button went down (see ACTIVATION_CLICK_SECONDS).
        self._activated_at = float("-inf")
        self._press_window_active = True
        # Whether the map's window (or its photo preview) has the focus.
        # While another program is active the map shows the normal arrow
        # and no hints: a click there only brings the window back.
        self._window_active = False
        # The map is inside the map window, and Qt tells only windows (not
        # the widgets in them) about activation, so watch the app's focus.
        # On Linux the window manager re-activates the window before the
        # click arrives, so the timing check is what catches the click.
        QGuiApplication.instance().focusWindowChanged.connect(self._focus_window_changed)
        self._press_center = (self._center_x, self._center_y)
        self._press_on_pin = False
        self._pin_grab_offset = QPointF()
        self._dragging = False
        # The space bar is held down (pan mode), and whether it was when the
        # button went down (that press only pans).
        self._space_held = False
        self._press_with_space = False
        self._wheel_remainder = 0

        self._retry_timer = QTimer(self)
        self._retry_timer.setSingleShot(True)
        self._retry_timer.timeout.connect(self._request_visible_tiles)

        # The credit line the tile licenses require, with clickable links.
        self._attribution = QLabel(self)
        self._attribution.setObjectName("mapAttribution")
        self._attribution.setTextFormat(Qt.RichText)
        self._attribution.setOpenExternalLinks(True)
        self._attribution.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self._update_attribution()

    # --- Public state ---------------------------------------------------------

    @property
    def source(self) -> TileSource:
        return self._source

    @property
    def zoom(self) -> float:
        return self._zoom

    @property
    def pin(self) -> tuple[float, float] | None:
        return self._pin

    @property
    def center(self) -> tuple[float, float]:
        """
        The latitude and longitude at the middle of the view.
        """
        return world_to_lat_lon(self._center_x, self._center_y)

    def set_api_key(self, source_key: str, api_key: str) -> None:
        """
        Set (or with "" remove) the user's key for a source that needs one.
        Tiles refused with the old key are tried again.
        """
        self._api_keys[source_key] = api_key
        self._denied = {key for key in self._denied if key[0] != source_key}
        self._failed = {key: when for key, when in self._failed.items() if key[0] != source_key}
        if self._source.key == source_key:
            self._view_changed()

    def api_key(self, source_key: str) -> str:
        return self._api_keys.get(source_key, "")

    def has_api_key(self, source: TileSource) -> bool:
        return bool(self.api_key(source.key))

    def set_source(self, source: TileSource) -> None:
        if source == self._source:
            return
        self._source = source
        self._update_attribution()
        self._view_changed()

    def set_view(self, latitude: float, longitude: float, zoom: float) -> None:
        self._zoom = float(clamp(zoom, MIN_ZOOM, MAX_ZOOM))
        self._center_x, self._center_y = lat_lon_to_world(latitude, longitude)
        self._view_changed()

    def zoom_by(self, steps: int, anchor: QPointF | None = None) -> None:
        """
        Zoom in (positive steps) or out by whole levels, keeping the place
        under anchor (default: the middle of the view) where it is.
        """
        new_zoom = float(clamp(self._zoom + steps, MIN_ZOOM, MAX_ZOOM))
        if new_zoom == self._zoom:
            return
        if anchor is None:
            anchor = QPointF(self.width() / 2, self.height() / 2)
        anchor_x, anchor_y = self._screen_to_world(anchor)
        self._zoom = new_zoom
        size = world_size(new_zoom)
        self._center_x = anchor_x - (anchor.x() - self.width() / 2) / size
        self._center_y = anchor_y - (anchor.y() - self.height() / 2) / size
        self._view_changed()

    def fit_points(
        self,
        points: list[tuple[float, float]],
        *,
        padding: float = 0.1,
        max_zoom: float = 16,
    ) -> None:
        """
        Show every (latitude, longitude) point, as close as possible with a
        margin of padding times the view's size on every side.
        """
        if not points:
            return
        self._center_x, self._center_y, self._zoom = zoom_to_fit(
            points,
            max(self.width(), 320),
            max(self.height(), 240),
            padding=padding,
            max_zoom=max_zoom,
        )
        self._view_changed()

    def set_pin(self, location: tuple[float, float] | None, *, reveal: bool = False) -> None:
        """
        Place (or remove, with None) the New Location pin. With reveal, the
        map moves to the pin if it is outside the view.
        """
        self._pin = location
        if location is not None and reveal and not self.is_visible_on_map(*location):
            self._center_x, self._center_y = lat_lon_to_world(*location)
            self._view_changed()
        else:
            self.update()

    def set_photo_pins(self, pins: list[PhotoPin]) -> None:
        # Selected photos are drawn last, on top of the others.
        self._photo_pins = sorted(pins, key=lambda pin: pin.selected)
        self.update()

    def screen_point_for(self, latitude: float, longitude: float) -> QPointF:
        return self._world_to_screen(*lat_lon_to_world(latitude, longitude))

    def lat_lon_at(self, point: QPointF) -> tuple[float, float]:
        return world_to_lat_lon(*self._screen_to_world(point))

    def is_visible_on_map(self, latitude: float, longitude: float) -> bool:
        point = self.screen_point_for(latitude, longitude)
        return QRectF(self.rect()).contains(point)

    def photo_paths_at(self, point: QPointF) -> list[str]:
        """
        The photos at the dot under point: the nearest dot's photo, and any
        others drawn at the same spot (they look like one dot). Photos on
        nearby but separate dots are left out.
        """
        nearest = None
        for pin in self._photo_pins:
            spot = self.screen_point_for(pin.latitude, pin.longitude)
            distance = _distance(spot, point)
            if distance <= PHOTO_HIT_RADIUS and (nearest is None or distance < nearest[0]):
                nearest = (distance, spot)
        if nearest is None:
            return []
        same_spot = []
        for pin in self._photo_pins:
            spot = self.screen_point_for(pin.latitude, pin.longitude)
            if _distance(spot, nearest[1]) <= SAME_SPOT_PIXELS:
                same_spot.append((_distance(spot, point), pin.path))
        same_spot.sort()
        return [path for _distance_to_point, path in same_spot]

    def hover_text_at(self, point: QPointF) -> str:
        """
        What the hover hint says at point: the file names of the photos
        under the mouse, or "" for none.
        """
        paths = self.photo_paths_at(point)
        if not paths:
            return ""
        names = [Path(path).name for path in paths[:TOOLTIP_NAME_LIMIT]]
        if len(paths) > TOOLTIP_NAME_LIMIT:
            names.append(f"and {len(paths) - TOOLTIP_NAME_LIMIT} more")
        return "\n".join(names)

    def has_tile_problem(self) -> bool:
        """
        True if tiles in view were refused (the API key) or could not be
        downloaded, or a source that needs a key has none.
        """
        if self._source.needs_key and not self.has_api_key(self._source):
            return True
        return any(key in self._denied or key in self._failed for key in self._needed_tile_keys())

    def notes(self) -> list[str]:
        """
        Notes shown over the map for the view right now: tiles that could
        not be downloaded, or no imagery here.
        """
        needed = self._needed_tile_keys()
        notes = []
        # A source with the user's key has its own banner in the map window
        # (check the key in Settings, or use another map) instead.
        if not self._source.needs_key and any(key in self._failed for key in needed):
            notes.append(OFFLINE_NOTE)
        if self._source.coverage_note and any(key in self._missing for key in needed):
            notes.append(self._source.coverage_note)
        return notes

    # --- Coordinates ----------------------------------------------------------

    def _world_to_screen(self, x: float, y: float) -> QPointF:
        size = world_size(self._zoom)
        return QPointF(
            (x - self._center_x) * size + self.width() / 2,
            (y - self._center_y) * size + self.height() / 2,
        )

    def _screen_to_world(self, point: QPointF) -> tuple[float, float]:
        size = world_size(self._zoom)
        return (
            self._center_x + (point.x() - self.width() / 2) / size,
            self._center_y + (point.y() - self.height() / 2) / size,
        )

    def _clamp_center(self) -> None:
        """
        Keep the world in view: no panning off its edges. A world smaller
        than the view (zoomed far out) stays in the middle.
        """
        size = world_size(self._zoom)
        half_width = self.width() / 2 / size
        half_height = self.height() / 2 / size
        self._center_x = 0.5 if half_width >= 0.5 else clamp(self._center_x, half_width, 1 - half_width)
        self._center_y = 0.5 if half_height >= 0.5 else clamp(self._center_y, half_height, 1 - half_height)

    # --- Tiles ----------------------------------------------------------------

    def _tile_zoom(self) -> int:
        """
        The whole zoom level the view's tiles are laid out at (the view's
        zoom rounded); they are drawn scaled by _tile_scale().
        """
        return int(round(self._zoom))

    def _tile_scale(self) -> float:
        return 2 ** (self._zoom - self._tile_zoom())

    def _visible_tiles(self) -> list[tuple[int, int]]:
        scale = self._tile_scale()
        return visible_tiles(
            self._center_x,
            self._center_y,
            self._tile_zoom(),
            int(self.width() / scale) + 1,
            int(self.height() / scale) + 1,
        )

    def _download_zoom(self, tile_zoom: int) -> int:
        """
        The level tiles for a view laid out at tile_zoom are downloaded at:
        the same level, or the server's closest level when zoomed in
        further (those tiles are enlarged).
        """
        return min(tile_zoom, self._source.max_zoom)

    def _source_zoom(self) -> int:
        return self._download_zoom(self._tile_zoom())

    def _needed_tile_keys(self) -> list[tuple[str, int, int, int]]:
        source_zoom = self._source_zoom()
        shift = self._tile_zoom() - source_zoom
        keys: list[tuple[str, int, int, int]] = []
        for x, y in self._visible_tiles():
            key = tile_key(self._source, source_zoom, x >> shift, y >> shift)
            if key not in keys:
                keys.append(key)
        return keys

    def _view_changed(self) -> None:
        self._clamp_center()
        self._request_visible_tiles()
        self.update()
        self.view_changed.emit()
        self.tiles_changed.emit()

    def _request_visible_tiles(self) -> None:
        if self.width() <= 0 or self.height() <= 0:
            return
        needed = self._needed_tile_keys()
        self._fetcher.abort_except(set(needed))
        now = time.monotonic()
        retry_later = False
        if self._source.needs_key and not self.has_api_key(self._source):
            # Nothing can be downloaded until the user adds a key.
            return
        api_key = self._api_keys.get(self._source.key, "")
        for key in needed:
            if (
                key in self._tiles
                or key in self._missing
                or key in self._denied
                or self._fetcher.is_pending(key)
            ):
                continue
            failed_at = self._failed.get(key)
            if failed_at is not None and now - failed_at < FAILED_TILE_RETRY_SECONDS:
                retry_later = True
                continue
            _source_key, zoom, x, y = key
            self._fetcher.fetch(self._source, zoom, x, y, api_key)
        if retry_later and not self._retry_timer.isActive():
            self._retry_timer.start(FAILED_TILE_RETRY_SECONDS * 1000)

    def _tile_finished(self, source_key: str, zoom: int, x: int, y: int, result: int) -> None:
        key = (source_key, zoom, x, y)
        if result == TILE_LOADED:
            image = self._fetcher.take_image(key)
            if image is not None:
                self._failed.pop(key, None)
                self._tiles[key] = QPixmap.fromImage(image)
                while len(self._tiles) > MEMORY_TILE_LIMIT:
                    self._tiles.popitem(last=False)
        elif result == TILE_MISSING:
            self._missing.add(key)
        elif result == TILE_DENIED:
            self._denied.add(key)
        else:
            self._failed[key] = time.monotonic()
            if not self._retry_timer.isActive():
                self._retry_timer.start(FAILED_TILE_RETRY_SECONDS * 1000)
        self.update()
        self.tiles_changed.emit()

    def _cached_tile_part(self, zoom: int, x: int, y: int) -> tuple[QPixmap, QRectF] | None:
        """
        The loaded tile that covers tile (x, y) at zoom, and the part of it
        to draw: the tile itself, or a part of a coarser tile (enlarged)
        while the detailed one downloads or when the server has none.
        """
        start_zoom = self._download_zoom(zoom)
        for source_zoom in range(start_zoom, max(-1, start_zoom - 6), -1):
            shift = zoom - source_zoom
            key = tile_key(self._source, source_zoom, x >> shift, y >> shift)
            pixmap = self._tiles.get(key)
            if pixmap is None:
                continue
            self._tiles.move_to_end(key)
            part = TILE_SIZE / (2 ** shift)
            offset_x = (x - ((x >> shift) << shift)) * part
            offset_y = (y - ((y >> shift) << shift)) * part
            scale = pixmap.width() / TILE_SIZE
            return pixmap, QRectF(offset_x * scale, offset_y * scale, part * scale, part * scale)
        return None

    def _update_attribution(self) -> None:
        self._attribution.setText(self._source.attribution_html)
        self._attribution.adjustSize()
        self._place_attribution()

    def _place_attribution(self) -> None:
        self._attribution.move(
            self.width() - self._attribution.width(),
            self.height() - self._attribution.height(),
        )

    # --- Painting -------------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), BACKGROUND_COLOR)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        tile_zoom = self._tile_zoom()
        tile_count = 2 ** tile_zoom
        drawn_size = TILE_SIZE * self._tile_scale()
        for x, y in self._visible_tiles():
            part = self._cached_tile_part(tile_zoom, x, y)
            if part is None:
                continue
            top_left = self._world_to_screen(x / tile_count, y / tile_count)
            # One extra pixel hides hairline seams between scaled tiles.
            target = QRectF(top_left.x(), top_left.y(), drawn_size + 1, drawn_size + 1)
            painter.drawPixmap(target, part[0], part[1])

        painter.setRenderHint(QPainter.Antialiasing)
        for pin in self._photo_pins:
            self._draw_photo_dot(painter, pin)
        if self._pin is not None:
            self._draw_location_pin(painter, self.screen_point_for(*self._pin))
        self._draw_notes(painter)
        painter.end()

    def _draw_photo_dot(self, painter: QPainter, pin: PhotoPin) -> None:
        center = self.screen_point_for(pin.latitude, pin.longitude)
        painter.setPen(QPen(QColor("#ffffff"), PHOTO_DOT_OUTLINE))
        painter.setBrush(SELECTED_PHOTO_COLOR if pin.selected else PHOTO_COLOR)
        painter.drawEllipse(center, PHOTO_DOT_RADIUS, PHOTO_DOT_RADIUS)

    def _draw_location_pin(self, painter: QPainter, tip: QPointF) -> None:
        draw_location_pin(painter, tip, width=PIN_WIDTH, height=PIN_HEIGHT, fill=PIN_COLOR)

    def _is_on_pin(self, point: QPointF) -> bool:
        if self._pin is None:
            return False
        tip = self.screen_point_for(*self._pin)
        return location_pin_path(tip, PIN_WIDTH, PIN_HEIGHT).contains(point)

    def _draw_notes(self, painter: QPainter) -> None:
        notes = self.notes()
        if not notes:
            return
        text = "\n".join(notes)
        metrics = painter.fontMetrics()
        bounds = metrics.boundingRect(
            0, 0, max(200, self.width() - 80), 1000, Qt.AlignCenter | Qt.TextWordWrap, text
        )
        box = QRectF(
            (self.width() - bounds.width()) / 2 - 12, 12, bounds.width() + 24, bounds.height() + 14
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 230))
        painter.drawRoundedRect(box, 8, 8)
        painter.setPen(NOTE_TEXT_COLOR)
        painter.drawText(box, Qt.AlignCenter | Qt.TextWordWrap, text)

    # --- Events ---------------------------------------------------------------

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place_attribution()
        self._clamp_center()
        self._request_visible_tiles()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._window_active = self._has_focus_window()
        self._request_visible_tiles()

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        position = event.position()
        self._press_pos = position
        # perf_counter: Windows' monotonic clock only ticks every ~16 ms,
        # too coarse to order the window's activation and a click.
        self._press_time = time.perf_counter()
        self._press_window_active = self._window_active
        self._press_center = (self._center_x, self._center_y)
        self._press_with_space = self._space_held
        # With the space bar held, even a press on the pin grabs the map.
        self._press_on_pin = not self._space_held and self._is_on_pin(position)
        if self._press_on_pin:
            self._pin_grab_offset = self.screen_point_for(*self._pin) - position
        self._dragging = False
        # The closed hand right away: holding the button grabs the map (or
        # the pin). A photo dot keeps the pointing hand: a click opens it.
        if self._press_on_pin or self._space_held or not self.photo_paths_at(position):
            self.setCursor(Qt.ClosedHandCursor)
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        position = event.position()
        self.pointer_moved.emit(*self.lat_lon_at(position))
        if self._press_pos is None or not event.buttons() & Qt.LeftButton:
            self._update_hover_cursor(position)
            return

        delta = position - self._press_pos
        if not self._dragging and max(abs(delta.x()), abs(delta.y())) < DRAG_THRESHOLD:
            return
        self._dragging = True
        self.setCursor(Qt.ClosedHandCursor)
        if self._press_on_pin:
            self._pin = self.lat_lon_at(position + self._pin_grab_offset)
            self.update()
        else:
            size = world_size(self._zoom)
            self._center_x = self._press_center[0] - delta.x() / size
            self._center_y = self._press_center[1] - delta.y() / size
            self._view_changed()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.LeftButton or self._press_pos is None:
            super().mouseReleaseEvent(event)
            return
        position = event.position()
        was_dragging = self._dragging
        on_pin = self._press_on_pin
        with_space = self._press_with_space
        self._press_pos = None
        self._dragging = False
        self._press_on_pin = False
        self._press_with_space = False
        self._update_hover_cursor(position)

        if with_space:
            # Space bar pan mode: a drag only panned, and a click does nothing.
            return

        if was_dragging:
            if on_pin and self._pin is not None:
                self.location_picked.emit(*self._pin)
            return
        if on_pin:
            # A click on the pin itself leaves it where it is.
            return
        paths = self.photo_paths_at(position)
        if paths:
            global_point = event.globalPosition().toPoint()
            self.photo_pins_clicked.emit(paths, global_point.x(), global_point.y())
            return
        held = time.perf_counter() - self._press_time
        if held > QUICK_CLICK_SECONDS:
            # Held, not clicked: grabbing the map, not choosing a place.
            return
        if (
            not self._press_window_active
            or self._activated_at > self._press_time - ACTIVATION_CLICK_SECONDS
        ):
            # This click switched back to the window (from another app):
            # it doesn't choose a place.
            return
        self._pin = self.lat_lon_at(position)
        self.update()
        self.location_picked.emit(*self._pin)

    def wheelEvent(self, event) -> None:
        # Touchpads send many small steps; zoom one level per notch (120).
        self._wheel_remainder += event.angleDelta().y()
        steps = int(self._wheel_remainder / 120)
        if steps:
            self._wheel_remainder -= steps * 120
            self.zoom_by(steps, event.position())
        event.accept()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Space:
            # Holding the key repeats the press: only the first one counts.
            if not event.isAutoRepeat():
                self._set_space_held(True)
            event.accept()
        elif event.key() in (Qt.Key_Plus, Qt.Key_Equal):
            self.zoom_by(1)
        elif event.key() == Qt.Key_Minus:
            self.zoom_by(-1)
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        if event.key() == Qt.Key_Space:
            if not event.isAutoRepeat():
                # A drag still going on finishes as a pan.
                self._set_space_held(False)
            event.accept()
        else:
            super().keyReleaseEvent(event)

    def focusOutEvent(self, event) -> None:
        # The key's release goes elsewhere now: leave pan mode.
        self._set_space_held(False)
        super().focusOutEvent(event)

    def enterEvent(self, event) -> None:
        # Pointing at the map gives it the keyboard (+/-, the space bar), so
        # the space bar never presses a focused button such as Done.
        if self._window_active and not self.hasFocus():
            self.setFocus(Qt.MouseFocusReason)
        super().enterEvent(event)

    def _set_space_held(self, held: bool) -> None:
        if held == self._space_held:
            return
        self._space_held = held
        if self._press_pos is None:
            self._update_hover_cursor(QPointF(self.mapFromGlobal(QCursor.pos())))

    def event(self, event) -> bool:
        if event.type() == QEvent.ToolTip:
            # No photo names while another program is active.
            text = self.hover_text_at(QPointF(event.pos())) if self._window_active else ""
            if text:
                QToolTip.showText(event.globalPos(), text, self)
            else:
                QToolTip.hideText()
                event.ignore()
            return True
        return super().event(event)

    def _focus_window_changed(self, _window) -> None:
        active = self._has_focus_window()
        if active and not self._window_active:
            # Back from another program (not just from the photo preview).
            self._activated_at = time.perf_counter()
        self._window_active = active
        if not active:
            QToolTip.hideText()
        self._update_hover_cursor(QPointF(self.mapFromGlobal(QCursor.pos())))

    def _has_focus_window(self) -> bool:
        """
        True if the focus is in the map's window, or in a window that
        belongs to it (the photo preview).
        """
        mine = self.window().windowHandle()
        focus = QGuiApplication.focusWindow()
        while focus is not None:
            if focus is mine:
                return True
            focus = focus.transientParent()
        return False

    def leaveEvent(self, event) -> None:
        self.pointer_left.emit()
        super().leaveEvent(event)

    def _update_hover_cursor(self, position: QPointF) -> None:
        if not self._window_active:
            self.setCursor(Qt.ArrowCursor)
            return
        if self._space_held:
            self.setCursor(Qt.OpenHandCursor)
        elif self._is_on_pin(position):
            self.setCursor(Qt.OpenHandCursor)
        elif self.photo_paths_at(position):
            self.setCursor(Qt.PointingHandCursor)
        else:
            self.setCursor(self._crosshair)
