"""
The Date & Time tab and the Photo List's Date & Time mode, driven with real
mouse clicks and key presses like a user would.
"""

import os
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QCheckBox, QMessageBox, QWidget

from core.models import PhotoInfo
from core.photo_dates import date_taken_from_tags, format_exif_datetime, time_offset_from_tags
from gui.main_window import MainWindow
from gui.widgets.editor_panel import DATE_TIME_TAB, LOCATION_TAB
from gui.widgets.thumbnail_delegate import PICK_DISABLED_ROLE, SOURCE_ROLE
from services.workflow_facade import PhotoWorkflowFacade
from tests.test_main_window_smoke import FakeThumbnailLoader


def exif(*parts) -> str:
    return format_exif_datetime(datetime(*parts))


class FakeDateExifTool:
    """Keeps each photo's date tags in a dict; can fail on chosen files."""

    def __init__(self, tags_by_path: dict[Path, dict]) -> None:
        self.tags_by_path = tags_by_path
        self.date_writes: list[tuple[Path, dict]] = []
        self.failures: dict[Path, Exception] = {}

    def write_date_tags(self, path: Path, values: dict) -> None:
        if path in self.failures:
            raise self.failures[path]
        self.date_writes.append((path, dict(values)))
        # Like ExifTool: None removes a tag; tags not given stay as they are.
        tags = {**self.tags_by_path.get(path, {}), **values}
        self.tags_by_path[path] = {tag: value for tag, value in tags.items() if value is not None}


class FakeDateLoader:
    def __init__(self, tags_by_path: dict[Path, dict], cameras: dict[Path, str | None], gps: set[Path]) -> None:
        self.tags_by_path = tags_by_path
        self.cameras = cameras
        self.gps = gps

    def load_photo_info(self, path: Path) -> PhotoInfo:
        tags = self.tags_by_path.get(path, {})
        return PhotoInfo(
            path=path,
            file_type="JPG",
            current_latitude=40.5 if path in self.gps else None,
            current_longitude=-111.8 if path in self.gps else None,
            date_taken=date_taken_from_tags(tags),
            time_offset=time_offset_from_tags(tags),
            camera=self.cameras.get(path),
            date_tags=dict(tags),
        )


def tags(*parts) -> dict:
    value = exif(*parts)
    return {"DateTimeOriginal": value, "CreateDate": value, "ModifyDate": value, "FileModifyDate": value + "-06:00"}


class DateTimeTabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        settings_dir = tempfile.TemporaryDirectory()
        self.addCleanup(settings_dir.cleanup)
        self.settings = QSettings(str(Path(settings_dir.name) / "s.ini"), QSettings.IniFormat)

        # Two Canon photos (clock 1 h 2 min 10 s slow), an iPhone photo with
        # the right time taken at the same moment as the first, and a scan.
        # Real (empty) files: undo leaves out photos that no longer exist.
        photo_dir = Path(settings_dir.name)
        self.canon1 = photo_dir / "IMG_4101.CR3"
        self.canon2 = photo_dir / "IMG_4102.CR3"
        self.phone = photo_dir / "IMG_8801.jpg"
        self.scan = photo_dir / "scan.jpg"
        for path in (self.canon1, self.canon2, self.phone, self.scan):
            path.write_bytes(b"")
        self.tags = {
            self.canon1: tags(2026, 10, 3, 9, 14, 2),
            self.canon2: tags(2026, 10, 3, 9, 15, 40),
            self.phone: tags(2026, 10, 3, 10, 16, 12),
            self.scan: {},
        }
        self.original_tags = {path: dict(value) for path, value in self.tags.items()}
        cameras = {self.canon1: "Canon EOS R6", self.canon2: "Canon EOS R6", self.phone: "Apple iPhone 15 Pro"}

        self.window = MainWindow(settings=self.settings)
        self.window.background.run_inline = True
        self.window.show()
        self.writer = FakeDateExifTool(self.tags)
        self.window.workflow = PhotoWorkflowFacade(
            loader=FakeDateLoader(self.tags, cameras, gps={self.phone}),
            writer=self.writer,
        )
        self.window.thumbnail_loader = FakeThumbnailLoader()
        self.window.session.selected_paths = [self.canon1, self.canon2, self.phone, self.scan]
        self.window.populate_list()

    def tearDown(self) -> None:
        self.window.close()

    # --- Helpers ----------------------------------------------------------------

    def _open_date_tab(self) -> None:
        tab_bar = self.window.editor_tabs.tabBar()
        QTest.mouseClick(tab_bar, Qt.LeftButton, Qt.NoModifier, tab_bar.tabRect(DATE_TIME_TAB).center())
        self.assertEqual(self.window.editor_tabs.currentIndex(), DATE_TIME_TAB)

    def _choose_shift(self) -> None:
        """Step 2: click the Shift card."""
        QTest.mouseClick(self.window.date_shift_choice, Qt.LeftButton)

    def _choose_set(self) -> None:
        """Step 2: click the Set card."""
        QTest.mouseClick(self.window.date_set_choice, Qt.LeftButton)

    def _click_item(self, path: Path) -> None:
        grid = self.window.list_widget
        item = self.window._grid_items_by_path[str(path)]
        QTest.mouseClick(grid.viewport(), Qt.LeftButton, Qt.NoModifier, grid.visualItemRect(item).center())

    def _select(self, *paths: Path) -> None:
        for path in paths:
            self._click_item(path)

    def _headings(self) -> list[str]:
        titles = []
        for header in self.window._group_header_items:
            widget = self.window.list_widget.itemWidget(header)
            label = widget.findChild(QWidget, "thumbnailGroupHeader")
            if not header.isHidden():
                titles.append(label.text())
        return titles

    def _set_corrected_time(self, value: datetime) -> None:
        """Set the reference photo's correct time with the drop-downs."""
        picker = self.window.date_reference_picker
        picker.date_edit.setDate(value.date())
        picker.hour_box.setCurrentIndex(value.hour)
        picker.minute_box.setCurrentIndex(value.minute)
        picker.second_box.setCurrentIndex(value.second)

    def _change_rows(self) -> list[tuple[str, str, str]]:
        changes = self.window.date_changes_list
        return [
            tuple(changes.topLevelItem(row).text(column) for column in range(3))
            for row in range(changes.topLevelItemCount())
        ]

    # --- Steps ----------------------------------------------------------------

    def _step_states(self) -> list[str]:
        return [step.property("state") for step in self.window.date_steps]

    def test_steps_open_one_after_another(self) -> None:
        self._open_date_tab()
        self.assertEqual(self._step_states(), ["active", "locked", "locked", "locked"])
        self.assertTrue(self.window.step_add_photos_button.isHidden())

        self._select(self.canon1, self.canon2)
        self.assertEqual(self._step_states(), ["done", "active", "locked", "locked"])
        self.assertEqual(self.window.date_steps[0].summary.text(), "2 photos selected")
        self.assertFalse(self.window.date_apply_button.isVisible())

        self._choose_shift()
        self.assertTrue(self.window.date_shift_choice.isChecked())
        self.assertEqual(self._step_states(), ["done", "done", "active", "locked"])

        self._set_corrected_time(datetime(2026, 10, 3, 10, 16, 12))
        self.assertEqual(self._step_states(), ["done", "done", "done", "active"])
        self.assertTrue(self.window.date_apply_button.isVisible())

        # After applying, back to step 1 with nothing chosen.
        QTest.mouseClick(self.window.date_apply_button, Qt.LeftButton)
        self.assertEqual(self._step_states(), ["active", "locked", "locked", "locked"])
        self.assertFalse(self.window.date_shift_choice.isChecked())

    def test_empty_list_offers_add_photos_in_step_1(self) -> None:
        self.window.clear_photo_list()
        self._open_date_tab()

        self.assertFalse(self.window.step_add_photos_button.isHidden())
        self.assertIn("The Photo List is empty", self.window.step_select_hint.text())
        with patch.object(self.window, "_pick_photo_files") as pick:
            QTest.mouseClick(self.window.step_add_photos_button, Qt.LeftButton)
        pick.assert_called_once()

    def test_step_2_cards_are_stacked_with_one_line_titles(self) -> None:
        self._open_date_tab()
        self._select(self.canon1)
        QApplication.processEvents()
        cards = list(self.window.date_choice_cards.values())

        self.assertEqual(self.window.date_steps[1].title.text(), "Choose how to change Date & Time")
        self.assertEqual(
            [card.title_label.text() for card in cards],
            ["Shift Date and Time", "Set One Date and Time", "Change Time Zone"],
        )
        for card in cards:
            # Full width, one line per title, only as tall as the text needs.
            self.assertEqual(card.width(), cards[0].width())
            self.assertGreaterEqual(card.title_label.width(), card.title_label.sizeHint().width())
            self.assertEqual(card.height(), card.heightForWidth(card.width()))
            self.assertFalse(card.change_label.isVisible())

    def test_step_2_folds_up_to_the_choice_and_opens_again(self) -> None:
        # Already in the default zone: step 3 waits for another zone.
        self._give_zone(self.canon1, "-06:00")
        self._open_date_tab()
        self._select(self.canon1)
        zone_card = self.window.date_zone_choice
        QTest.mouseClick(zone_card, Qt.LeftButton)

        # Folded: only the chosen card, with "Change ▾"; step 3 is next.
        self.assertTrue(self.window.date_shift_choice.isHidden())
        self.assertTrue(self.window.date_set_choice.isHidden())
        self.assertTrue(zone_card.change_label.isVisible())
        self.assertEqual(self._step_states()[1:3], ["done", "active"])
        self.assertEqual(self.window.date_steps[2].title.text(), "Choose the new time zone")
        self.assertFalse(self.window.date_zone_box.isHidden())

        # Clicking it opens all three again (step 3 waits) ...
        QTest.mouseClick(zone_card, Qt.LeftButton)
        self.assertFalse(self.window.date_shift_choice.isHidden())
        self.assertFalse(zone_card.change_label.isVisible())
        self.assertEqual(self._step_states()[1:3], ["active", "locked"])

        # ... and picking one folds up to it.
        QTest.mouseClick(self.window.date_set_choice, Qt.LeftButton)
        self.assertTrue(zone_card.isHidden())
        self.assertTrue(self.window.date_set_choice.change_label.isVisible())
        self.assertEqual(self.window.date_steps[2].title.text(), "Enter the date and time")

    # --- Change Time Zone -------------------------------------------------------

    def _give_zone(self, path: Path, offset_text: str) -> None:
        """Give a loaded photo a time zone (as if read from OffsetTimeOriginal)."""
        info = self.window.session.loaded_photo_infos[path]
        tags = {**info.date_tags, "OffsetTimeOriginal": offset_text}
        # In the "file" too, so undo has the same tags to go back to.
        self.tags[path]["OffsetTimeOriginal"] = offset_text
        self.original_tags[path]["OffsetTimeOriginal"] = offset_text
        self.window.session.loaded_photo_infos[path] = replace(
            info, time_offset=time_offset_from_tags(tags), date_tags=tags
        )

    def _choose_zone_mode(self, *paths: Path) -> None:
        self._open_date_tab()
        self._select(*paths)
        QTest.mouseClick(self.window.date_zone_choice, Qt.LeftButton)

    def test_change_time_zone_keeps_the_moment(self) -> None:
        self._give_zone(self.canon1, "-06:00")
        self._choose_zone_mode(self.canon1)
        self.window.date_zone_chosen("central")

        self.assertEqual(self.window.date_apply_button.text(), "Change Time Zone of 1 Photo")
        QTest.mouseClick(self.window.date_apply_button, Qt.LeftButton)

        self.assertEqual(self.tags[self.canon1]["DateTimeOriginal"], exif(2026, 10, 3, 10, 14, 2))
        self.assertEqual(self.tags[self.canon1]["OffsetTimeOriginal"], "-05:00")
        self.assertEqual(self.tags[self.canon1]["OffsetTime"], "-05:00")
        self.assertIn("Changed the time zone of 1 photo", self.window.browser_hint.text())

        self.window.undo_action.trigger()
        self.assertEqual(self.tags[self.canon1], self.original_tags[self.canon1])

    def test_keep_clock_time_asks_first(self) -> None:
        self._give_zone(self.canon1, "-06:00")
        self._choose_zone_mode(self.canon1)
        self.window.date_zone_chosen("central")
        shown = []
        with patch.object(self.window, "show_message", side_effect=lambda dialog, closed: shown.append((dialog, closed))):
            QTest.mouseClick(self.window.date_keep_clock_check, Qt.LeftButton)
        dialog, closed = shown[0]
        # (Not the window title: macOS message boxes have none.)
        self.assertTrue(dialog.text().startswith("When enabled, the photos keep their clock times"))
        self.assertIn("9:14:02am MDT → 9:14:02am CDT", dialog.text())
        self.assertIn("(1 h here)", dialog.text())

        # Cancel: unchecked, the moment is kept.
        closed(dialog.button(QMessageBox.Cancel))
        self.assertFalse(self.window.date_keep_clock_check.isChecked())

        # Keep Clock Time: the clock stays, only the zone changes.
        with patch.object(self.window, "show_message", side_effect=lambda dialog, closed: shown.append((dialog, closed))):
            QTest.mouseClick(self.window.date_keep_clock_check, Qt.LeftButton)
        dialog, closed = shown[1]
        keep = next(button for button in dialog.buttons() if button.text() == "Keep Clock Time")
        closed(keep)
        self.assertTrue(self.window.date_keep_clock_check.isChecked())
        QTest.mouseClick(self.window.date_apply_button, Qt.LeftButton)
        self.assertEqual(self.tags[self.canon1]["DateTimeOriginal"], exif(2026, 10, 3, 9, 14, 2))
        self.assertEqual(self.tags[self.canon1]["OffsetTimeOriginal"], "-05:00")
        # The next change starts with the box off.
        self.assertFalse(self.window.date_keep_clock_check.isChecked())

    def test_zone_drop_down_hint_only_for_mixed_zones(self) -> None:
        self._give_zone(self.canon1, "-06:00")
        self._give_zone(self.canon2, "-06:00")
        self._choose_zone_mode(self.canon1, self.canon2)
        self.assertEqual(self.window.date_zone_combo.toolTip(), "")

        self._give_zone(self.canon2, "-05:00")
        self.window.update_details_panel()
        self.assertTrue(self.window.date_zone_combo.property("mixed"))
        self.assertIn("more than one time zone", self.window.date_zone_combo.toolTip())

    def test_changes_list_hint_shows_cut_short_rows_in_full(self) -> None:
        self._give_zone(self.canon1, "-06:00")
        self._choose_zone_mode(self.canon1)
        self.window.date_zone_chosen("central")
        changes = self.window.date_changes_list

        # Wide enough for the whole row: no hint.
        self.window.resize(3200, 900)
        QApplication.processEvents()
        self.assertEqual(changes.row_tooltip(changes.topLevelItem(0)), "")

        # Narrow: the original date ends in "…", so the hint shows the row.
        self.window.resize(900, 900)
        QApplication.processEvents()
        item = changes.topLevelItem(0)
        self.assertEqual(
            changes.row_tooltip(item),
            "IMG_4101.CR3\nOriginal: 10/03/2026 9:14:02am MDT\nNew: 10/03/2026 10:14:02am CDT",
        )

    def test_changes_list_keeps_new_dates_in_view(self) -> None:
        # A photo without a zone gets the long "(time kept, time zone added)"
        # note; it once pushed the new-date column past the list's right
        # edge, so no row showed its new date (found on Windows).
        self._give_zone(self.canon1, "-06:00")
        self._choose_zone_mode(self.canon1, self.canon2)
        self.window.date_zone_chosen("central")
        self.window.resize(900, 900)
        QApplication.processEvents()
        changes = self.window.date_changes_list
        header = changes.header()

        self.assertLessEqual(header.sectionPosition(2) + header.sectionSize(2), changes.viewport().width())
        # The usual row's new date is whole; the long one is cut short and
        # its hover hint shows it in full.
        rows = {changes.topLevelItem(row).text(0): changes.topLevelItem(row) for row in range(2)}
        self.assertFalse(changes._is_cut_short(rows["IMG_4101.CR3"], 2))
        self.assertTrue(changes._is_cut_short(rows["IMG_4102.CR3"], 2))
        self.assertIn("(time kept, time zone added)", changes.row_tooltip(rows["IMG_4102.CR3"]))

    def test_set_zone_change_keeps_the_moment(self) -> None:
        # Choosing another zone converts Set's date and time (the same
        # moment); only editing the date or time moves it.
        self._give_zone(self.canon1, "-06:00")
        self._open_date_tab()
        self._select(self.canon1)
        self._choose_set()
        picker = self.window.date_set_picker
        self.assertEqual(picker.value(), datetime(2026, 10, 3, 9, 14, 2))
        # The zone comes first, above the date and time.
        self.assertLess(picker.zone_box.y(), picker.date_edit.y())

        box = picker.zone_box
        index = box.findData("central")
        box.setCurrentIndex(index)
        box.activated.emit(index)
        self.assertEqual(picker.value(), datetime(2026, 10, 3, 10, 14, 2))

        QTest.mouseClick(self.window.date_apply_button, Qt.LeftButton)
        self.assertEqual(self.tags[self.canon1]["DateTimeOriginal"], exif(2026, 10, 3, 10, 14, 2))
        self.assertEqual(self.tags[self.canon1]["OffsetTimeOriginal"], "-05:00")

    def test_photo_without_a_zone_keeps_its_time_and_gets_the_zone(self) -> None:
        self._choose_zone_mode(self.canon2)
        self.window.date_zone_chosen("central")
        QTest.mouseClick(self.window.date_apply_button, Qt.LeftButton)
        self.assertEqual(self.tags[self.canon2]["DateTimeOriginal"], exif(2026, 10, 3, 9, 15, 40))
        self.assertEqual(self.tags[self.canon2]["OffsetTimeOriginal"], "-05:00")

    def test_set_card_titles_step_3_enter(self) -> None:
        self._open_date_tab()
        self._select(self.canon1)
        self._choose_set()
        self.assertEqual(self.window.date_steps[2].title.text(), "Enter the date and time")
        self.assertTrue(self.window.date_shift_box.isHidden())
        self.assertFalse(self.window.date_set_box.isHidden())

    # --- Photo List in Date & Time mode ---------------------------------------

    def test_date_tab_groups_the_photo_list_by_camera(self) -> None:
        self.assertEqual(
            self._headings(),
            ["Photos without GPS Coordinates (3)", "Photos with GPS Coordinates (1)"],
        )

        self._open_date_tab()

        self.assertEqual(
            self._headings(),
            ["Apple iPhone 15 Pro (1)", "Canon EOS R6 (2)", "Unknown Camera (1)"],
        )
        # The date under each name.
        self.assertEqual(
            self.window._grid_items_by_path[str(self.canon1)].text(),
            "IMG_4101.CR3\n10/03/2026 9:14:02am",
        )
        self.assertTrue(self.window.gps_filter_bar.isHidden())
        self.assertFalse(self.window.camera_filter_bar.isHidden())
        self.assertEqual(
            [button.text() for button in self.window.camera_filter_buttons.values()],
            ["All (4)", "Apple iPhone 15 Pro (1)", "Canon EOS R6 (2)", "Unknown Camera (1)"],
        )

        # Back to Location: GPS groups again.
        tab_bar = self.window.editor_tabs.tabBar()
        QTest.mouseClick(tab_bar, Qt.LeftButton, Qt.NoModifier, tab_bar.tabRect(LOCATION_TAB).center())
        self.assertEqual(self._headings()[0], "Photos without GPS Coordinates (3)")
        self.assertFalse(self.window.gps_filter_bar.isHidden())

    def test_switching_tabs_keeps_the_selection(self) -> None:
        self._select(self.canon2, self.phone)

        self._open_date_tab()

        self.assertEqual(set(self.window.get_selected_paths()), {self.canon2, self.phone})

    def test_camera_filter_shows_one_camera_and_hides_with_one_camera(self) -> None:
        self._open_date_tab()

        self.window.camera_filter_buttons["Canon EOS R6"].click()
        self.assertEqual(self._headings(), ["Canon EOS R6 (2)"])
        self.assertTrue(self.window._grid_items_by_path[str(self.phone)].isHidden())

        # One camera in the list: no camera filter.
        self.window.session.selected_paths = [self.canon1, self.canon2]
        self.window.populate_list()
        self.assertTrue(self.window.camera_filter_bar.isHidden())

    def test_camera_checkbox_selects_every_photo_from_that_camera(self) -> None:
        self._open_date_tab()
        boxes = {box.property("camera"): box for box in self.window.findChildren(QCheckBox, "cameraCheck")}

        boxes["Canon EOS R6"].click()
        self.assertEqual(set(self.window.get_selected_paths()), {self.canon1, self.canon2})

        # Deselecting one photo unchecks it; checking again selects both.
        self._click_item(self.canon2)
        boxes = {box.property("camera"): box for box in self.window.findChildren(QCheckBox, "cameraCheck")}
        self.assertFalse(boxes["Canon EOS R6"].isChecked())
        boxes["Canon EOS R6"].click()
        self.assertEqual(set(self.window.get_selected_paths()), {self.canon1, self.canon2})
        boxes["Canon EOS R6"].click()
        self.assertEqual(self.window.get_selected_paths(), [])

    # --- Shift ----------------------------------------------------------------

    def test_shift_by_correcting_the_earliest_photo(self) -> None:
        self._open_date_tab()
        self._select(self.canon2, self.canon1)
        self._choose_shift()
        self.assertEqual(self.window.date_reference_title.text(), "IMG_4101.CR3 · Canon EOS R6")
        self.assertEqual(self.window.date_reference_detail.text(), "Current Date: 10/03/2026 9:14:02am")
        self.assertFalse(self.window.date_apply_button.isEnabled())

        self._set_corrected_time(datetime(2026, 10, 3, 10, 16, 12))

        self.assertEqual(
            self._change_rows(),
            [
                ("IMG_4101.CR3", "10/03/2026 9:14:02am", "→  10/03/2026 10:16:12am"),
                ("IMG_4102.CR3", "10/03/2026 9:15:40am", "→  10/03/2026 10:17:50am"),
            ],
        )
        self.assertEqual(self.window.date_apply_button.text(), "Shift 2 Photos")
        QTest.mouseClick(self.window.date_apply_button, Qt.LeftButton)

        self.assertEqual(self.tags[self.canon1]["DateTimeOriginal"], "2026:10:03 10:16:12")
        self.assertEqual(self.tags[self.canon2]["CreateDate"], "2026:10:03 10:17:50")
        self.assertEqual(self.tags[self.canon2]["FileModifyDate"], "2026:10:03 10:17:50")
        # Like GPS: the changed photos are deselected, and Undo is offered.
        self.assertEqual(self.window.get_selected_paths(), [])
        self.assertIn("Shifted 2 photos (1 h 2 min 10 s later).", self.window.browser_hint.text())
        self.assertIn('href="undo"', self.window.browser_hint.text())

    def test_undo_and_redo_restore_the_exact_tags(self) -> None:
        self._open_date_tab()
        self._select(self.canon1, self.canon2)
        self._choose_shift()
        self._set_corrected_time(datetime(2026, 10, 3, 10, 16, 12))
        QTest.mouseClick(self.window.date_apply_button, Qt.LeftButton)
        shifted = {path: dict(self.tags[path]) for path in (self.canon1, self.canon2)}

        self.window.undo_action.trigger()

        for path in (self.canon1, self.canon2):
            self.assertEqual(self.tags[path], self.original_tags[path])
        self.assertIn("Date change undone.", self.window.browser_hint.text())
        # Undo also brings the selection back.
        self.assertEqual(set(self.window.get_selected_paths()), {self.canon1, self.canon2})

        self.window.redo_action.trigger()
        for path in (self.canon1, self.canon2):
            self.assertEqual(self.tags[path], shifted[path])

    def test_reference_arrows_choose_another_photo(self) -> None:
        self._open_date_tab()
        self._select(self.canon1, self.canon2)
        self.assertEqual(self.window.date_reference_position.text(), "1 of 2")
        self.assertFalse(self.window.date_reference_back.isEnabled())

        QTest.mouseClick(self.window.date_reference_forward, Qt.LeftButton)

        self.assertEqual(self.window.date_reference_position.text(), "2 of 2")
        self.assertEqual(self.window.date_reference_title.text(), "IMG_4102.CR3 · Canon EOS R6")
        self.assertTrue(self.window.date_reference_earliest.isHidden())

    def test_undated_photos_are_skipped_with_a_warning(self) -> None:
        self._open_date_tab()
        self._select(self.canon1, self.scan)
        self._choose_shift()
        self._set_corrected_time(datetime(2026, 10, 3, 10, 16, 12))

        self.assertIn("without a date will be skipped", self.window.date_hint_label.text())
        self.assertIn("2 cameras", self.window.date_hint_label.text())
        self.assertEqual(self._change_rows()[-1], ("scan.jpg", "No date", "Skipped"))
        QTest.mouseClick(self.window.date_apply_button, Qt.LeftButton)
        self.assertEqual([path for path, _ in self.writer.date_writes], [self.canon1])

    # --- The photo with the correct time --------------------------------------

    def test_pick_the_photo_with_the_correct_time_from_the_photo_list(self) -> None:
        self._open_date_tab()
        self._select(self.canon1, self.canon2)
        self._choose_shift()

        QTest.mouseClick(self.window.pick_time_button, Qt.LeftButton)
        self.assertTrue(self.window.is_picking_location)
        self.assertEqual(self.window.pick_time_button.text(), "Cancel")
        self.assertFalse(self.window.date_apply_button.isEnabled())
        self.assertFalse(self.window.date_reference_picker.isEnabled())
        # Photos being changed and photos without a date can't be picked.
        self.assertEqual(self.window._grid_items_by_path[str(self.canon1)].data(PICK_DISABLED_ROLE), "Being Changed")
        self.assertEqual(self.window._grid_items_by_path[str(self.scan)].data(PICK_DISABLED_ROLE), "No Date")

        self._click_item(self.phone)

        self.assertFalse(self.window.is_picking_location)
        self.assertTrue(self.window._grid_items_by_path[str(self.phone)].data(SOURCE_ROLE))
        self.assertFalse(self.window.time_source_card.isHidden())
        self.assertEqual(self.window.time_source_title.text(), "Time from IMG_8801.jpg")
        self.assertEqual(self.window.date_reference_picker.value(), datetime(2026, 10, 3, 10, 16, 12))
        # Picking didn't change the selection.
        self.assertEqual(set(self.window.get_selected_paths()), {self.canon1, self.canon2})

        QTest.mouseClick(self.window.date_apply_button, Qt.LeftButton)
        self.assertEqual(self.tags[self.canon1]["DateTimeOriginal"], "2026:10:03 10:16:12")
        self.assertEqual(self.tags[self.phone], self.original_tags[self.phone])

    def test_escape_cancels_picking(self) -> None:
        self._open_date_tab()
        self._select(self.canon1)
        QTest.mouseClick(self.window.pick_time_button, Qt.LeftButton)

        QTest.keyClick(self.window.list_widget, Qt.Key_Escape)

        self.assertFalse(self.window.is_picking_location)
        self.assertEqual(self.window.pick_time_button.text(), "From a Photo in the Photo List")
        # The camera checkboxes, locked while picking, work again.
        self.assertTrue(all(box.isEnabled() for box in self.window.findChildren(QCheckBox, "cameraCheck")))
        self.assertIsNone(self.window._grid_items_by_path[str(self.canon1)].data(PICK_DISABLED_ROLE))

    def test_typing_a_time_drops_the_source(self) -> None:
        self._open_date_tab()
        self._select(self.canon1)
        self.window.use_time_from_path(self.phone)
        self.assertTrue(self.window._grid_items_by_path[str(self.phone)].data(SOURCE_ROLE))

        self._set_corrected_time(datetime(2026, 10, 3, 11, 0, 0))

        self.assertTrue(self.window.time_source_card.isHidden())
        self.assertFalse(self.window._grid_items_by_path[str(self.phone)].data(SOURCE_ROLE))

    def test_source_photo_is_left_out_when_also_selected(self) -> None:
        self._open_date_tab()
        self._select(self.canon1)
        self._choose_shift()
        self.window.use_time_from_path(self.phone)
        self._click_item(self.phone)

        self.assertEqual(self._change_rows()[-1], ("IMG_8801.jpg", "10/03/2026 10:16:12am", "Source, not changed"))
        QTest.mouseClick(self.window.date_apply_button, Qt.LeftButton)
        self.assertEqual([path for path, _ in self.writer.date_writes], [self.canon1])

    def test_photo_on_the_computer_without_a_date_shows_a_message(self) -> None:
        self._open_date_tab()
        self._select(self.canon1)
        outside = Path("/tmp/other.jpg")
        shown = []
        with patch.object(self.window, "show_message", side_effect=lambda dialog, *_: shown.append(dialog.text())):
            self.window.use_time_from_file(outside)

        self.assertEqual(shown, ["Selected Photo has no date taken, so its time can't be used."])
        self.assertTrue(self.window.time_source_card.isHidden())

    def test_photo_on_the_computer_with_a_date_becomes_the_source(self) -> None:
        self._open_date_tab()
        self._select(self.canon1)
        outside = Path("/tmp/PXL_1.jpg")
        self.tags[outside] = tags(2026, 10, 3, 10, 16, 12)

        self.window.use_time_from_file(outside)

        self.assertFalse(self.window.time_source_card.isHidden())
        self.assertEqual(self.window.date_reference_picker.value(), datetime(2026, 10, 3, 10, 16, 12))

    def test_deselect_all_starts_the_change_over(self) -> None:
        self._open_date_tab()
        self._select(self.canon1, self.canon2)
        self.window.use_time_from_path(self.phone)
        self._choose_zone("eastern")

        QTest.mouseClick(self.window.deselect_all_button, Qt.LeftButton)
        self._select(self.canon1)

        self.assertTrue(self.window.time_source_card.isHidden())
        self.assertEqual(self.window.date_reference_picker.value(), datetime(2026, 10, 3, 9, 14, 2))
        self.assertEqual(self.window.date_reference_picker.zone_box.currentText(), "No time zone")

    def test_removing_the_source_photo_from_the_list_starts_over(self) -> None:
        self._open_date_tab()
        self._select(self.canon1)
        self.window.use_time_from_path(self.phone)
        self.assertNotEqual(self.window.date_reference_picker.value(), datetime(2026, 10, 3, 9, 14, 2))

        self.window._remove_browser_paths({self.phone})
        # Removing photos from the list clears the selection; select again.
        self._select(self.canon1)

        self.assertTrue(self.window.time_source_card.isHidden())
        self.assertEqual(self.window.date_reference_picker.value(), datetime(2026, 10, 3, 9, 14, 2))

    # --- Set ------------------------------------------------------------------

    def test_set_gives_every_selected_photo_one_date(self) -> None:
        self._open_date_tab()
        self._select(self.canon1, self.scan)
        self._choose_set()
        self.assertTrue(self.window.date_shift_box.isHidden())
        picker = self.window.date_set_picker
        picker.date_edit.setDate(datetime(1987, 6, 1).date())
        picker.hour_box.setCurrentIndex(13)
        picker.minute_box.setCurrentIndex(0)
        picker.second_box.setCurrentIndex(0)

        self.assertEqual(picker.am_pm_label.text(), "pm")
        self.assertEqual(self.window.date_apply_button.text(), "Set Date on 2 Photos")
        QTest.mouseClick(self.window.date_apply_button, Qt.LeftButton)

        for path in (self.canon1, self.scan):
            self.assertEqual(self.tags[path]["DateTimeOriginal"], "1987:06:01 13:00:00")

    # --- Time zone ------------------------------------------------------------

    def _reload(self) -> None:
        """Read the photos again after changing their tags in the test (the
        files themselves don't change, so the metadata cache would answer)."""
        self.window.workflow.metadata_cache.forget(list(self.tags))
        self.window.populate_list()

    def _choose_zone(self, key: str) -> None:
        """Pick a time zone in the drop-down, as the user would."""
        box = self.window.date_reference_picker.zone_box
        index = box.findData(key)
        box.setCurrentIndex(index)
        box.activated.emit(index)

    def test_time_zone_is_blank_until_a_photo_is_selected(self) -> None:
        self._open_date_tab()
        for picker in (self.window.date_reference_picker, self.window.date_set_picker):
            self.assertEqual(picker.zone_box.currentText(), "")
            self.assertFalse(picker.zone_box.isEnabled())

    def test_time_zone_can_be_chosen_for_photos_without_a_date(self) -> None:
        self._open_date_tab()
        self._select(self.scan)
        self.assertTrue(self.window.date_reference_picker.zone_box.isEnabled())
        self.assertEqual(self.window.date_reference_picker.zone_box.currentText(), "No time zone")

    def test_photos_without_a_zone_default_to_no_time_zone(self) -> None:
        self._open_date_tab()
        self._select(self.canon1)
        box = self.window.date_reference_picker.zone_box
        self.assertEqual(box.currentText(), "No time zone")
        self.assertFalse(box.property("mixed"))

    def test_choosing_a_zone_gives_it_to_the_photos(self) -> None:
        self._open_date_tab()
        self._select(self.canon1)
        self._choose_shift()

        self._choose_zone("eastern")

        # No zone before: the clock time stays and the photo gets the zone.
        self.assertEqual(self.window.date_reference_picker.value(), datetime(2026, 10, 3, 9, 14, 2))
        self.assertEqual(self._change_rows()[0][2], "→  10/03/2026 9:14:02am EDT")
        QTest.mouseClick(self.window.date_apply_button, Qt.LeftButton)
        self.assertEqual(self.tags[self.canon1]["OffsetTimeOriginal"], "-04:00")
        self.assertEqual(self.tags[self.canon1]["DateTimeOriginal"], "2026:10:03 09:14:02")

        # Undo removes the zone again.
        self.window.undo_action.trigger()
        self.assertNotIn("OffsetTimeOriginal", self.tags[self.canon1])

    def test_changing_the_zone_keeps_the_same_moment(self) -> None:
        self.tags[self.phone]["OffsetTimeOriginal"] = "-06:00"
        self._reload()
        self._open_date_tab()
        self._select(self.phone)
        self._choose_shift()
        self.assertEqual(self.window.date_reference_picker.zone_box.currentData(), "mountain")
        self.assertEqual(self.window.date_reference_detail.text(), "Current Date: 10/03/2026 10:16:12am MDT")

        self._choose_zone("eastern")

        self.assertEqual(self.window.date_reference_picker.value(), datetime(2026, 10, 3, 12, 16, 12))
        QTest.mouseClick(self.window.date_apply_button, Qt.LeftButton)
        self.assertEqual(self.tags[self.phone]["DateTimeOriginal"], "2026:10:03 12:16:12")
        self.assertEqual(self.tags[self.phone]["OffsetTimeOriginal"], "-04:00")

    def test_mixed_zones_show_in_red_with_a_warning(self) -> None:
        self.tags[self.phone]["OffsetTimeOriginal"] = "-06:00"
        self.tags[self.canon1]["OffsetTimeOriginal"] = "-04:00"
        self._reload()
        self._open_date_tab()
        self._select(self.phone, self.canon1)

        box = self.window.date_reference_picker.zone_box
        self.assertTrue(box.property("mixed"))
        self.assertIn("more than one time zone", box.toolTip())
        # Left alone, each photo keeps its own zone.
        self._set_corrected_time(datetime(2026, 10, 3, 9, 15, 2))
        QTest.mouseClick(self.window.date_apply_button, Qt.LeftButton)
        self.assertEqual(self.tags[self.phone]["OffsetTimeOriginal"], "-06:00")
        self.assertEqual(self.tags[self.canon1]["OffsetTimeOriginal"], "-04:00")

    # --- Failures ---------------------------------------------------------------

    def test_a_failed_photo_stays_selected_and_is_reported(self) -> None:
        self._open_date_tab()
        self._select(self.canon1, self.canon2)
        self._choose_shift()
        self.writer.failures[self.canon2] = RuntimeError("read-only")
        self._set_corrected_time(datetime(2026, 10, 3, 10, 16, 12))
        shown = []
        with patch.object(self.window, "show_message", side_effect=lambda dialog, *_: shown.append(dialog.detailedText())):
            QTest.mouseClick(self.window.date_apply_button, Qt.LeftButton)

        self.assertEqual(self.window.get_selected_paths(), [self.canon2])
        self.assertEqual(shown, ["IMG_4102.CR3: read-only"])


if __name__ == "__main__":
    unittest.main()
