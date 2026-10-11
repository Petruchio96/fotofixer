import os
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QFocusEvent, QImage, QKeyEvent, QMouseEvent, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from core.map_tiles import (
    ESRI_SATELLITE_MAP,
    SATELLITE_MAP,
    STREET_MAP,
    lat_lon_to_world,
    visible_tiles,
    world_size,
    world_to_lat_lon,
    zoom_to_fit,
)
from gui.widgets.map_view import (
    OFFLINE_NOTE,
    TILE_DENIED,
    TILE_FAILED,
    TILE_LOADED,
    TILE_MISSING,
    MapView,
    PhotoPin,
    TileFetcher,
    tile_key,
)


class FakeTileFetcher(TileFetcher):
    """
    Answers every tile at once with a plain image, without the network.
    Set result to TILE_MISSING or TILE_FAILED to act like a server without
    the tile, or like being offline.
    """

    def __init__(self) -> None:
        super().__init__()
        self.requests: list[tuple[str, int, int, int]] = []
        self.api_keys: list[str] = []
        self.result = TILE_LOADED
        self._images = {}

    def fetch(self, source, zoom, x, y, api_key="") -> None:
        key = tile_key(source, zoom, x, y)
        self.requests.append(key)
        self.api_keys.append(api_key)
        if self.result == TILE_LOADED:
            image = QImage(256, 256, QImage.Format_RGB32)
            image.fill(QColor("#cfe3c8"))
            self._images[key] = image
        self.tile_finished.emit(*key, self.result)

    def take_image(self, key):
        return self._images.pop(key, None)

    def is_pending(self, key) -> bool:
        return False


def mouse_drag(widget, start: QPoint, end: QPoint) -> None:
    """Press, move with the button held, and release: a real drag."""
    QTest.mousePress(widget, Qt.LeftButton, Qt.NoModifier, start)
    for point in (start + (end - start) / 2, end):
        move = QMouseEvent(
            QEvent.MouseMove,
            QPointF(point),
            QPointF(widget.mapToGlobal(point)),
            Qt.NoButton,
            Qt.LeftButton,
            Qt.NoModifier,
        )
        QApplication.sendEvent(widget, move)
    QTest.mouseRelease(widget, Qt.LeftButton, Qt.NoModifier, end)


class MapTileMathTests(unittest.TestCase):
    def test_world_coordinates_round_trip(self) -> None:
        for latitude, longitude in ((0, 0), (40.5865, -111.6558), (-33.86, 151.21)):
            x, y = lat_lon_to_world(latitude, longitude)
            back = world_to_lat_lon(x, y)
            self.assertAlmostEqual(back[0], latitude, places=9)
            self.assertAlmostEqual(back[1], longitude, places=9)

    def test_world_middle_is_zero_zero_and_poles_are_clamped(self) -> None:
        self.assertEqual(lat_lon_to_world(0, 0), (0.5, 0.5))
        self.assertEqual(lat_lon_to_world(90, -180), (0.0, 0.0))

    def test_visible_tiles_cover_the_view_nearest_first(self) -> None:
        x, y = lat_lon_to_world(40.5865, -111.6558)
        tiles = visible_tiles(x, y, 10, 800, 600)

        center_tile = (int(x * 2**10), int(y * 2**10))
        self.assertEqual(tiles[0], center_tile)
        # 800 x 600 pixels needs 4 or 5 tiles across and 3 or 4 down.
        self.assertGreaterEqual(len(tiles), 12)
        self.assertLessEqual(len(tiles), 20)

    def test_zoom_to_fit_leaves_the_margin_on_the_tighter_side(self) -> None:
        points = [(40.58, -111.65), (40.76, -111.89)]
        center_x, center_y, zoom = zoom_to_fit(points, 800, 600, padding=0.12)
        size = world_size(zoom)

        for latitude, longitude in points:
            x, y = lat_lon_to_world(latitude, longitude)
            self.assertLessEqual(abs(x - center_x) * size, 400 * 0.76 + 1e-6)
            self.assertLessEqual(abs(y - center_y) * size, 300 * 0.76 + 1e-6)
        # Exactly fits one side: no closer zoom would leave the margin.
        world = [lat_lon_to_world(*point) for point in points]
        x_span = abs(world[0][0] - world[1][0]) * size
        y_span = abs(world[0][1] - world[1][1]) * size
        self.assertTrue(abs(x_span - 800 * 0.76) < 1e-6 or abs(y_span - 600 * 0.76) < 1e-6)

    def test_zoom_to_fit_one_point_uses_the_closest_zoom_allowed(self) -> None:
        _x, _y, zoom = zoom_to_fit([(40.58, -111.65)], 800, 600, max_zoom=15)
        self.assertEqual(zoom, 15)

    def test_satellite_tiles_use_row_then_column(self) -> None:
        self.assertTrue(SATELLITE_MAP.tile_url(5, 6, 7).endswith("/tile/5/7/6"))
        self.assertEqual(STREET_MAP.tile_url(5, 6, 7), "https://tile.openstreetmap.org/5/6/7.png")


class MapViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        # Tests click right after the window opens (and becomes active).
        activation = patch("gui.widgets.map_view.ACTIVATION_CLICK_SECONDS", 0)
        activation.start()
        self.addCleanup(activation.stop)
        self.fetcher = FakeTileFetcher()
        self.view = MapView(self.fetcher)
        self.view.resize(800, 600)
        self.view.show()
        # Clicks only count in the active window, as for a real user.
        self.view.activateWindow()
        QTest.qWaitForWindowActive(self.view)
        self.view.set_view(40.5865, -111.6558, 14)
        self.picked = []
        self.clicked = []
        self.view.location_picked.connect(lambda lat, lon: self.picked.append((lat, lon)))
        self.view.photo_pins_clicked.connect(lambda paths, x, y: self.clicked.append(paths))

    def tearDown(self) -> None:
        self.view.close()

    def test_click_moves_the_pin_and_reports_the_place(self) -> None:
        point = QPoint(200, 150)
        expected = self.view.lat_lon_at(QPointF(point))

        QTest.mouseClick(self.view, Qt.LeftButton, Qt.NoModifier, point)

        self.assertEqual(self.picked, [expected])
        self.assertEqual(self.view.pin, expected)

    def test_a_click_while_the_window_is_not_active_does_not_move_the_pin(self) -> None:
        self.view.set_pin((40.5865, -111.6558))

        self._switch_to_another_program()
        QTest.mouseClick(self.view, Qt.LeftButton, Qt.NoModifier, QPoint(200, 150))

        self.assertEqual(self.picked, [])
        self.assertEqual(self.view.pin, (40.5865, -111.6558))

    def _switch_to_another_program(self) -> QWidget:
        other = QWidget()
        self.addCleanup(other.close)
        other.show()
        other.activateWindow()
        QTest.qWaitForWindowActive(other)
        return other

    def test_while_another_program_is_active_the_map_shows_the_normal_arrow(self) -> None:
        self.view.set_photo_pins([PhotoPin("/tmp/a.jpg", 40.58, -111.64)])
        dot = self.view.screen_point_for(40.58, -111.64)

        self._switch_to_another_program()

        self.assertEqual(self.view.cursor().shape(), Qt.ArrowCursor)
        move = QMouseEvent(
            QEvent.MouseMove, dot, QPointF(self.view.mapToGlobal(dot.toPoint())),
            Qt.NoButton, Qt.NoButton, Qt.NoModifier,
        )
        QApplication.sendEvent(self.view, move)
        self.assertEqual(self.view.cursor().shape(), Qt.ArrowCursor)

        # Back in the map window: the crosshair again.
        self.view.activateWindow()
        QTest.qWaitForWindowActive(self.view)
        QApplication.sendEvent(self.view, QMouseEvent(
            QEvent.MouseMove, QPointF(300, 300), QPointF(self.view.mapToGlobal(QPoint(300, 300))),
            Qt.NoButton, Qt.NoButton, Qt.NoModifier,
        ))
        self.assertEqual(self.view.cursor().shape(), Qt.BitmapCursor)

    def test_the_window_becoming_active_is_noticed(self) -> None:
        other = QWidget()
        other.show()
        other.activateWindow()
        QTest.qWaitForWindowActive(other)
        before = time.perf_counter()

        self.view.activateWindow()
        QTest.qWaitForWindowActive(self.view)
        other.close()

        self.assertGreaterEqual(self.view._activated_at, before)

    def test_the_click_that_switches_back_to_the_window_does_not_move_the_pin(self) -> None:
        self.view.set_pin((40.5865, -111.6558))
        point = QPoint(200, 150)

        with patch("gui.widgets.map_view.ACTIVATION_CLICK_SECONDS", 0.3):
            # The window becomes active as the click arrives.
            self.view._activated_at = time.perf_counter()
            QTest.mouseClick(self.view, Qt.LeftButton, Qt.NoModifier, point)
            self.assertEqual(self.picked, [])

            # The next click (the window was already active) works.
            self.view._activated_at = time.perf_counter() - 5
            QTest.mouseClick(self.view, Qt.LeftButton, Qt.NoModifier, point)
        self.assertEqual(len(self.picked), 1)

    def test_holding_the_button_without_moving_does_not_move_the_pin(self) -> None:
        self.view.set_pin((40.5865, -111.6558))
        point = QPoint(200, 150)

        with patch("gui.widgets.map_view.time.perf_counter", side_effect=[100.0, 100.6]):
            QTest.mousePress(self.view, Qt.LeftButton, Qt.NoModifier, point)
            QTest.mouseRelease(self.view, Qt.LeftButton, Qt.NoModifier, point)

        self.assertEqual(self.picked, [])
        self.assertEqual(self.view.pin, (40.5865, -111.6558))

    def test_a_slight_wiggle_while_pressed_pans_instead_of_moving_the_pin(self) -> None:
        self.view.set_pin((40.5865, -111.6558))

        mouse_drag(self.view, QPoint(200, 150), QPoint(203, 151))

        self.assertEqual(self.picked, [])
        self.assertEqual(self.view.pin, (40.5865, -111.6558))

    def test_dragging_the_map_pans_without_moving_the_pin(self) -> None:
        self.view.set_pin((40.5865, -111.6558))
        before = self.view.center

        mouse_drag(self.view, QPoint(400, 300), QPoint(300, 250))

        self.assertEqual(self.picked, [])
        self.assertEqual(self.view.pin, (40.5865, -111.6558))
        self.assertGreater(self.view.center[1], before[1])  # moved east
        self.assertLess(self.view.center[0], before[0])  # moved south

    def test_dragging_the_pin_reports_where_it_was_dropped(self) -> None:
        self.view.set_pin((40.5865, -111.6558))
        tip = self.view.screen_point_for(40.5865, -111.6558).toPoint()
        grab = tip - QPoint(0, 20)  # on the pin's head

        mouse_drag(self.view, grab, grab + QPoint(100, 50))

        self.assertEqual(len(self.picked), 1)
        expected = self.view.lat_lon_at(QPointF(tip + QPoint(100, 50)))
        self.assertAlmostEqual(self.picked[0][0], expected[0], places=6)
        self.assertAlmostEqual(self.picked[0][1], expected[1], places=6)

    def test_clicking_the_pin_leaves_it_alone(self) -> None:
        self.view.set_pin((40.5865, -111.6558))
        tip = self.view.screen_point_for(40.5865, -111.6558).toPoint()

        QTest.mouseClick(self.view, Qt.LeftButton, Qt.NoModifier, tip - QPoint(0, 20))

        self.assertEqual(self.picked, [])

    # --- Space bar: pan mode (as in Photoshop) -------------------------------

    def _space(self, press: bool, *, repeat: bool = False) -> None:
        kind = QEvent.KeyPress if press else QEvent.KeyRelease
        QApplication.sendEvent(self.view, QKeyEvent(kind, Qt.Key_Space, Qt.NoModifier, " ", repeat))

    def test_space_shows_the_open_hand_until_released(self) -> None:
        self._space(True)
        self.assertEqual(self.view.cursor().shape(), Qt.OpenHandCursor)
        self._space(True, repeat=True)
        self._space(False, repeat=True)
        self.assertEqual(self.view.cursor().shape(), Qt.OpenHandCursor)
        self._space(False)
        self.assertNotEqual(self.view.cursor().shape(), Qt.OpenHandCursor)

    def test_with_space_a_click_does_not_move_the_pin(self) -> None:
        self._space(True)
        QTest.mouseClick(self.view, Qt.LeftButton, Qt.NoModifier, QPoint(200, 150))
        self._space(False)
        self.assertEqual(self.picked, [])
        self.assertIsNone(self.view.pin)

    def test_with_space_dragging_from_the_pin_pans_the_map(self) -> None:
        self.view.set_pin((40.5865, -111.6558))
        tip = self.view.screen_point_for(40.5865, -111.6558).toPoint()
        before = self.view.center

        self._space(True)
        mouse_drag(self.view, tip - QPoint(0, 20), tip + QPoint(-100, -70))
        self._space(False)

        self.assertEqual(self.picked, [])
        self.assertEqual(self.view.pin, (40.5865, -111.6558))
        self.assertNotEqual(self.view.center, before)

    def test_with_space_a_photo_dot_click_does_nothing(self) -> None:
        self.view.set_photo_pins([PhotoPin("/tmp/a.jpg", 40.58, -111.64)])
        dot = self.view.screen_point_for(40.58, -111.64).toPoint()
        self._space(True)
        QTest.mouseClick(self.view, Qt.LeftButton, Qt.NoModifier, dot + QPoint(3, 2))
        self.assertEqual(self.clicked, [])

    def test_losing_focus_leaves_pan_mode(self) -> None:
        self._space(True)
        QApplication.sendEvent(self.view, QFocusEvent(QEvent.FocusOut))
        QTest.mouseClick(self.view, Qt.LeftButton, Qt.NoModifier, QPoint(200, 150))
        self.assertEqual(len(self.picked), 1)

    def test_clicking_a_photo_dot_reports_the_photo_not_a_location(self) -> None:
        self.view.set_photo_pins([PhotoPin("/tmp/a.jpg", 40.58, -111.64)])
        dot = self.view.screen_point_for(40.58, -111.64).toPoint()

        QTest.mouseClick(self.view, Qt.LeftButton, Qt.NoModifier, dot + QPoint(3, 2))

        self.assertEqual(self.clicked, [["/tmp/a.jpg"]])
        self.assertEqual(self.picked, [])

    def test_nearby_but_separate_dots_are_not_combined(self) -> None:
        self.view.set_photo_pins([
            PhotoPin("/tmp/a.jpg", 40.58, -111.64),
            PhotoPin("/tmp/b.jpg", 40.58, -111.64),
        ])
        a = self.view.screen_point_for(40.58, -111.64)
        # A third photo whose dot overlaps but sits 6 px to the right.
        near = self.view.lat_lon_at(a + QPointF(6, 0))
        self.view.set_photo_pins([*self.view._photo_pins, PhotoPin("/tmp/c.jpg", *near)])

        self.assertEqual(sorted(self.view.photo_paths_at(a)), ["/tmp/a.jpg", "/tmp/b.jpg"])
        self.assertEqual(self.view.photo_paths_at(a + QPointF(6, 0)), ["/tmp/c.jpg"])
        self.assertEqual(self.view.hover_text_at(a + QPointF(6, 0)), "c.jpg")

    def test_hovering_a_dot_names_the_photos_there(self) -> None:
        pins = [PhotoPin(f"/tmp/photo-{index}.jpg", 40.58, -111.64) for index in range(8)]
        self.view.set_photo_pins(pins)
        dot = self.view.screen_point_for(40.58, -111.64)

        text = self.view.hover_text_at(dot)

        self.assertIn("photo-0.jpg", text)
        self.assertTrue(text.endswith("and 2 more"))
        self.assertEqual(self.view.hover_text_at(dot + QPointF(40, 40)), "")

    def test_zoom_in_between_levels_draws_scaled_tiles(self) -> None:
        self.fetcher.requests.clear()
        self.view.set_view(40.5865, -111.6558, 4.6)
        point = self.view.screen_point_for(40.5865, -111.6558)

        # Tiles come from the nearest whole level, and positions stay exact.
        self.assertEqual({key[1] for key in self.fetcher.requests}, {5})
        self.assertAlmostEqual(point.x(), 400, places=6)
        self.assertAlmostEqual(point.y(), 300, places=6)

    def test_the_pointer_is_a_crosshair_and_its_place_is_reported(self) -> None:
        moved = []
        self.view.pointer_moved.connect(lambda lat, lon: moved.append((lat, lon)))
        point = QPoint(250, 180)

        QTest.mouseMove(self.view, point)

        self.assertEqual(self.view.cursor().shape(), Qt.BitmapCursor)
        self.assertEqual(moved[-1], self.view.lat_lon_at(QPointF(point)))

    def test_the_crosshair_clicks_at_its_center(self) -> None:
        cursor = self.view.cursor()
        pixmap = cursor.pixmap()
        hot_spot = cursor.hotSpot() * pixmap.devicePixelRatio()

        self.assertAlmostEqual(hot_spot.x(), pixmap.width() / 2, delta=1)
        self.assertAlmostEqual(hot_spot.y(), pixmap.height() / 2, delta=1)

    def test_pressing_the_map_shows_the_closed_hand_at_once(self) -> None:
        point = QPoint(300, 200)

        QTest.mousePress(self.view, Qt.LeftButton, Qt.NoModifier, point)
        self.assertEqual(self.view.cursor().shape(), Qt.ClosedHandCursor)

        QTest.mouseRelease(self.view, Qt.LeftButton, Qt.NoModifier, point)
        self.assertEqual(self.view.cursor().shape(), Qt.BitmapCursor)  # the crosshair
        self.assertEqual(len(self.picked), 1)  # still a click: the pin moved

    def test_pressing_a_photo_dot_keeps_the_pointing_hand(self) -> None:
        self.view.set_photo_pins([PhotoPin("/tmp/a.jpg", 40.58, -111.64)])
        dot = self.view.screen_point_for(40.58, -111.64).toPoint()
        QTest.mouseMove(self.view, dot)

        QTest.mousePress(self.view, Qt.LeftButton, Qt.NoModifier, dot)

        self.assertEqual(self.view.cursor().shape(), Qt.PointingHandCursor)
        QTest.mouseRelease(self.view, Qt.LeftButton, Qt.NoModifier, dot)

    def test_the_pointer_is_a_hand_over_a_photo_dot(self) -> None:
        self.view.set_photo_pins([PhotoPin("/tmp/a.jpg", 40.58, -111.64)])
        dot = self.view.screen_point_for(40.58, -111.64).toPoint()

        QTest.mouseMove(self.view, dot)
        self.assertEqual(self.view.cursor().shape(), Qt.PointingHandCursor)

        QTest.mouseMove(self.view, dot + QPoint(60, 60))
        self.assertEqual(self.view.cursor().shape(), Qt.BitmapCursor)

    def test_wheel_zoom_keeps_the_place_under_the_mouse(self) -> None:
        point = QPointF(600, 150)
        before = self.view.lat_lon_at(point)
        wheel = QWheelEvent(
            point,
            QPointF(self.view.mapToGlobal(point.toPoint())),
            QPoint(),
            QPoint(0, 120),
            Qt.NoButton,
            Qt.NoModifier,
            Qt.NoScrollPhase,
            False,
        )
        QApplication.sendEvent(self.view, wheel)

        self.assertEqual(self.view.zoom, 15)
        after = self.view.lat_lon_at(point)
        self.assertAlmostEqual(after[0], before[0], places=6)
        self.assertAlmostEqual(after[1], before[1], places=6)

    def test_set_pin_with_reveal_moves_the_map_only_when_out_of_view(self) -> None:
        center = self.view.center
        self.view.set_pin((40.587, -111.655), reveal=True)
        self.assertEqual(self.view.center, center)

        self.view.set_pin((37.77, -122.42), reveal=True)
        self.assertTrue(self.view.is_visible_on_map(37.77, -122.42))
        self.assertEqual(self.view.zoom, 14)

    def test_satellite_zoomed_past_its_detail_enlarges_level_16_tiles(self) -> None:
        self.view.set_source(SATELLITE_MAP)
        self.fetcher.requests.clear()

        self.view.set_view(40.5865, -111.6558, 18)

        self.assertTrue(self.fetcher.requests)
        self.assertEqual({key[1] for key in self.fetcher.requests}, {16})

    def test_offline_tiles_show_a_note(self) -> None:
        self.fetcher.result = TILE_FAILED
        self.view.set_view(10, 10, 6)

        self.assertEqual(self.view.notes(), [OFFLINE_NOTE])

    def test_satellite_outside_the_united_states_says_so(self) -> None:
        self.fetcher.result = TILE_MISSING
        self.view.set_source(SATELLITE_MAP)
        self.view.set_view(48.85, 2.35, 10)

        self.assertEqual(self.view.notes(), [SATELLITE_MAP.coverage_note])

    def test_esri_without_a_key_downloads_nothing(self) -> None:
        self.fetcher.requests.clear()

        self.view.set_source(ESRI_SATELLITE_MAP)

        self.assertEqual(self.fetcher.requests, [])
        self.assertTrue(self.view.has_tile_problem())

    def test_esri_tiles_are_downloaded_with_the_key(self) -> None:
        self.view.set_api_key("esri", "my-key")
        self.view.set_source(ESRI_SATELLITE_MAP)
        self.fetcher.requests.clear()
        self.fetcher.api_keys.clear()

        self.view.set_view(40.5865, -111.6558, 19)

        self.assertEqual({key[1] for key in self.fetcher.requests}, {19})
        self.assertEqual(set(self.fetcher.api_keys), {"my-key"})
        self.assertEqual(self.view.notes(), [])

    def test_esri_tile_address_carries_the_key_safely_encoded(self) -> None:
        url = ESRI_SATELLITE_MAP.tile_url(5, 6, 7, "a+b/c..d")

        self.assertTrue(url.startswith("https://ibasemaps-api.arcgis.com/"))
        self.assertIn("/tile/5/7/6?token=a%2Bb%2Fc..d", url)

    def test_a_refused_key_says_so_and_a_new_key_tries_again(self) -> None:
        self.fetcher.result = TILE_DENIED
        self.view.set_api_key("esri", "bad-key")
        self.view.set_source(ESRI_SATELLITE_MAP)
        self.assertTrue(self.view.has_tile_problem())
        # The map window shows its own banner, not a note on the map.
        self.assertEqual(self.view.notes(), [])

        self.fetcher.result = TILE_LOADED
        self.fetcher.requests.clear()
        self.view.set_api_key("esri", "good-key")

        self.assertTrue(self.fetcher.requests)
        self.assertFalse(self.view.has_tile_problem())

    def test_loaded_tiles_are_not_downloaded_again(self) -> None:
        self.fetcher.requests.clear()
        self.view.zoom_by(1)
        self.view.zoom_by(-1)
        requests_after_return = list(self.fetcher.requests)

        self.view.zoom_by(1)

        self.assertEqual(self.fetcher.requests, requests_after_return)


if __name__ == "__main__":
    unittest.main()
