"""
"Pick from a Map": the pop-out map window as a source for New Location.

No new write path: the map only fills the latitude/longitude fields (like
typing or pasting), and Apply writes them as usual. Whatever is in the fields
shows as the pin. The map opens on the street map, centered on the photos
with GPS (or the United States); the window remembers its size and position.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtGui import QIcon

from gui.widgets.map_view import NetworkTileFetcher, PhotoPin, TileFetcher
from gui.widgets.map_window import MapWindow
from services.coordinate_service import parse_manual_coordinates

# QSettings keys: the map window's size and position, and the user's own
# ArcGIS API key for Esri Satellite (saved in plain text, like the other
# settings).
MAP_GEOMETRY_SETTING = "map/geometry"
ESRI_KEY_SETTING = "map/esri_api_key"


class MapPickerMixin:
    _map_window: MapWindow | None = None
    # The pin last given to the map, to notice when New Location changes.
    _map_pin_shown: tuple[float, float] | None = None
    # For the map's Back button: New Location (latitude text, longitude text,
    # source photo) before each change made on the map, newest last.
    # Emptied each time the map opens.
    _map_location_history: list[tuple[str, str, Path | None]] = []

    def show_map(self) -> None:
        """
        Open the map window, centered on New Location when one is set, else on
        the photos in the Photo List with GPS (or the United States), or bring
        it to the front if it is open.
        """
        if self._map_window is None:
            self._map_window = self._build_map_window()
            geometry = self.settings.value(MAP_GEOMETRY_SETTING)
            if geometry is not None:
                self._map_window.restoreGeometry(geometry)
        opening = not self._map_window.isVisible()
        if opening:
            # Always opens on the street map, with Satellite back to Esri
            # if a key is set (after "Use US Satellite Instead" last time).
            self._map_window.reset_for_opening()
        self._map_window.show()
        if opening:
            # The pin counts as already shown: opening centers on it
            # (show_photos_or_united_states), so it needn't be revealed.
            self._map_pin_shown = self._new_location_pin()
            self._map_location_history = []
            self._map_window.set_back_enabled(False)
            self._refresh_map()
            # Fitted once shown, so the map has its real size.
            self._map_window.show_photos_or_united_states()
        self._map_window.raise_()
        self._map_window.activateWindow()
        self._apply_pick_mode_lock()

    def _create_tile_fetcher(self) -> TileFetcher:
        """
        The tile downloader. Tests replace this so they never use the network.
        """
        cache_root = QStandardPaths.writableLocation(QStandardPaths.CacheLocation)
        return NetworkTileFetcher(
            user_agent=(
                f"PhotoGPSEditor/{self.app_version} "
                "(+https://github.com/Petruchio96/photo-gps-editor)"
            ),
            cache_directory=Path(cache_root) / "map-tiles",
            parent=self,
        )

    def _build_map_window(self) -> MapWindow:
        window = MapWindow(self, fetcher=self._create_tile_fetcher(), icon_for=self._map_photo_icon)
        window.location_picked.connect(self._use_map_location)
        window.use_photo_location.connect(self._use_map_photo_location)
        window.clear_requested.connect(self._clear_map_location)
        window.back_requested.connect(self._map_go_back)
        window.set_esri_key(self.settings.value(ESRI_KEY_SETTING, "", type=str))
        return window

    def set_esri_key(self, api_key: str) -> None:
        """
        Save (or with "", remove) the user's ArcGIS key from Settings, and
        give it to the map: Satellite is Esri with a key, USGS without.
        """
        if api_key:
            self.settings.setValue(ESRI_KEY_SETTING, api_key)
        else:
            self.settings.remove(ESRI_KEY_SETTING)
        if self._map_window is not None:
            self._map_window.set_esri_key(api_key)

    def _close_map_window(self) -> None:
        if self._map_window is not None:
            self.settings.setValue(MAP_GEOMETRY_SETTING, self._map_window.saveGeometry())
            self._map_window.close()

    def _use_map_location(self, latitude: float, longitude: float) -> None:
        """
        A click or a dropped pin on the map: fill New Location, the same
        as typing coordinates (any location source photo is dropped).
        """
        self._remember_location_for_back()
        self._map_pin_shown = (round(latitude, 6), round(longitude, 6))
        self.set_location_fields(f"{latitude:.6f}", f"{longitude:.6f}")

    def _use_map_photo_location(self, path_text: str) -> None:
        """
        Use This Location in a photo's preview on the map.
        """
        self._remember_location_for_back()
        self.use_location_from_path(Path(path_text))

    def _clear_map_location(self) -> None:
        """
        The map's Clear: empty New Location (Back can bring it back).
        """
        if self.latitude_input.text() or self.longitude_input.text():
            self._remember_location_for_back()
        self.clear_location_fields()

    def _remember_location_for_back(self) -> None:
        self._map_location_history.append(
            (self.latitude_input.text(), self.longitude_input.text(), self._location_source)
        )
        self._map_window.set_back_enabled(True)

    def _map_go_back(self) -> None:
        """
        The map's Back: put New Location back to what it was before the last
        change made on the map (and its source photo, if it had one).
        """
        if not self._map_location_history:
            return
        latitude, longitude, source = self._map_location_history.pop()
        self.set_location_fields(latitude, longitude, source=source)
        self._map_window.set_back_enabled(bool(self._map_location_history))

    def _map_photo_icon(self, path: Path) -> QIcon:
        item = self._grid_items_by_path.get(str(path))
        if item is not None:
            return item.icon()
        return self.thumbnail_loader.load_icon(path, has_gps=True)

    def _new_location_pin(self) -> tuple[float, float] | None:
        pin = parse_manual_coordinates(self.latitude_input.text(), self.longitude_input.text())
        return (round(pin[0], 6), round(pin[1], 6)) if pin is not None else None

    def _refresh_map(self) -> None:
        """
        Show the New Location as the pin, and the photos in the Photo List
        with GPS as dots. Runs whenever the details panel updates.
        """
        window = self._map_window
        if window is None:
            return

        pin = self._new_location_pin()
        # Move the map to a new location only when it changed (typed, pasted,
        # copied from a photo) and is out of view.
        changed = pin != self._map_pin_shown
        self._map_pin_shown = pin
        window.set_pin(pin, reveal=changed)

        selected = {str(path) for path in self.get_selected_paths()}
        pins = []
        for path in self.session.selected_paths:
            info = self.session.loaded_photo_infos.get(path)
            if info is None or info.current_latitude is None or info.current_longitude is None:
                continue
            pins.append(
                PhotoPin(
                    path=str(path),
                    latitude=info.current_latitude,
                    longitude=info.current_longitude,
                    selected=str(path) in selected,
                )
            )
        window.set_photo_pins(pins)
