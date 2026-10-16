import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from core.models import PhotoInfo
from gui.main_window import MainWindow
from gui.presenters.date_time_state import MODE_SHIFT
from gui.widgets.editor_panel import DATE_TIME_TAB
from gui.widgets.geotag_window import PHOTO_ZOOM, READOUT_IDLE
from gui.widgets.map_view import LEFT_OUT_PHOTO_COLOR, PHOTO_COLOR, REPLACE_RING_COLOR, SELECTED_PHOTO_COLOR
from services.geotag_service import AFTER, BEFORE, GAP, NO_DATE, ON_TRACK
from services.workflow_facade import PhotoWorkflowFacade
from test_map_view import FakeTileFetcher

MDT = timedelta(hours=-6)

# A track from 15:12 to 15:42 UTC (9:12 to 9:42 MDT), a two-hour pause, then 17:42 to 17:52.
GPX = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>
<trkpt lat="40.60" lon="-111.60"><ele>2000</ele><time>2026-10-03T15:12:00Z</time></trkpt>
<trkpt lat="40.61" lon="-111.59"><ele>2100</ele><time>2026-10-03T15:22:00Z</time></trkpt>
<trkpt lat="40.62" lon="-111.58"><ele>2200</ele><time>2026-10-03T15:32:00Z</time></trkpt>
<trkpt lat="40.63" lon="-111.57"><ele>2300</ele><time>2026-10-03T15:42:00Z</time></trkpt>
</trkseg><trkseg>
<trkpt lat="40.70" lon="-111.50"><ele>2600</ele><time>2026-10-03T17:42:00Z</time></trkpt>
<trkpt lat="40.71" lon="-111.49"><ele>2700</ele><time>2026-10-03T17:52:00Z</time></trkpt>
</trkseg></trk></gpx>
"""


class FakeGeotagWriter:
    """Records GPS writes with their altitude; keeps each photo's GPS for the loader."""

    def __init__(self, gps_by_path: dict[Path, tuple]) -> None:
        self.gps_by_path = gps_by_path
        self.writes: list[tuple] = []
        self.clears: list[Path] = []
        self.failures: dict[Path, Exception] = {}

    def write_gps(self, path: Path, latitude: float, longitude: float, altitude: float | None = None) -> None:
        if path in self.failures:
            raise self.failures[path]
        self.writes.append((path, latitude, longitude, altitude))
        self.gps_by_path[path] = (latitude, longitude)

    def clear_gps(self, path: Path) -> None:
        self.clears.append(path)
        self.gps_by_path[path] = (None, None)


class FakeGeotagLoader:
    def __init__(self, gps_by_path: dict[Path, tuple], dates: dict[Path, tuple]) -> None:
        self.gps_by_path = gps_by_path
        self.dates = dates

    def load_photo_info(self, path: Path) -> PhotoInfo:
        latitude, longitude = self.gps_by_path.get(path, (None, None))
        taken, offset = self.dates.get(path, (None, None))
        return PhotoInfo(
            path=path, file_type="JPG", current_latitude=latitude, current_longitude=longitude,
            date_taken=taken, time_offset=offset, camera="Canon EOS R6",
        )


class FakeThumbnails:
    def cached_icon(self, path, has_gps=False):
        return None

    def load_images(self, paths):
        return {path: None for path in paths}

    def icon_from_image(self, path, has_gps, image):
        return self.load_icon(path, has_gps)

    def fallback_icon_for(self, has_gps):
        return self.load_icon(Path("fallback"), has_gps)

    def load_icon(self, path, has_gps=False):
        pixmap = QPixmap(32, 24)
        pixmap.fill(Qt.darkGreen)
        return QIcon(pixmap)


def _choosing(chosen):
    return lambda *_args, **_kwargs: (_args[-1] if _args else _kwargs["on_chosen"])(chosen)


