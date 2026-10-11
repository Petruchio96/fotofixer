import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, QSettings, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from gui.main_window import MainWindow
from core.map_tiles import CONTIGUOUS_US_CORNERS
from gui.widgets.map_window import READOUT_IDLE
from services.workflow_facade import PhotoWorkflowFacade
from test_main_window_smoke import FakeExifTool, FakePhotoLoader, FakeThumbnailLoader
from gui.widgets.map_view import TILE_DENIED, TILE_LOADED
from test_map_view import FakeTileFetcher


class MapWindowTests(unittest.TestCase):
    """
    "Pick from a Map" through the main window, with real mouse clicks on the
    map. Tiles come from a fake, so these never use the network.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        # Tests click right after the map opens (and becomes active).
        activation = patch("gui.widgets.map_view.ACTIVATION_CLICK_SECONDS", 0)
        activation.start()
        self.addCleanup(activation.stop)
        settings_dir = tempfile.TemporaryDirectory()
        self.addCleanup(settings_dir.cleanup)
        self.settings = QSettings(str(Path(settings_dir.name) / "settings.ini"), QSettings.IniFormat)

        self.with_gps = Path("/tmp/map-alta.jpg")
        self.with_gps_too = Path("/tmp/map-brighton.jpg")
        self.without_gps = Path("/tmp/map-none.jpg")
        self.gps_by_path = {
            self.with_gps: (40.5865, -111.6558),
            self.with_gps_too: (40.5980, -111.5833),
            self.without_gps: (None, None),
        }
        self.window = self._open_window()

    def _open_window(self) -> MainWindow:
        window = MainWindow(settings=self.settings)
        window.background.run_inline = True
        window._create_tile_fetcher = FakeTileFetcher
        window.show()
        window.exiftool = FakeExifTool(self.gps_by_path)
        window.loader = FakePhotoLoader(self.gps_by_path)
        window.workflow = PhotoWorkflowFacade(loader=window.loader, writer=window.exiftool)
        window.thumbnail_loader = FakeThumbnailLoader()
        window.load_photos(list(self.gps_by_path))
        self.addCleanup(window.close)
        return window

    def _open_map(self, window: MainWindow | None = None):
        window = window or self.window
        QTest.mouseClick(window.show_map_button, Qt.LeftButton)
        # Clicks on the map only count in the active window.
        QTest.qWaitForWindowActive(window._map_window)
        return window._map_window

    def _fields(self) -> tuple[str, str]:
        return self.window.latitude_input.text(), self.window.longitude_input.text()

    def test_pick_on_the_map_opens_the_map_with_photo_dots(self) -> None:
        map_window = self._open_map()

        self.assertTrue(map_window.isVisible())
        dots = {pin.path for pin in map_window.map_view._photo_pins}
        self.assertEqual(dots, {str(self.with_gps), str(self.with_gps_too)})

    def _assert_shown_with_margin(self, map_view, points) -> None:
        """Every point is in view, at least 10% in from every edge."""
        for point in points:
            screen = map_view.screen_point_for(*point)
            self.assertGreaterEqual(screen.x(), map_view.width() * 0.1)
            self.assertLessEqual(screen.x(), map_view.width() * 0.9)
            self.assertGreaterEqual(screen.y(), map_view.height() * 0.1)
            self.assertLessEqual(screen.y(), map_view.height() * 0.9)

    def test_opens_centered_on_the_photos_with_gps(self) -> None:
        map_window = self._open_map()

        locations = [self.gps_by_path[self.with_gps], self.gps_by_path[self.with_gps_too]]
        self._assert_shown_with_margin(map_window.map_view, locations)
        center = map_window.map_view.center
        self.assertAlmostEqual(center[1], (locations[0][1] + locations[1][1]) / 2, places=6)

    def test_opens_on_the_united_states_without_photos_with_gps(self) -> None:
        self.window.clear_photo_list()
        self.window.load_photos([self.without_gps])

        map_window = self._open_map()

        self._assert_shown_with_margin(map_window.map_view, CONTIGUOUS_US_CORNERS)
        self.assertLess(map_window.map_view.zoom, 5)

    def test_reopening_the_map_centers_on_the_photos_again(self) -> None:
        map_window = self._open_map()
        map_window.map_view.set_view(51.5, -0.12, 10)
        map_window.close()

        map_window = self._open_map()

        self.assertTrue(map_window.map_view.is_visible_on_map(*self.gps_by_path[self.with_gps]))

    def test_opening_centers_on_new_location_when_set(self) -> None:
        self.window.set_location_fields("37.774900", "-122.419400")

        map_window = self._open_map()

        self.assertEqual(map_window.map_view.pin, (37.7749, -122.4194))
        self.assertTrue(map_window.map_view.is_visible_on_map(37.7749, -122.4194))
        self.assertEqual(map_window.map_view.zoom, 15)
        self.assertFalse(map_window.map_view.is_visible_on_map(*self.gps_by_path[self.with_gps]))

    def test_readout_shows_the_coordinates_under_the_mouse(self) -> None:
        map_window = self._open_map()
        point = QPoint(320, 240)
        latitude, longitude = map_window.map_view.lat_lon_at(QPointF(point))

        # Sent straight to the map: offscreen, QTest.mouseMove doesn't reach
        # the map window here once it has been activated.
        move = QMouseEvent(
            QEvent.MouseMove,
            QPointF(point),
            QPointF(map_window.map_view.mapToGlobal(point)),
            Qt.NoButton,
            Qt.NoButton,
            Qt.NoModifier,
        )
        QApplication.sendEvent(map_window.map_view, move)

        self.assertEqual(map_window.readout_label.text(), f"{latitude:.6f}, {longitude:.6f}")
        map_window.map_view.pointer_left.emit()
        self.assertEqual(map_window.readout_label.text(), READOUT_IDLE)

    def test_clicking_the_map_fills_new_location(self) -> None:
        map_window = self._open_map()
        self.window.select_browser_paths([self.without_gps])
        point = QPoint(300, 200)
        expected = map_window.map_view.lat_lon_at(QPointF(point))

        QTest.mouseClick(map_window.map_view, Qt.LeftButton, Qt.NoModifier, point)

        self.assertEqual(self._fields(), (f"{expected[0]:.6f}", f"{expected[1]:.6f}"))
        self.assertTrue(self.window.apply_button.isEnabled())
        self.assertEqual(self.window.apply_button.text(), "Apply Location to 1 Photo")

    def test_close_button_is_cancel_until_a_location_is_selected(self) -> None:
        map_window = self._open_map()
        button = map_window.done_button
        self.assertEqual(button.text(), "Cancel")

        QTest.mouseClick(map_window.map_view, Qt.LeftButton, Qt.NoModifier, QPoint(300, 200))
        self.assertEqual(button.text(), "Select Location")
        self.assertEqual(button.objectName(), "accentButton")

        QTest.mouseClick(map_window.clear_button, Qt.LeftButton)
        self.assertEqual(button.text(), "Cancel")

    def test_map_location_replaces_a_location_source_photo(self) -> None:
        map_window = self._open_map()
        self.window.use_location_from_path(self.with_gps)
        self.assertIsNotNone(self.window._location_source)

        QTest.mouseClick(map_window.map_view, Qt.LeftButton, Qt.NoModifier, QPoint(300, 200))

        self.assertIsNone(self.window._location_source)
        self.assertFalse(self.window.source_card.isVisible())

    def test_apply_writes_the_location_picked_on_the_map(self) -> None:
        map_window = self._open_map()
        self.window.select_browser_paths([self.without_gps])
        QTest.mouseClick(map_window.map_view, Qt.LeftButton, Qt.NoModifier, QPoint(300, 200))
        latitude, longitude = (float(text) for text in self._fields())

        self.window.apply_coordinates_to_selected()

        self.assertEqual(self.window.exiftool.writes, [(self.without_gps, latitude, longitude)])

    def test_apply_never_writes_to_the_source_photo(self) -> None:
        self.window.use_location_from_path(self.with_gps)

        # Only the source selected: nothing to apply to.
        self.window.select_browser_paths([self.with_gps])
        self.assertFalse(self.window.apply_button.isEnabled())
        self.window.apply_coordinates_to_selected()
        self.assertEqual(self.window.exiftool.writes, [])

        # With another photo selected, only that photo is changed.
        self.window.select_browser_paths([self.with_gps, self.without_gps])
        self.assertTrue(self.window.apply_button.isEnabled())
        self.assertEqual(self.window.apply_button.text(), "Apply Location to 1 Photo")
        self.window.apply_coordinates_to_selected()
        self.assertEqual(self.window.exiftool.writes, [(self.without_gps, 40.5865, -111.6558)])

    def test_pin_follows_coordinates_typed_or_pasted(self) -> None:
        map_window = self._open_map()

        self.window.set_location_fields("37.774900", "-122.419400")

        self.assertEqual(map_window.map_view.pin, (37.7749, -122.4194))
        # San Francisco was out of view, so the map went there.
        self.assertTrue(map_window.map_view.is_visible_on_map(37.7749, -122.4194))

        self.window.clear_location_fields()
        self.assertIsNone(map_window.map_view.pin)

    def test_selected_photos_are_marked_on_the_map(self) -> None:
        map_window = self._open_map()

        self.window.select_browser_paths([self.with_gps])

        selected = {pin.path: pin.selected for pin in map_window.map_view._photo_pins}
        self.assertEqual(selected, {str(self.with_gps): True, str(self.with_gps_too): False})

    def test_clicking_a_photo_dot_shows_its_preview(self) -> None:
        map_window = self._open_map()
        dot = map_window.map_view.screen_point_for(*self.gps_by_path[self.with_gps]).toPoint()

        QTest.mouseClick(map_window.map_view, Qt.LeftButton, Qt.NoModifier, dot)

        self.assertTrue(map_window.preview.isVisible())
        self.assertEqual(map_window.preview.name_label.text(), self.with_gps.name)
        # Clicking a photo does not change New Location.
        self.assertEqual(self._fields(), ("", ""))

    def test_hovering_a_photo_dot_shows_its_file_name(self) -> None:
        map_window = self._open_map()
        dot = map_window.map_view.screen_point_for(*self.gps_by_path[self.with_gps_too])

        self.assertEqual(map_window.map_view.hover_text_at(dot), self.with_gps_too.name)

    def test_use_this_location_in_the_preview_makes_the_photo_the_source(self) -> None:
        map_window = self._open_map()
        dot = map_window.map_view.screen_point_for(*self.gps_by_path[self.with_gps]).toPoint()
        QTest.mouseClick(map_window.map_view, Qt.LeftButton, Qt.NoModifier, dot)

        QTest.mouseClick(map_window.preview.use_button, Qt.LeftButton)

        self.assertEqual(self.window._location_source, self.with_gps)
        self.assertEqual(self._fields(), ("40.586500", "-111.655800"))
        self.assertFalse(map_window.preview.isVisible())

    def test_map_always_opens_on_the_street_map(self) -> None:
        map_window = self._open_map()
        QTest.mouseClick(map_window.satellite_button, Qt.LeftButton)
        self.assertEqual(map_window.map_view.source.key, "satellite")
        map_window.close()

        reopened = self._open_map()

        self.assertEqual(reopened.map_view.source.key, "street")
        self.assertTrue(reopened.street_button.isChecked())

    def test_map_is_off_while_picking_from_the_photo_list(self) -> None:
        map_window = self._open_map()

        self.window.start_picking_location()
        self.assertFalse(map_window.isEnabled())
        self.assertFalse(self.window.show_map_button.isEnabled())

        self.window.stop_picking_location()
        self.assertTrue(map_window.isEnabled())
        self.assertTrue(self.window.show_map_button.isEnabled())

    def test_clear_removes_the_pin_and_empties_new_location(self) -> None:
        map_window = self._open_map()
        self.assertFalse(map_window.clear_button.isEnabled())
        QTest.mouseClick(map_window.map_view, Qt.LeftButton, Qt.NoModifier, QPoint(300, 200))
        self.assertTrue(map_window.clear_button.isEnabled())

        QTest.mouseClick(map_window.clear_button, Qt.LeftButton)

        self.assertEqual(self._fields(), ("", ""))
        self.assertIsNone(map_window.map_view.pin)
        self.assertFalse(map_window.clear_button.isEnabled())
        # Still open, ready for a new click.
        self.assertTrue(map_window.isVisible())

    def _click_map(self, map_window, point: QPoint) -> tuple[str, str]:
        QTest.mouseClick(map_window.map_view, Qt.LeftButton, Qt.NoModifier, point)
        return self._fields()

    def test_back_steps_through_the_locations_set_on_the_map(self) -> None:
        map_window = self._open_map()
        self.assertFalse(map_window.back_button.isEnabled())
        first = self._click_map(map_window, QPoint(300, 200))
        self._click_map(map_window, QPoint(500, 300))

        QTest.mouseClick(map_window.back_button, Qt.LeftButton)
        self.assertEqual(self._fields(), first)
        self.assertTrue(map_window.back_button.isEnabled())

        QTest.mouseClick(map_window.back_button, Qt.LeftButton)
        self.assertEqual(self._fields(), ("", ""))
        self.assertIsNone(map_window.map_view.pin)
        self.assertFalse(map_window.back_button.isEnabled())

    def test_back_undoes_clear(self) -> None:
        map_window = self._open_map()
        placed = self._click_map(map_window, QPoint(300, 200))
        QTest.mouseClick(map_window.clear_button, Qt.LeftButton)

        QTest.mouseClick(map_window.back_button, Qt.LeftButton)

        self.assertEqual(self._fields(), placed)
        self.assertIsNotNone(map_window.map_view.pin)

    def test_back_brings_back_a_source_photo(self) -> None:
        map_window = self._open_map()
        dot = map_window.map_view.screen_point_for(*self.gps_by_path[self.with_gps]).toPoint()
        QTest.mouseClick(map_window.map_view, Qt.LeftButton, Qt.NoModifier, dot)
        QTest.mouseClick(map_window.preview.use_button, Qt.LeftButton)
        self.assertEqual(self.window._location_source, self.with_gps)
        self._click_map(map_window, QPoint(500, 300))
        self.assertIsNone(self.window._location_source)

        QTest.mouseClick(map_window.back_button, Qt.LeftButton)

        self.assertEqual(self.window._location_source, self.with_gps)
        self.assertEqual(self._fields(), ("40.586500", "-111.655800"))

    def test_ctrl_z_in_the_map_is_back(self) -> None:
        map_window = self._open_map()
        first = self._click_map(map_window, QPoint(300, 200))
        self._click_map(map_window, QPoint(500, 300))

        QTest.keyClick(map_window, Qt.Key_Z, Qt.ControlModifier)

        self.assertEqual(self._fields(), first)

    def test_back_starts_empty_each_time_the_map_opens(self) -> None:
        map_window = self._open_map()
        self._click_map(map_window, QPoint(300, 200))
        QTest.mouseClick(map_window.done_button, Qt.LeftButton)

        map_window = self._open_map()

        self.assertFalse(map_window.back_button.isEnabled())

    def test_clicking_the_preview_thumbnail_zooms_to_the_photo(self) -> None:
        map_window = self._open_map()
        location = self.gps_by_path[self.with_gps]
        dot = map_window.map_view.screen_point_for(*location).toPoint()
        QTest.mouseClick(map_window.map_view, Qt.LeftButton, Qt.NoModifier, dot)

        QTest.mouseClick(map_window.preview.thumbnail_button, Qt.LeftButton)

        view = map_window.map_view
        self.assertGreaterEqual(view.zoom, 15)
        center = view.screen_point_for(*location)
        self.assertAlmostEqual(center.x(), view.width() / 2, delta=1)
        self.assertAlmostEqual(center.y(), view.height() / 2, delta=1)
        # The preview stays open, beside the photo's dot.
        self.assertTrue(map_window.preview.isVisible())
        expected = view.mapToGlobal(center.toPoint()) + QPoint(12, 12)
        self.assertEqual(map_window.preview.pos(), expected)
        # Zooming doesn't change New Location.
        self.assertEqual(self._fields(), ("", ""))

    def test_map_blocks_the_main_window_until_done(self) -> None:
        map_window = self._open_map()

        self.assertEqual(map_window.windowModality(), Qt.ApplicationModal)
        self.assertIs(QApplication.activeModalWidget(), map_window)

        QTest.mouseClick(map_window.done_button, Qt.LeftButton)

        self.assertFalse(map_window.isVisible())
        self.assertIsNone(QApplication.activeModalWidget())

    def test_escape_closes_the_map(self) -> None:
        map_window = self._open_map()
        map_window.activateWindow()

        QTest.keyClick(map_window, Qt.Key_Escape)

        self.assertFalse(map_window.isVisible())

    # --- Satellite: Esri with a key from Settings, USGS without ----------------

    def _save_esri_key_in_settings(self, key: str) -> None:
        self.window.open_settings()
        dialog = self.window._settings_dialog
        self.addCleanup(dialog.close)
        dialog.esri_key_input.setText(key)
        QTest.mouseClick(dialog.save_button, Qt.LeftButton)

    def test_without_a_key_the_satellite_button_is_us_satellite(self) -> None:
        map_window = self._open_map()

        self.assertEqual(map_window.satellite_button.text(), "US Satellite")
        QTest.mouseClick(map_window.satellite_button, Qt.LeftButton)

        self.assertEqual(map_window.map_view.source.key, "satellite")
        self.assertTrue(map_window.satellite_button.isChecked())
        self.assertFalse(map_window.street_button.isChecked())

    def test_with_a_key_the_satellite_button_shows_esri(self) -> None:
        self._save_esri_key_in_settings("  my-arcgis-key  ")
        self.assertEqual(self.settings.value("map/esri_api_key"), "my-arcgis-key")

        map_window = self._open_map()
        self.assertEqual(map_window.satellite_button.text(), "Satellite")
        QTest.mouseClick(map_window.satellite_button, Qt.LeftButton)

        self.assertEqual(map_window.map_view.source.key, "esri")
        self.assertIn("my-arcgis-key", map_window.map_view._fetcher.api_keys)
        self.assertFalse(map_window.esri_problem.isVisible())

    def test_removing_the_key_in_settings_goes_back_to_us_satellite(self) -> None:
        self._save_esri_key_in_settings("my-arcgis-key")
        map_window = self._open_map()
        QTest.mouseClick(map_window.satellite_button, Qt.LeftButton)
        QTest.mouseClick(map_window.done_button, Qt.LeftButton)

        self.window.open_settings()
        dialog = self.window._settings_dialog
        self.addCleanup(dialog.close)
        self.assertEqual(dialog.esri_key_input.text(), "my-arcgis-key")
        QTest.mouseClick(dialog.remove_key_button, Qt.LeftButton)
        QTest.mouseClick(dialog.save_button, Qt.LeftButton)

        self.assertIsNone(self.settings.value("map/esri_api_key"))
        map_window = self._open_map()
        self.assertEqual(map_window.satellite_button.text(), "US Satellite")

    def test_esri_trouble_offers_the_us_satellite_map(self) -> None:
        self._save_esri_key_in_settings("my-arcgis-key")
        map_window = self._open_map()
        map_window.map_view._fetcher.result = TILE_DENIED

        QTest.mouseClick(map_window.satellite_button, Qt.LeftButton)

        self.assertTrue(map_window.esri_problem.isVisible())
        self.assertIn("Edit > Settings", map_window.esri_problem.findChild(QLabel).text())

        map_window.map_view._fetcher.result = TILE_LOADED
        QTest.mouseClick(map_window.use_us_satellite_button, Qt.LeftButton)

        self.assertEqual(map_window.map_view.source.key, "satellite")
        self.assertEqual(map_window.satellite_button.text(), "US Satellite")
        self.assertTrue(map_window.satellite_button.isChecked())
        self.assertFalse(map_window.esri_problem.isVisible())

        # Opening the map again goes back to trying Esri.
        map_window.close()
        reopened = self._open_map()
        self.assertEqual(reopened.satellite_button.text(), "Satellite")

    def test_several_photos_at_one_spot_step_with_arrows_beside_the_count(self) -> None:
        self.gps_by_path[self.with_gps_too] = self.gps_by_path[self.with_gps]
        self.window.close()
        window = self._open_window()
        map_window = self._open_map(window)
        dot = map_window.map_view.screen_point_for(*self.gps_by_path[self.with_gps]).toPoint()

        QTest.mouseClick(map_window.map_view, Qt.LeftButton, Qt.NoModifier, dot)

        preview = map_window.preview
        self.assertEqual(preview.count_label.text(), "1 of 2")
        self.assertEqual((preview.previous_button.text(), preview.next_button.text()), ("<", ">"))
        # The arrows sit right beside the count: "< 1 of 2 >".
        count = preview.count_label.geometry()
        self.assertLess(count.left() - preview.previous_button.geometry().right(), 12)
        self.assertLess(preview.next_button.geometry().left() - count.right(), 12)
        first = preview.name_label.text()
        QTest.mouseClick(preview.next_button, Qt.LeftButton)
        self.assertEqual(preview.count_label.text(), "2 of 2")
        self.assertNotEqual(preview.name_label.text(), first)

    def test_every_map_button_has_a_hover_hint(self) -> None:
        map_window = self._open_map()

        missing = [
            button.text() or button.objectName()
            for button in map_window.findChildren(QPushButton)
            if not button.toolTip()
        ]
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
