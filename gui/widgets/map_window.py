"""
The pop-out map window, opened with "Pick from a Map".

The map is one more source for New Location, not a separate workflow:
clicking the map or dropping the pin fills the latitude/longitude fields in
the main window, and the usual "Apply Location to N Photos" button writes
them. The pin also follows coordinates already in New Location.

The window is modal (the main window can't be used while it is open, but
it is shown with show(), not a blocking exec()); Select Location (Cancel
without a pin) or Esc closes it, and
the New Location it set is then ready to apply. Photos in
the Photo List with GPS show as blue dots (orange when selected); hovering one
shows its file name, and clicking one shows a small preview.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QKeySequence
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.map_tiles import (
    CONTIGUOUS_US_CORNERS,
    ESRI_SATELLITE_MAP,
    SATELLITE_MAP,
    STREET_MAP,
    TileSource,
)
from gui.widgets.map_view import MapView, PhotoPin, TileFetcher
from gui.window_frame import apply_window_border

MAP_HINT = (
    "Click the map to set the New Location, or drag the orange pin. "
    "Then click Select Location, and Apply in the main window."
)

# Size of the thumbnail in the photo preview.
PREVIEW_SIZE = 128

# The coordinate readout under the map while the mouse is elsewhere.
READOUT_IDLE = "Point at the map to see its coordinates"

# Shown over the map when Esri's imagery doesn't load.
ESRI_PROBLEM_TEXT = (
    "Esri satellite imagery didn't load. Check your Esri key in Edit > Settings "
    "(close the map first), or use the US satellite map."
)

# Opening on photos (or the US): margin around them, as a share of the
# map's size on every side, and the closest zoom for a single photo.
FIT_PADDING = 0.12
SINGLE_PHOTO_ZOOM = 15


class PhotoPreviewPopup(QFrame):
    """
    A small preview of the photo(s) under a clicked dot: thumbnail, file
    name, and Use This Location. Photos taken at one spot overlap, so it
    steps through them with < and >. Clicking the thumbnail zooms the map to
    the photo. Closes when clicking elsewhere.
    """

    use_location = Signal(str)
    zoom_to = Signal(str)

    def __init__(self, parent: QWidget, icon_for: Callable[[Path], QIcon]) -> None:
        super().__init__(parent, Qt.Popup)
        self.setObjectName("mapPreview")
        self._icon_for = icon_for
        self._paths: list[str] = []
        self._index = 0
        # Photos selected to change: they can't be the location source.
        self.unavailable: set[str] = set()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        # A flat button: clicking the thumbnail zooms to the photo.
        self.thumbnail_button = QPushButton()
        self.thumbnail_button.setObjectName("previewThumb")
        self.thumbnail_button.setFixedSize(PREVIEW_SIZE + 8, PREVIEW_SIZE + 8)
        self.thumbnail_button.setIconSize(QSize(PREVIEW_SIZE, PREVIEW_SIZE))
        self.thumbnail_button.setCursor(Qt.PointingHandCursor)
        self.thumbnail_button.setToolTip("Zoom the map to this photo's location")
        self.thumbnail_button.clicked.connect(self._zoom_to_current)
        self.name_label = QLabel()
        self.name_label.setObjectName("mapPreviewName")
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setWordWrap(True)
        self.name_label.setMaximumWidth(220)

        # "< 1 of 2 >": small arrow buttons right beside the count.
        self.previous_button = QPushButton("<")
        self.previous_button.setObjectName("previewStep")
        self.previous_button.setToolTip("Previous photo at this spot")
        self.previous_button.clicked.connect(lambda: self._step(-1))
        self.count_label = QLabel()
        self.count_label.setObjectName("previewCount")
        self.count_label.setAlignment(Qt.AlignCenter)
        self.next_button = QPushButton(">")
        self.next_button.setObjectName("previewStep")
        self.next_button.setToolTip("Next photo at this spot")
        self.next_button.clicked.connect(lambda: self._step(1))
        self.stepper = QWidget()
        stepper_layout = QHBoxLayout(self.stepper)
        stepper_layout.setContentsMargins(0, 0, 0, 0)
        stepper_layout.setSpacing(4)
        stepper_layout.addStretch(1)
        stepper_layout.addWidget(self.previous_button)
        stepper_layout.addWidget(self.count_label)
        stepper_layout.addWidget(self.next_button)
        stepper_layout.addStretch(1)

        self.use_button = QPushButton("Use This Location")
        self.use_button.setObjectName("pickButton")
        self.use_button.setToolTip("Copy this photo's location into New Location")
        self.use_button.clicked.connect(self._use_location)

        layout.addWidget(self.thumbnail_button, 0, Qt.AlignHCenter)
        layout.addWidget(self.name_label)
        layout.addWidget(self.stepper)
        layout.addWidget(self.use_button)

    @property
    def current_path(self) -> str | None:
        return self._paths[self._index] if self._paths else None

    def show_photos(self, paths: list[str], global_point: QPoint) -> None:
        self._paths = list(paths)
        self._index = 0
        self._show_current()
        self.adjustSize()
        # Just below and to the right of the click.
        self.move(global_point + QPoint(12, 12))
        self.show()

    def _step(self, offset: int) -> None:
        self._index = (self._index + offset) % len(self._paths)
        self._show_current()

    def _show_current(self) -> None:
        path = Path(self._paths[self._index])
        self.thumbnail_button.setIcon(self._icon_for(path))
        self.name_label.setText(path.name)
        several = len(self._paths) > 1
        self.stepper.setVisible(several)
        self.count_label.setText(f"{self._index + 1} of {len(self._paths)}")
        being_changed = str(path) in self.unavailable
        self.use_button.setEnabled(not being_changed)
        self.use_button.setToolTip(
            "This photo is selected to change, so it can't be the location source too. "
            "Deselect it in the Photo List to use its location."
            if being_changed
            else "Copy this photo's location into New Location"
        )

    def _use_location(self) -> None:
        path = self.current_path
        self.hide()
        if path is not None:
            self.use_location.emit(path)

    def _zoom_to_current(self) -> None:
        path = self.current_path
        if path is not None:
            self.zoom_to.emit(path)


class MapWindow(QWidget):
    """
    The map window. The main window keeps it in sync (set_pin,
    set_photo_pins) and listens for:

    location_picked(latitude, longitude):
        Clicked or dropped on the map: fill New Location with it.
    use_photo_location(path):
        Use This Location in a photo's preview.
    view_changed():
        Panned, zoomed, or another map style.

    Two map buttons: Street, and one satellite button that is "Satellite"
    (Esri) when the user has an ArcGIS key in Settings, or "US Satellite"
    (USGS) when not, or after "Use US Satellite Instead".
    """

    location_picked = Signal(float, float)
    use_photo_location = Signal(str)
    view_changed = Signal()
    # Clear: empty New Location (the pin goes away) to start over.
    clear_requested = Signal()
    # Back (or Ctrl+Z): the New Location before the last change on the map.
    back_requested = Signal()

    def __init__(
        self,
        parent: QWidget,
        *,
        fetcher: TileFetcher,
        icon_for: Callable[[Path], QIcon],
    ) -> None:
        # A separate window that blocks the main window while open (as the
        # Add Photos picker does). Shown with show(), never a blocking exec().
        super().__init__(parent, Qt.Window)
        self.setWindowModality(Qt.ApplicationModal)
        self.setObjectName("mapWindow")
        self.setWindowTitle("Map - FotoFixer")
        self.resize(960, 700)
        self.setMinimumSize(480, 360)
        self._photo_locations: list[tuple[float, float]] = []
        self._photo_location_by_path: dict[str, tuple[float, float]] = {}
        # The user's ArcGIS key, and True after "Use US Satellite Instead"
        # (until the map is opened again).
        self._esri_key = ""
        self._use_us_satellite = False

        self.map_view = MapView(fetcher, self)
        self.map_view.location_picked.connect(self.location_picked)
        self.map_view.photo_pins_clicked.connect(self._show_preview)
        self.map_view.view_changed.connect(self._view_changed)
        self.map_view.pointer_moved.connect(self._show_pointer_location)
        self.map_view.pointer_left.connect(lambda: self.readout_label.setText(READOUT_IDLE))
        self.map_view.tiles_changed.connect(self._update_esri_problem)

        self.preview = PhotoPreviewPopup(self, icon_for)
        self.preview.use_location.connect(self.use_photo_location)
        self.preview.zoom_to.connect(self._zoom_to_photo)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addLayout(self._build_toolbar())
        self.hint_label = QLabel(MAP_HINT)
        self.hint_label.setObjectName("mapHint")
        self.hint_label.setWordWrap(True)
        layout.addWidget(self.hint_label)
        layout.addWidget(self._build_esri_problem_banner())
        layout.addWidget(self.map_view, 1)
        # The coordinates under the mouse, updated as it moves.
        self.readout_label = QLabel(READOUT_IDLE)
        self.readout_label.setObjectName("mapReadout")
        self.readout_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        # "Select Location" with a pin, "Cancel" without (see _update_buttons).
        self.done_button = QPushButton()
        self.done_button.setMinimumWidth(130)
        self.done_button.clicked.connect(self.close)
        self.clear_button = QPushButton("Clear")
        self.clear_button.setProperty("tone", "neutral")
        self.clear_button.setMinimumWidth(110)
        self.clear_button.clicked.connect(self.clear_requested)
        self.back_button = QPushButton("Back")
        self.back_button.setProperty("tone", "neutral")
        self.back_button.setMinimumWidth(110)
        self.back_button.clicked.connect(self.back_requested)
        self.set_back_enabled(False)
        bottom = QHBoxLayout()
        bottom.addWidget(self.readout_label, 1)
        bottom.addWidget(self.back_button)
        bottom.addWidget(self.clear_button)
        bottom.addWidget(self.done_button)
        layout.addLayout(bottom)
        self._update_buttons()

    def _build_toolbar(self) -> QHBoxLayout:
        toolbar = QHBoxLayout()
        toolbar.setSpacing(0)

        # Street / Satellite, styled like the Photo List's Show filter.
        self.street_button = QPushButton(STREET_MAP.name)
        self.street_button.setProperty("segment", "first")
        self.street_button.setToolTip("Show the OpenStreetMap street map")
        self.street_button.clicked.connect(self.show_street_map)
        self.satellite_button = QPushButton()
        self.satellite_button.setProperty("segment", "last")
        self.satellite_button.clicked.connect(self.show_satellite_map)
        for button in (self.street_button, self.satellite_button):
            button.setObjectName("filterButton")
            button.setCheckable(True)
            toolbar.addWidget(button)
        toolbar.addStretch(1)

        self.show_photos_button = QPushButton("Show All Photo Locations")
        self.show_photos_button.setProperty("tone", "neutral")
        self.show_photos_button.clicked.connect(self.show_all_photos)
        self.show_pin_button = QPushButton("Go to Selected Location")
        self.show_pin_button.setProperty("tone", "neutral")
        self.show_pin_button.clicked.connect(self.show_new_location)
        self.zoom_out_button = QPushButton("−")
        self.zoom_out_button.setProperty("tone", "neutral")
        self.zoom_out_button.setToolTip("Zoom out (or scroll the mouse wheel)")
        self.zoom_out_button.setFixedWidth(40)
        self.zoom_out_button.clicked.connect(lambda: self.map_view.zoom_by(-1))
        self.zoom_in_button = QPushButton("+")
        self.zoom_in_button.setProperty("tone", "neutral")
        self.zoom_in_button.setToolTip("Zoom in (or scroll the mouse wheel)")
        self.zoom_in_button.setFixedWidth(40)
        self.zoom_in_button.clicked.connect(lambda: self.map_view.zoom_by(1))

        for button in (self.show_photos_button, self.show_pin_button):
            toolbar.addWidget(button)
            toolbar.addSpacing(8)
        toolbar.addSpacing(8)
        toolbar.addWidget(self.zoom_out_button)
        toolbar.addSpacing(4)
        toolbar.addWidget(self.zoom_in_button)
        self._show_source_checked()
        return toolbar

    # --- Kept in sync by the main window --------------------------------------

    def set_pin(self, location: tuple[float, float] | None, *, reveal: bool = False) -> None:
        self.map_view.set_pin(location, reveal=reveal)
        self._update_buttons()

    def set_back_enabled(self, enabled: bool) -> None:
        self.back_button.setEnabled(enabled)
        self.back_button.setToolTip(
            "Go back to the location before your last change (Ctrl+Z)"
            if enabled
            else "Nothing to go back to yet"
        )

    def set_photo_pins(self, pins: list[PhotoPin]) -> None:
        self._photo_locations = [(pin.latitude, pin.longitude) for pin in pins]
        self._photo_location_by_path = {pin.path: (pin.latitude, pin.longitude) for pin in pins}
        self.map_view.set_photo_pins(pins)
        self.preview.unavailable = {pin.path for pin in pins if pin.selected}
        if self.preview.isVisible() and self.preview.current_path not in {pin.path for pin in pins}:
            # The photo left the list or lost its GPS.
            self.preview.hide()
        self._update_buttons()

    def set_esri_key(self, api_key: str) -> None:
        """
        The user's ArcGIS key from Settings ("" for none). Satellite shows
        Esri with a key, USGS without.
        """
        self._esri_key = api_key
        self.map_view.set_api_key(ESRI_SATELLITE_MAP.key, api_key)
        if self.map_view.source != STREET_MAP:
            self.map_view.set_source(self.satellite_source())
        self._show_source_checked()

    def reset_for_opening(self) -> None:
        """
        Each time the map opens: the street map, and Satellite back to Esri
        if there is a key (after "Use US Satellite Instead" last time).
        """
        self._use_us_satellite = False
        self.show_street_map()

    def satellite_source(self) -> TileSource:
        """
        What the satellite button shows: Esri with a key, otherwise USGS.
        """
        if self._esri_key and not self._use_us_satellite:
            return ESRI_SATELLITE_MAP
        return SATELLITE_MAP

    def show_street_map(self) -> None:
        self.map_view.set_source(STREET_MAP)
        self._show_source_checked()

    def show_satellite_map(self) -> None:
        self.map_view.set_source(self.satellite_source())
        self._show_source_checked()

    def use_us_satellite_instead(self) -> None:
        """
        Esri's imagery didn't load: show USGS instead until the map is
        opened again.
        """
        self._use_us_satellite = True
        self.show_satellite_map()

    # --- Toolbar --------------------------------------------------------------

    def show_all_photos(self) -> None:
        self.map_view.fit_points(
            self._photo_locations, padding=FIT_PADDING, max_zoom=SINGLE_PHOTO_ZOOM
        )

    def show_photos_or_united_states(self) -> None:
        """
        Where the map opens: the New Location (the orange pin) when one is
        already set, at street level; else every photo with GPS, or with
        none, the lower 48 United States; either with a margin around it.
        """
        self.readout_label.setText(READOUT_IDLE)
        pin = self.map_view.pin
        if pin is not None:
            self.map_view.set_view(pin[0], pin[1], SINGLE_PHOTO_ZOOM)
        elif self._photo_locations:
            self.show_all_photos()
        else:
            self.map_view.fit_points(CONTIGUOUS_US_CORNERS, padding=FIT_PADDING)

    def show_new_location(self) -> None:
        pin = self.map_view.pin
        if pin is not None:
            self.map_view.set_view(pin[0], pin[1], max(self.map_view.zoom, 15))

    def _show_source_checked(self) -> None:
        satellite = self.satellite_source()
        self.satellite_button.setText(satellite.name)
        self.satellite_button.setToolTip(
            "Show Esri's satellite imagery of the whole world"
            if satellite == ESRI_SATELLITE_MAP
            else "Show aerial photos of the United States from USGS. For worldwide "
            "imagery, add a free Esri key in Edit > Settings"
        )
        on_street = self.map_view.source == STREET_MAP
        self.street_button.setChecked(on_street)
        self.satellite_button.setChecked(not on_street)
        self._update_esri_problem()

    def _build_esri_problem_banner(self) -> QFrame:
        """
        Shown when Esri's imagery doesn't load: what to do, and a button to
        switch to the US satellite map.
        """
        self.esri_problem = QFrame()
        self.esri_problem.setObjectName("mapProblem")
        layout = QHBoxLayout(self.esri_problem)
        layout.setContentsMargins(12, 8, 8, 8)
        text = QLabel(ESRI_PROBLEM_TEXT)
        text.setObjectName("mapProblemText")
        text.setWordWrap(True)
        self.use_us_satellite_button = QPushButton("Use US Satellite Instead")
        self.use_us_satellite_button.setProperty("tone", "neutral")
        self.use_us_satellite_button.setToolTip(
            "Show the USGS aerial photos (United States only) until the map is opened again"
        )
        self.use_us_satellite_button.clicked.connect(self.use_us_satellite_instead)
        layout.addWidget(text, 1)
        layout.addWidget(self.use_us_satellite_button)
        self.esri_problem.hide()
        return self.esri_problem

    def _update_esri_problem(self) -> None:
        if not hasattr(self, "esri_problem"):
            return
        showing_esri = self.map_view.source == ESRI_SATELLITE_MAP
        self.esri_problem.setVisible(showing_esri and self.map_view.has_tile_problem())

    def _update_buttons(self) -> None:
        has_photos = bool(self._photo_locations)
        self.show_photos_button.setEnabled(has_photos)
        self.show_photos_button.setToolTip(
            "Zoom the map to fit every photo in the Photo List that has GPS"
            if has_photos
            else "No photos in the Photo List have GPS"
        )
        has_pin = self.map_view.pin is not None
        if hasattr(self, "clear_button"):
            self.clear_button.setEnabled(has_pin)
            self.clear_button.setToolTip(
                "Remove the orange pin and empty New Location, to start over"
                if has_pin
                else "No location selected yet"
            )
        self.show_pin_button.setEnabled(has_pin)
        self.show_pin_button.setToolTip(
            "Move the map to the orange pin (the New Location)"
            if has_pin
            else "No location selected yet: click the map to place the pin"
        )
        if hasattr(self, "done_button"):
            # With a pin: "Select Location" (orange: what is about to change).
            # Without one there is nothing to take back: "Cancel" (neutral).
            # Either way it closes the map; New Location is already filled.
            self.done_button.setText("Select Location" if has_pin else "Cancel")
            self.done_button.setToolTip(
                "Use the orange pin as the New Location and go back to the main "
                "window, where Apply writes it (Esc)"
                if has_pin
                else "Close the map without choosing a location (Esc)"
            )
            self.done_button.setObjectName("accentButton" if has_pin else "")
            self.done_button.setProperty("tone", None if has_pin else "neutral")
            self.done_button.style().unpolish(self.done_button)
            self.done_button.style().polish(self.done_button)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # A clearer edge on Windows 11 (see gui/window_frame.py).
        apply_window_border(self)

    def closeEvent(self, event) -> None:
        # The photo preview goes with the map.
        self.preview.hide()
        super().closeEvent(event)

    def keyPressEvent(self, event) -> None:
        # Esc closes the map too (the photo preview, a popup, closes first).
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        # Ctrl+Z (Cmd+Z on macOS): Back.
        if event.matches(QKeySequence.StandardKey.Undo):
            if self.back_button.isEnabled():
                self.back_requested.emit()
            return
        super().keyPressEvent(event)

    def _zoom_to_photo(self, path: str) -> None:
        """
        Clicking the preview's thumbnail: zoom to the photo, like Go to
        Selected Location does for the pin, and keep the preview beside it.
        """
        location = self._photo_location_by_path.get(path)
        if location is None:
            return
        self.map_view.set_view(location[0], location[1], max(self.map_view.zoom, 15))
        dot = self.map_view.screen_point_for(*location).toPoint()
        self.preview.move(self.map_view.mapToGlobal(dot) + QPoint(12, 12))

    def _show_pointer_location(self, latitude: float, longitude: float) -> None:
        self.readout_label.setText(f"{latitude:.6f}, {longitude:.6f}")

    def _show_preview(self, paths: list, x: int, y: int) -> None:
        self.preview.show_photos(paths, QPoint(x, y))

    def _view_changed(self) -> None:
        self._show_source_checked()
        self.view_changed.emit()