class GeotagWindowTests(unittest.TestCase):
    """
    File > Geotag from GPS Track through the main window: the window's rows
    and thumbnails, toggling, the overwrite question, Apply with altitude,
    Undo, Cancel, the empty-list case, and the Shift link.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.gpx = self.tmp / "hike.gpx"
        self.gpx.write_text(GPX)
        self.settings = QSettings(str(self.tmp / "settings.ini"), QSettings.IniFormat)

        self.phone = Path("/tmp/geo-phone.jpg")  # 9:17 MDT: halfway between the first two points
        self.canon = Path("/tmp/geo-canon.cr3")  # 9:27 MDT
        self.tagged = Path("/tmp/geo-tagged.jpg")  # on the track, already has GPS
        self.early = Path("/tmp/geo-early.jpg")  # before the track
        self.paused = Path("/tmp/geo-paused.jpg")  # in the two-hour gap
        self.late = Path("/tmp/geo-late.jpg")  # after the track
        self.scan = Path("/tmp/geo-scan.jpg")  # no date
        day = datetime(2026, 10, 3)
        self.dates = {
            self.phone: (day.replace(hour=9, minute=17), MDT),
            self.canon: (day.replace(hour=9, minute=27), MDT),
            self.tagged: (day.replace(hour=9, minute=37), MDT),
            self.early: (day.replace(hour=7, minute=0), MDT),
            self.paused: (day.replace(hour=10, minute=40), MDT),
            self.late: (day.replace(hour=12, minute=30), MDT),
            self.scan: (None, None),
        }
        self.gps_by_path = {path: (None, None) for path in self.dates}
        self.gps_by_path[self.tagged] = (40.5, -111.5)

        self.window = MainWindow(settings=self.settings)
        self.window.background.run_inline = True
        self.window._create_tile_fetcher = FakeTileFetcher
        self.window.show()
        self.writer = FakeGeotagWriter(self.gps_by_path)
        self.loader = FakeGeotagLoader(self.gps_by_path, self.dates)
        self.window.exiftool = self.writer
        self.window.loader = self.loader
        self.window.workflow = PhotoWorkflowFacade(loader=self.loader, writer=self.writer)
        self.window.thumbnail_loader = FakeThumbnails()
        self.addCleanup(self.window.close)

    def _load(self, paths=None) -> None:
        self.window.load_photos(list(paths if paths is not None else self.dates))

    def _open(self):
        """Trigger the menu item with the GPX "chosen" at once."""
        with patch.object(self.window, "_pick_track_files", side_effect=_choosing([self.gpx])):
            self.window.geotag_action.trigger()
        geotag = self.window._geotag_window
        self.assertIsNotNone(geotag)
        self.assertTrue(geotag.isVisible())
        return geotag

    def _rows(self):
        return {row.name: row for row in self.window._geotag_plan.rows}

    def _click_row(self, path: Path, *, on_checkbox: bool = True) -> None:
        """Click a row's checkbox (its left edge), or the row's name."""
        geotag = self.window._geotag_window
        item = geotag.photo_list._items_by_path[str(path)]
        rect = geotag.photo_list.visualItemRect(item)
        point = QPoint(rect.left() + 20, rect.center().y()) if on_checkbox else rect.center()
        QTest.mouseClick(geotag.photo_list.viewport(), Qt.LeftButton, Qt.NoModifier, point)

    def _answer_overwrite_dialog(self, button_text: str | None):
        seen: list[str] = []

        def fake_show(dialog):
            seen.extend(button.text() for button in dialog.buttons())
            for button in dialog.buttons():
                if button.text() == button_text:
                    button.click()
                    return
            dialog.reject()

        return patch.object(QMessageBox, "show", new=fake_show), seen

    def test_the_window_shows_every_photo_with_its_place_on_the_track(self) -> None:
        self._load()
        geotag = self._open()

        rows = self._rows()
        self.assertEqual(
            [(row.name, row.status) for row in self.window._geotag_plan.rows],
            [("geo-early.jpg", BEFORE), ("geo-phone.jpg", ON_TRACK), ("geo-canon.cr3", ON_TRACK),
             ("geo-tagged.jpg", ON_TRACK), ("geo-paused.jpg", GAP), ("geo-late.jpg", AFTER), ("geo-scan.jpg", NO_DATE)],
        )
        self.assertAlmostEqual(rows["geo-phone.jpg"].latitude, 40.605)
        self.assertAlmostEqual(rows["geo-phone.jpg"].altitude, 2050.0)
        self.assertTrue(all(rows[name].included for name in ("geo-phone.jpg", "geo-canon.cr3")))
        self.assertFalse(rows["geo-tagged.jpg"].included, "a photo with GPS starts unchecked")
        self.assertEqual(rows["geo-tagged.jpg"].chip, "Has GPS")
        self.assertEqual(rows["geo-early.jpg"].chip, "Before the Track")
        self.assertIn("Date & Time tab", geotag.photo_list._items_by_path[str(self.early)].toolTip())
        # The track, and a dot per photo the map has a place for: orange where
        # the track puts a checked photo, blue where an unchecked photo with GPS is now.
        self.assertEqual(len(geotag.map_view.track_points), 6)
        dots = {pin.path: pin for pin in geotag.map_view._photo_pins}
        self.assertEqual(set(dots), {str(self.phone), str(self.canon), str(self.tagged)})
        self.assertEqual(dots[str(self.phone)].color, SELECTED_PHOTO_COLOR)
        self.assertIsNone(dots[str(self.phone)].ring)
        self.assertEqual((dots[str(self.tagged)].latitude, dots[str(self.tagged)].longitude), (40.5, -111.5))
        self.assertEqual(dots[str(self.tagged)].color, PHOTO_COLOR)
        self.assertEqual(geotag.apply_button.text(), "Geotag 2 Photos")
        self.assertEqual(geotag.check_all_box.checkState(), Qt.Checked)
        self.assertEqual(geotag.list_heading.text(), "Photos · ☑ will be geotagged")
        self.assertTrue(geotag.apply_button.isEnabled())
        self.assertIn("3 of 7 photos on the track", geotag.summary_label.text())
        self.assertIn("Shift the date and time", geotag.warning_label.text())
        # Every button has a hover hint.
        for button in geotag.findChildren(type(geotag.apply_button)):
            self.assertTrue(button.toolTip(), button.text())

    def test_clicking_a_row_leaves_the_photo_out_and_back_in(self) -> None:
        self._load()
        geotag = self._open()

        self._click_row(self.canon)
        self.assertFalse(self._rows()["geo-canon.cr3"].included)
        self.assertEqual(geotag.apply_button.text(), "Geotag 1 Photo")
        dots = {pin.path: pin for pin in geotag.map_view._photo_pins}
        self.assertEqual(dots[str(self.canon)].color, LEFT_OUT_PHOTO_COLOR, "left out: a grey dot on the track")
        self.assertIn("Left out", geotag.photo_list._items_by_path[str(self.canon)].toolTip())
        self.assertEqual(geotag.check_all_box.checkState(), Qt.PartiallyChecked)

        self._click_row(self.canon)
        self.assertTrue(self._rows()["geo-canon.cr3"].included)
        self.assertEqual(geotag.apply_button.text(), "Geotag 2 Photos")
        # Rows off the track can't be toggled.
        self._click_row(self.early)
        self.assertEqual(geotag.apply_button.text(), "Geotag 2 Photos")
        # A photo with GPS can be checked (Apply will ask about it): its blue
        # dot moves to where the track puts it, orange with a red ring, drawn last.
        self._click_row(self.tagged)
        self.assertTrue(self._rows()["geo-tagged.jpg"].included)
        self.assertEqual(geotag.apply_button.text(), "Geotag 3 Photos")
        tagged = next(pin for pin in geotag.map_view._photo_pins if pin.path == str(self.tagged))
        self.assertEqual((tagged.color, tagged.ring), (SELECTED_PHOTO_COLOR, REPLACE_RING_COLOR))
        self.assertAlmostEqual(tagged.latitude, 40.625)
        self.assertIs(geotag.map_view._photo_pins[-1], tagged, "ringed dots are drawn on top")
        self._click_row(self.tagged)
        tagged = next(pin for pin in geotag.map_view._photo_pins if pin.path == str(self.tagged))
        self.assertEqual((tagged.color, tagged.latitude), (PHOTO_COLOR, 40.5))

    def test_clicking_a_row_outside_its_checkbox_opens_the_preview_zoomed_in(self) -> None:
        self._load()
        geotag = self._open()
        geotag.map_view.set_view(0.0, 0.0, 3)

        self._click_row(self.tagged, on_checkbox=False)
        self.assertFalse(self._rows()["geo-tagged.jpg"].included, "not toggled")
        latitude, longitude = geotag.map_view.center
        self.assertAlmostEqual(latitude, 40.5, places=3)
        self.assertAlmostEqual(longitude, -111.5, places=3)
        self.assertEqual(geotag.map_view.zoom, PHOTO_ZOOM)
        self.assertTrue(geotag.preview.isVisible())
        self.assertEqual(geotag.preview.current_path, str(self.tagged))
        self.assertEqual(geotag.preview.use_button.text(), "Put On Track")
        self.assertEqual(geotag.preview.time_label.text(), "10/03/2026 9:37:00am MDT")
        self.assertEqual(geotag.photo_list.active_path, self.tagged)
        self.assertFalse(geotag.preview.stepper.isVisible(), "one photo at this spot")

        # Another photo: the preview moves to it (one preview at a time).
        self._click_row(self.phone, on_checkbox=False)
        self.assertTrue(self._rows()["geo-phone.jpg"].included, "not toggled")
        self.assertAlmostEqual(geotag.map_view.center[0], 40.605, places=3)
        self.assertEqual(geotag.preview.current_path, str(self.phone))
        self.assertEqual(geotag.preview.use_button.text(), "Leave Off Track")

        # Its button toggles the photo; the preview stays and re-reads.
        QTest.mouseClick(geotag.preview.use_button, Qt.LeftButton)
        self.assertFalse(self._rows()["geo-phone.jpg"].included)
        self.assertEqual(geotag.preview.use_button.text(), "Put On Track")

        # Checking the photo with GPS while its preview is open re-zooms to the new spot.
        self._click_row(self.tagged, on_checkbox=False)
        self._click_row(self.tagged)
        self.assertAlmostEqual(geotag.map_view.center[0], 40.625, places=3)
        self.assertEqual(geotag.preview.current_path, str(self.tagged))

        # Esc closes the preview first, then the window.
        QTest.keyClick(geotag, Qt.Key_Escape)
        self.assertFalse(geotag.preview.isVisible())
        self.assertIsNone(geotag.photo_list.active_path)
        self.assertTrue(geotag.isVisible())

        # Clicking the shown photo's row again closes its preview; so does a
        # click on the map itself; a photo with no dot can't be shown.
        self._click_row(self.phone, on_checkbox=False)
        self.assertTrue(geotag.preview.isVisible())
        self._click_row(self.phone, on_checkbox=False)
        self.assertFalse(geotag.preview.isVisible())
        self._click_row(self.phone, on_checkbox=False)
        geotag.map_view.background_clicked.emit()
        self.assertFalse(geotag.preview.isVisible())
        self.assertIsNone(geotag.photo_list.active_path)
        self._click_row(self.early, on_checkbox=False)
        self.assertFalse(geotag.preview.isVisible())
        self.assertIsNone(geotag.photo_list.active_path)

    def test_clicking_a_dot_opens_its_preview(self) -> None:
        self._load()
        geotag = self._open()
        geotag.map_view.photo_pins_clicked.emit([str(self.canon)], 0, 0)
        self.assertEqual(geotag.preview.current_path, str(self.canon))
        self.assertEqual(geotag.map_view.zoom, PHOTO_ZOOM)
        self.assertEqual(geotag.photo_list.active_path, self.canon)
        self.assertEqual(geotag.map_view.cursor().shape(), Qt.ArrowCursor)

    def test_the_master_box_checks_photos_without_gps_and_unchecks_everything(self) -> None:
        self._load()
        geotag = self._open()
        self.assertEqual(geotag.check_all_box.checkState(), Qt.Checked, "everything checkable is checked already")

        QTest.mouseClick(geotag.check_all_box, Qt.LeftButton, Qt.NoModifier, QPoint(8, geotag.check_all_box.height() // 2))
        self.assertEqual([row.name for row in self.window._geotag_plan.included], [])
        self.assertEqual(geotag.apply_button.text(), "No Photos on the Track")
        self.assertEqual(geotag.check_all_box.checkState(), Qt.Unchecked)

        QTest.mouseClick(geotag.check_all_box, Qt.LeftButton, Qt.NoModifier, QPoint(8, geotag.check_all_box.height() // 2))
        self.assertEqual([row.name for row in self.window._geotag_plan.included], ["geo-phone.jpg", "geo-canon.cr3"])
        self.assertFalse(self._rows()["geo-tagged.jpg"].included, "a photo with GPS is checked by hand only")
        self.assertEqual(geotag.check_all_box.checkState(), Qt.Checked)
        # A photo with GPS checked by hand: still "all checked"; unchecking all clears it too.
        self._click_row(self.tagged)
        self.assertEqual(geotag.check_all_box.checkState(), Qt.Checked)
        self._click_row(self.canon)
        self.assertEqual(geotag.check_all_box.checkState(), Qt.PartiallyChecked)
        QTest.mouseClick(geotag.check_all_box, Qt.LeftButton, Qt.NoModifier, QPoint(8, geotag.check_all_box.height() // 2))
        self.assertEqual([row.name for row in self.window._geotag_plan.included], ["geo-phone.jpg", "geo-canon.cr3", "geo-tagged.jpg"])
        QTest.mouseClick(geotag.check_all_box, Qt.LeftButton, Qt.NoModifier, QPoint(8, geotag.check_all_box.height() // 2))
        self.assertEqual(self.window._geotag_plan.included, [])

    def test_hovering_a_dot_or_a_row_fills_the_readout_and_grows_the_dot(self) -> None:
        self._load()
        geotag = self._open()

        geotag.map_view.photos_hovered.emit([str(self.phone)])
        self.assertIn("40.605000, -111.595000 · 6,726 ft", geotag.readout_label.text(), "feet by default")
        self.assertTrue(next(p for p in geotag.map_view._photo_pins if p.path == str(self.phone)).hovered)
        geotag.map_view.photos_hovered.emit([])
        self.assertEqual(geotag.readout_label.text(), READOUT_IDLE)
        # A row hovered grows its dot (the row itself isn't highlighted).
        geotag.photo_list.hovered.emit(str(self.canon))
        self.assertTrue(next(p for p in geotag.map_view._photo_pins if p.path == str(self.canon)).hovered)
        self.assertIsNone(geotag.photo_list.active_path)
        # A blue dot (an unchecked photo with GPS) says so.
        geotag.map_view.photos_hovered.emit([str(self.tagged)])
        self.assertIn("where it is now", geotag.readout_label.text())
        # The hint on the dot is the row's hint.
        self.assertIn("Will be placed", next(p for p in geotag.map_view._photo_pins if p.path == str(self.phone)).hint)

    def test_altitudes_follow_the_units_setting(self) -> None:
        self._load()
        geotag = self._open()
        self.assertIn("6,726 ft", geotag.photo_list._items_by_path[str(self.phone)].toolTip())
        self.window.set_use_feet(False)
        self.assertIn("2,050 m", geotag.photo_list._items_by_path[str(self.phone)].toolTip())
        geotag.map_view.photos_hovered.emit([str(self.phone)])
        self.assertIn("· 2,050 m", geotag.readout_label.text())

    def test_apply_asks_about_existing_gps_then_writes_positions_with_altitude(self) -> None:
        self._load()
        geotag = self._open()
        self._click_row(self.tagged)
        self.window.select_browser_paths([self.phone])

        dialog_patch, buttons = self._answer_overwrite_dialog("Skip Photos with GPS")
        with dialog_patch:
            QTest.mouseClick(geotag.apply_button, Qt.LeftButton)

        self.assertTrue({"Cancel", "Skip Photos with GPS", "Replace"} <= set(buttons), buttons)
        self.assertEqual([write[0] for write in self.writer.writes], [self.phone, self.canon])
        path, latitude, longitude, altitude = self.writer.writes[0]
        self.assertAlmostEqual(latitude, 40.605)
        self.assertAlmostEqual(longitude, -111.595)
        self.assertAlmostEqual(altitude, 2050.0)
        self.assertIsNone(self.window._geotag_window, "the window closed")
        self.assertEqual(self.window.get_selected_paths(), [], "the changed photos are deselected")
        self.assertIn("Geotagged 2 photos from the GPS track. Skipped 1 that already has GPS.", self.window._last_status_message)
        self.assertTrue(self.window.undo_action.isEnabled())

        # Undo clears the GPS (the altitude with it) from photos that had none;
        # Redo writes the position back with its altitude.
        self.window.undo_gps_edit()
        self.assertEqual(set(self.writer.clears), {self.phone, self.canon})
        self.assertEqual(self.gps_by_path[self.phone], (None, None))
        self.writer.writes.clear()
        self.window.redo_gps_edit()
        self.assertEqual(len(self.writer.writes), 2)
        self.assertAlmostEqual(self.writer.writes[0][3], 2050.0)

    def test_replace_writes_over_existing_gps(self) -> None:
        self._load()
        geotag = self._open()
        self._click_row(self.tagged)
        dialog_patch, _buttons = self._answer_overwrite_dialog("Replace")
        with dialog_patch:
            QTest.mouseClick(geotag.apply_button, Qt.LeftButton)
        self.assertEqual({write[0] for write in self.writer.writes}, {self.phone, self.canon, self.tagged})
        # Undo puts the old coordinates back on the photo that had them.
        self.window.undo_gps_edit()
        self.assertIn((self.tagged, 40.5, -111.5, None), self.writer.writes)

    def test_cancelling_the_question_keeps_the_window_open(self) -> None:
        self._load()
        geotag = self._open()
        self._click_row(self.tagged)
        dialog_patch, _buttons = self._answer_overwrite_dialog("Cancel")
        with dialog_patch:
            QTest.mouseClick(geotag.apply_button, Qt.LeftButton)
        self.assertEqual(self.writer.writes, [])
        self.assertTrue(geotag.isVisible())

    def test_unchecked_gps_photos_are_left_alone_without_a_question(self) -> None:
        self._load()
        geotag = self._open()
        QTest.mouseClick(geotag.apply_button, Qt.LeftButton)
        self.assertEqual({write[0] for write in self.writer.writes}, {self.phone, self.canon})
        self.assertEqual(self.window._last_status_message, "Geotagged 2 photos from the GPS track.")

    def test_escape_cancels_and_deselects(self) -> None:
        self._load()
        self.window.select_browser_paths([self.phone, self.early])
        geotag = self._open()

        QTest.keyClick(geotag, Qt.Key_Escape)

        self.assertIsNone(self.window._geotag_window)
        self.assertEqual(self.window.get_selected_paths(), [])
        self.assertEqual(self.writer.writes, [])

    def test_the_menu_item_is_greyed_out_until_photos_are_loaded(self) -> None:
        self.assertFalse(self.window.geotag_action.isEnabled())
        self.assertIn("Add photos to the Photo List first", self.window.geotag_action.toolTip())
        with patch.object(self.window, "_pick_track_files", side_effect=_choosing([self.gpx])):
            self.window.geotag_action.trigger()
        self.assertIsNone(self.window._geotag_window)

        self._load([self.phone, self.canon])
        self.assertTrue(self.window.geotag_action.isEnabled())
        self.assertIn("Load a GPS track", self.window.geotag_action.toolTip())
        self._open()
        self.assertEqual(sorted(self._rows()), ["geo-canon.cr3", "geo-phone.jpg"])

    def test_add_more_photos_refreshes_the_plan_keeping_the_checks(self) -> None:
        self._load([self.phone, self.canon])
        geotag = self._open()
        self._click_row(self.canon)

        with patch.object(self.window, "_pick_photo_files", side_effect=_choosing([self.tagged, self.scan])):
            QTest.mouseClick(geotag.add_photos_button, Qt.LeftButton)

        rows = self._rows()
        self.assertEqual(sorted(rows), ["geo-canon.cr3", "geo-phone.jpg", "geo-scan.jpg", "geo-tagged.jpg"])
        self.assertFalse(rows["geo-canon.cr3"].included, "the check made before stays")
        self.assertFalse(rows["geo-tagged.jpg"].included, "a photo with GPS starts unchecked")
        self.assertEqual(geotag.apply_button.text(), "Geotag 1 Photo")

    def test_nothing_matches_disables_apply_and_explains(self) -> None:
        self._load([self.early, self.scan])
        geotag = self._open()
        self.assertFalse(geotag.apply_button.isEnabled())
        self.assertEqual(geotag.apply_button.text(), "No Photos on the Track")
        self.assertIn("before this track", geotag.warning_label.text())
        self.assertEqual(geotag.map_view._photo_pins, [])

    def test_a_bad_file_shows_a_message_and_opens_nothing(self) -> None:
        self._load()
        bad = self.tmp / "notes.gpx"
        bad.write_text("not xml")
        shown = []
        with patch.object(QMessageBox, "show", new=lambda dialog: shown.append(dialog.text())), \
                patch.object(self.window, "_pick_track_files", side_effect=_choosing([bad])):
            self.window.geotag_action.trigger()
        self.assertIsNone(self.window._geotag_window)
        self.assertIn("notes.gpx is not a GPX file", shown[0])

    def test_the_shift_link_lands_on_date_and_time_with_the_photos_selected(self) -> None:
        self._load()
        geotag = self._open()

        geotag.warning_label.linkActivated.emit("shift")

        self.assertIsNone(self.window._geotag_window)
        self.assertEqual(self.window.editor_tabs.currentIndex(), DATE_TIME_TAB)
        self.assertEqual(self.window._date_change_mode, MODE_SHIFT)
        self.assertEqual(set(self.window.get_selected_paths()), set(self.dates) - {self.scan})
        self.assertIn("load the track", self.window._last_status_message)


if __name__ == "__main__":
    unittest.main()
