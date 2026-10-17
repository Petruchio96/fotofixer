import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QSettings, Qt
from PySide6.QtGui import QIcon, QKeySequence, QMouseEvent, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QListWidget, QMessageBox

from core.models import PhotoInfo
from gui.main_window import APP_VERSION, MainWindow
from gui.window_mixins import location_editor
from gui.window_mixins.photo_list import THUMBNAIL_PATH_ROLE
from gui.widgets.thumbnail_delegate import FADED_ROLE, PICK_DISABLED_ROLE, SOURCE_ROLE
from services.workflow_facade import PhotoWorkflowFacade


class FakeExifTool:
    def __init__(
        self,
        gps_by_path: dict[Path, tuple[float | None, float | None]] | None = None,
    ) -> None:
        self.writes: list[tuple[Path, float, float]] = []
        self.clears: list[Path] = []
        self.failures: dict[Path, Exception] = {}
        self.gps_by_path = gps_by_path if gps_by_path is not None else {}

    def write_gps(self, path: Path, latitude: float, longitude: float, altitude="keep") -> None:
        if path in self.failures:
            raise self.failures[path]
        self.writes.append((path, latitude, longitude))
        self.gps_by_path[path] = (latitude, longitude)

    def clear_gps(self, path: Path) -> None:
        if path in self.failures:
            raise self.failures[path]
        self.clears.append(path)
        self.gps_by_path[path] = (None, None)


class FakePhotoLoader:
    def __init__(self, gps_by_path: dict[Path, tuple[float | None, float | None]]) -> None:
        self.gps_by_path = gps_by_path
        self.calls: list[Path] = []

    def load_photo_info(self, path: Path) -> PhotoInfo:
        self.calls.append(path)
        latitude, longitude = self.gps_by_path[path]
        return PhotoInfo(
            path=path,
            file_type=path.suffix.upper().lstrip("."),
            current_latitude=latitude,
            current_longitude=longitude,
        )


class FakeThumbnailLoader:
    def cached_icon(self, path: Path, has_gps: bool = False):
        return None

    def load_images(self, paths: list[Path]) -> dict:
        return {path: None for path in paths}

    def icon_from_image(self, path: Path, has_gps: bool, image) -> QIcon:
        return self.load_icon(path, has_gps)

    def fallback_icon_for(self, has_gps: bool) -> QIcon:
        return self.load_icon(Path("fallback"), has_gps)

    def load_icon(self, path: Path, has_gps: bool = False) -> QIcon:
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.blue if has_gps else Qt.lightGray)
        return QIcon(pixmap)


def _choosing(chosen):
    """Stand-in for _pick_photo_files / _pick_photo_file: "chooses" at once."""
    return lambda _title, on_chosen, **_options: on_chosen(chosen)


class MainWindowSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        # Use a throwaway settings file so tests never read or change the
        # user's real preferences.
        settings_dir = tempfile.TemporaryDirectory()
        self.addCleanup(settings_dir.cleanup)
        self.settings_path = Path(settings_dir.name) / "settings.ini"
        self.settings = QSettings(str(self.settings_path), QSettings.IniFormat)

        self.window = MainWindow(settings=self.settings)
        # Run background loading immediately, so these tests can check results
        # right after each action. Background behavior is tested separately.
        self.window.background.run_inline = True
        self.window.show()

        self.source_path = Path("/tmp/source.jpg")
        self.paths = [
            Path("/tmp/photo-one.jpg"),
            Path("/tmp/photo-two.jpg"),
        ]
        self.location = (40.486325, -111.813415)
        self.gps_by_path = {
            self.source_path: (40.486325, -111.813415),
            self.paths[0]: (None, None),
            self.paths[1]: (None, None),
        }

        self.window.exiftool = FakeExifTool(self.gps_by_path)
        self.window.loader = FakePhotoLoader(self.gps_by_path)
        self.window.workflow = PhotoWorkflowFacade(
            loader=self.window.loader,
            writer=self.window.exiftool,
        )
        self.window.thumbnail_loader = FakeThumbnailLoader()
        self.window.session.selected_paths = list(self.paths)
        self.window.populate_list()

    def tearDown(self) -> None:
        self.window.close()

    def _photo_items(self) -> list:
        # Group headings sit between photos in the grid; skip them.
        list_widget = self.window.list_widget
        return [
            list_widget.item(row)
            for row in range(list_widget.count())
            if list_widget.item(row).data(THUMBNAIL_PATH_ROLE) is not None
        ]

    def _visible_paths(self) -> list[Path]:
        return [
            Path(item.data(THUMBNAIL_PATH_ROLE))
            for item in self._photo_items()
            if not item.isHidden()
        ]

    def _select_index(self, index: int, clear: bool = True) -> None:
        """Select the index-th photo in the grid (headings not counted)."""
        if clear:
            self.window.list_widget.clearSelection()
        item = self._photo_items()[index]
        item.setSelected(True)
        self.window.update_details_panel()

    def _select_paths(self, paths: list[Path]) -> None:
        self.window.select_browser_paths(paths)

    def _set_location(self, latitude: float, longitude: float) -> None:
        self.window.set_location_fields(str(latitude), str(longitude))

    def _set_clipboard(self, text: str) -> None:
        """Put text on the clipboard and wait for the Paste button to follow it."""
        QApplication.clipboard().setText(text)
        self._wait_for_clipboard_check()

    def _wait_for_clipboard_check(self) -> None:
        # The Paste button re-checks the clipboard a moment after it changes
        # (and again while another program holds it), not at once.
        while self.window._clipboard_check_timer.isActive():
            QTest.qWait(20)

    def _new_location(self):
        location = self.window._build_inspector_state().new_location
        return None if location is None else (location.latitude, location.longitude)

    def _assert_coordinates_almost_equal(self, actual, expected) -> None:
        self.assertAlmostEqual(actual[0], expected[0], places=12)
        self.assertAlmostEqual(actual[1], expected[1], places=12)

    # --- Layout and menus -------------------------------------------------

    def test_window_builds_expected_panels(self) -> None:
        self.assertEqual(self.window.add_photos_button.text(), "Add Photos")
        self.assertEqual(self.window.clear_list_button.text(), "Clear List")
        self.assertEqual(self.window.open_action.text(), "Add Photos...")
        self.assertEqual(self.window.clear_list_action.text(), "Clear List")
        self.assertEqual(self.window.editor_tabs.count(), 2)
        self.assertEqual(self.window.editor_tabs.tabText(0), "Location")
        self.assertEqual(self.window.editor_tabs.tabText(1), "Date && Time")
        # Apply is the only orange (main action) button; Remove GPS has its own
        # destructive style.
        self.assertEqual(self.window.apply_button.objectName(), "accentButton")
        self.assertEqual(self.window.remove_gps_button.objectName(), "removeGpsButton")
        self.assertNotEqual(self.window.add_photos_button.objectName(), "accentButton")
        self.assertNotEqual(self.window.paste_coordinates_button.objectName(), "accentButton")
        self.assertEqual(self.window.paste_coordinates_button.text(), "Paste")
        self.assertEqual(
            self.window.location_from_photo_button.text(), "From a Photo on Your Computer"
        )
        self.assertEqual(
            self.window.pick_location_button.text(), "From a Photo in the Photo List"
        )
        self.assertEqual(self.window.clear_location_button.text(), "Clear")
        # The platform decides the Quit shortcut: Ctrl+Q on most Linux
        # desktops, Cmd+Q on macOS, and none on Windows (Alt+F4 is built in).
        self.assertEqual(
            self.window.exit_action.shortcuts(),
            QKeySequence.keyBindings(QKeySequence.StandardKey.Quit),
        )
        self.assertEqual(self.window.undo_action.text(), "Undo")
        self.assertFalse(self.window.undo_action.isEnabled())
        self.assertIn(
            self.window.undo_action.shortcuts()[0],
            QKeySequence.keyBindings(QKeySequence.StandardKey.Undo),
        )
        self.assertEqual(self.window.redo_action.text(), "Redo")
        self.assertFalse(self.window.redo_action.isEnabled())
        self.assertIn(
            self.window.redo_action.shortcuts()[0],
            QKeySequence.keyBindings(QKeySequence.StandardKey.Redo),
        )
        self.assertEqual(self.window.copy_action.text(), "Copy GPS Coordinates")
        self.assertEqual(self.window.paste_action.text(), "Paste Coordinates")
        self.assertEqual(self.window.select_all_action.text(), "Select All Photos")

    def test_initial_inspector_with_nothing_selected(self) -> None:
        self.assertEqual(self.window.selection_title_label.text(), "No Photos Selected")
        self.assertFalse(self.window.apply_button.isEnabled())
        self.assertEqual(self.window.apply_button.text(), "Apply Location to Selected Photos")
        self.assertEqual(
            self.window.apply_hint_label.text(),
            "Select the photos to change in the Photo List.",
        )
        self.assertFalse(self.window.remove_gps_button.isEnabled())
        self.assertTrue(self.window.copy_location_button.isHidden())
        self.assertTrue(self.window.source_card.isHidden())
        self.assertTrue(self.window.pick_banner.isHidden())
        # The status row under the grid only shows up with something to say.
        self.assertTrue(self.window.loading_indicator.isHidden())

    def test_about_action_opens_versioned_dialog(self) -> None:
        with patch("gui.main_window.QMessageBox.show") as show_mock:
            self.window.show_about_dialog()

        show_mock.assert_called_once()
        # Shown without blocking, but nothing else can be used meanwhile.
        self.assertEqual(self.window._open_messages[0].windowModality(), Qt.ApplicationModal)

    def test_about_dialog_uses_clickable_external_repository_link(self) -> None:
        about_dialog = self.window._build_about_dialog()
        # macOS hides message box titles, so Qt reports an empty title there.
        if sys.platform != "darwin":
            self.assertIn(APP_VERSION, about_dialog.windowTitle())
        self.assertFalse(about_dialog.iconPixmap().isNull())
        link_label = about_dialog.findChild(QLabel, "aboutRepositoryLink")
        self.assertIsNotNone(link_label)
        self.assertIn(APP_VERSION, link_label.text())
        self.assertEqual(link_label.textFormat(), Qt.RichText)
        self.assertEqual(link_label.textInteractionFlags(), Qt.TextBrowserInteraction)
        self.assertTrue(link_label.openExternalLinks())
        self.assertGreaterEqual(link_label.minimumWidth(), 360)
        self.assertGreaterEqual(about_dialog.minimumWidth(), 520)
        self.assertIn("FotoFixer", link_label.text())
        self.assertIn(APP_VERSION, link_label.text())
        self.assertIn(
            '<a href="https://github.com/Petruchio96/fotofixer">',
            link_label.text(),
        )

    # --- Selecting and removing photos -----------------------------------

    def test_select_all_and_deselect_all_buttons_work(self) -> None:
        self.window.select_all_button.click()
        self.assertEqual(self.window.get_selected_paths(), self.paths)
        self.assertEqual(self.window.selection_title_label.text(), "2 Photos Selected")
        # Everything shown is selected, so Select All has nothing left to do.
        self.assertFalse(self.window.select_all_button.isEnabled())

        self.window.deselect_all_button.click()
        self.assertEqual(self.window.get_selected_paths(), [])
        self.assertEqual(self.window.selection_title_label.text(), "No Photos Selected")

    def test_selection_bar_turns_orange_only_with_a_selection(self) -> None:
        window = self.window
        self.assertFalse(window.selection_bar.property("active"))
        self.assertEqual(window.selection_count_label.text(), "0 selected")
        self.assertFalse(window.deselect_all_button.isEnabled())
        self.assertFalse(window.remove_from_list_button.isEnabled())

        self._select_index(0)

        self.assertTrue(window.selection_bar.property("active"))
        self.assertEqual(window.selection_count_label.text(), "1 selected")
        self.assertTrue(window.deselect_all_button.isEnabled())
        self.assertTrue(window.remove_from_list_button.isEnabled())

    def test_remove_from_list_removes_selected_photos_only(self) -> None:
        self._select_index(1)

        self.window.remove_from_list_button.click()

        self.assertEqual(self.window.session.selected_paths, [self.paths[0]])

    def test_remove_from_list_does_nothing_without_a_selection(self) -> None:
        self.window.remove_selected_from_list()

        self.assertEqual(self.window.session.selected_paths, self.paths)

    def test_delete_key_removes_selected_photos_from_list(self) -> None:
        self._select_index(0)
        self.window.list_widget.setFocus()

        QTest.keyClick(self.window.list_widget, Qt.Key_Delete)

        self.assertEqual(self.window.session.selected_paths, [self.paths[1]])

    def test_clear_list_empties_the_list(self) -> None:
        self.window.clear_list_button.click()

        self.assertEqual(self.window.session.selected_paths, [])
        self.assertEqual(self.window.list_widget.count(), 0)
        self.assertFalse(self.window.clear_list_button.isEnabled())
        self.assertFalse(self.window.clear_list_action.isEnabled())
        self.assertIn("Add Photos", self.window.list_widget.empty_message)

    def test_file_menu_clear_list_clears_all_photos(self) -> None:
        self.window.clear_list_action.trigger()

        self.assertEqual(self.window.session.selected_paths, [])
        self.assertFalse(self.window.clear_list_action.isEnabled())

    def test_add_photos_adds_to_the_list_and_skips_photos_already_in_it(self) -> None:
        new_path = Path("/tmp/new-photo.jpg")
        self.gps_by_path[new_path] = (None, None)
        self._select_index(0)

        self._choose_photos([self.paths[1], new_path])

        self.assertEqual(self.window.session.selected_paths, [*self.paths, new_path])
        # What was selected stays selected.
        self.assertEqual(self.window.get_selected_paths(), [self.paths[0]])
        self.assertIn("Added 1 photo.", self.window.browser_hint.text())
        self.assertIn("1 was already in the list.", self.window.browser_hint.text())
        self.assertFalse(self.window.loading_indicator.isHidden())

    def test_add_photos_with_only_photos_already_in_the_list(self) -> None:
        self._choose_photos([self.paths[0]])

        self.assertEqual(self.window.session.selected_paths, self.paths)
        self.assertIn("already in the list", self.window.browser_hint.text())

    def test_every_button_has_a_hover_hint(self) -> None:
        from PySide6.QtWidgets import QPushButton

        missing = [
            button.text() or button.objectName()
            for button in self.window.findChildren(QPushButton)
            if not button.toolTip()
        ]
        self.assertEqual(missing, [])

    # --- Click selection ------------------------------------------------------

    def _load_photos(self, count: int, with_gps: set[int] = frozenset()) -> list[Path]:
        paths = [Path(f"/tmp/click-{index}.jpg") for index in range(count)]
        for index, path in enumerate(paths):
            self.gps_by_path[path] = (41.0, -112.0) if index in with_gps else (None, None)
        self.window.session.selected_paths = list(paths)
        self.window.populate_list()
        return paths

    def _press(self, path: Path, modifier=Qt.NoModifier) -> None:
        self._click_item(path, Qt.LeftButton) if modifier == Qt.NoModifier else QTest.mouseClick(
            self.window.list_widget.viewport(),
            Qt.LeftButton,
            modifier,
            self.window.list_widget.visualItemRect(self._item_for(path)).center(),
        )

    def test_click_adds_and_click_again_removes(self) -> None:
        paths = self._load_photos(3)

        self._press(paths[0])
        self._press(paths[2])
        self.assertEqual(self.window.get_selected_paths(), [paths[0], paths[2]])
        self.assertEqual(self.window.selection_title_label.text(), "2 Photos Selected")

        self._press(paths[0])
        self.assertEqual(self.window.get_selected_paths(), [paths[2]])

    def test_ctrl_click_works_like_click(self) -> None:
        paths = self._load_photos(3)

        self._press(paths[0], Qt.ControlModifier)
        self._press(paths[1], Qt.ControlModifier)
        self._press(paths[0], Qt.ControlModifier)

        self.assertEqual(self.window.get_selected_paths(), [paths[1]])

    def test_shift_click_adds_range_from_last_clicked_photo(self) -> None:
        paths = self._load_photos(6)
        self._press(paths[5])  # selected elsewhere; must stay selected
        self._press(paths[1])

        self._press(paths[3], Qt.ShiftModifier)

        self.assertEqual(
            self.window.get_selected_paths(),
            [paths[1], paths[2], paths[3], paths[5]],
        )

    def test_shift_click_range_skips_hidden_photos(self) -> None:
        paths = self._load_photos(5, with_gps={2})
        self.window.set_grid_filter("needs")
        self._press(paths[0])

        self._press(paths[4], Qt.ShiftModifier)

        self.assertEqual(self.window.get_selected_paths(), [paths[0], paths[1], paths[3], paths[4]])
        self.assertFalse(self._item_for(paths[2]).isSelected())

    def test_shift_click_with_no_earlier_click_selects_just_that_photo(self) -> None:
        paths = self._load_photos(4)

        self._press(paths[2], Qt.ShiftModifier)

        self.assertEqual(self.window.get_selected_paths(), [paths[2]])

    def test_clicking_empty_space_keeps_the_selection(self) -> None:
        paths = self._load_photos(2)
        self._press(paths[0])
        viewport = self.window.list_widget.viewport()

        QTest.mouseClick(viewport, Qt.LeftButton, Qt.NoModifier, viewport.rect().bottomRight() - QPoint(5, 5))

        self.assertEqual(self.window.get_selected_paths(), [paths[0]])

    def test_dragging_from_empty_space_selects_nothing(self) -> None:
        paths = self._load_photos(4)
        grid = self.window.list_widget
        viewport = grid.viewport()
        self._press(paths[3])
        first = grid.visualItemRect(self._item_for(paths[0]))
        second = grid.visualItemRect(self._item_for(paths[1]))
        # Start in empty space just left of the first photo's tile, drag over two.
        start = QPoint(2, first.center().y())
        end = second.center()

        QTest.mousePress(viewport, Qt.LeftButton, Qt.NoModifier, start)
        move = QMouseEvent(QEvent.MouseMove, QPointF(end), QPointF(viewport.mapToGlobal(end)),
                           Qt.NoButton, Qt.LeftButton, Qt.NoModifier)
        QApplication.sendEvent(viewport, move)
        QTest.mouseRelease(viewport, Qt.LeftButton, Qt.NoModifier, end)

        self.assertEqual(self.window.get_selected_paths(), [paths[3]])

    def test_ctrl_a_selects_only_photos_shown(self) -> None:
        paths = self._load_photos(3, with_gps={1})
        self.window.set_grid_filter("needs")
        self.window.list_widget.setFocus()

        QTest.keyClick(self.window.list_widget, Qt.Key_A, Qt.ControlModifier)

        self.assertEqual(self.window.get_selected_paths(), [paths[0], paths[2]])

    def test_arrow_keys_move_focus_and_space_toggles(self) -> None:
        paths = self._load_photos(3)
        grid = self.window.list_widget
        self._press(paths[0])
        grid.setFocus()

        QTest.keyClick(grid, Qt.Key_Right)

        self.assertEqual(self.window.get_selected_paths(), [paths[0]])
        self.assertEqual(grid.currentItem(), self._item_for(paths[1]))

        QTest.keyClick(grid, Qt.Key_Space)
        self.assertEqual(self.window.get_selected_paths(), [paths[0], paths[1]])

    # --- File pickers: where they open --------------------------------------

    def test_photo_picker_starts_in_the_systems_pictures_folder(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        moved_pictures = Path(temp_dir.name) / "My Pictures"
        moved_pictures.mkdir()

        with patch(
            "gui.main_window.QStandardPaths.writableLocation",
            return_value=str(moved_pictures),
        ):
            self.assertEqual(self.window._default_photo_directory(), moved_pictures)

    def test_photo_picker_falls_back_when_system_folder_is_missing(self) -> None:
        with patch(
            "gui.main_window.QStandardPaths.writableLocation",
            return_value="/does/not/exist",
        ):
            folder = self.window._default_photo_directory()

        self.assertIn(folder, (Path.home() / "Pictures", Path.home()))

    def _photo_folder(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        folder = Path(temp_dir.name) / "trip"
        folder.mkdir()
        return folder

    def _fake_picker(
        self,
        *,
        chosen: list[Path],
        folder: Path | None,
        accept: bool = True,
        chosen_folders: list[Path] = (),
        include_subfolders: bool | None = None,
    ):
        """
        Stand in for the Add Photos picker: records how it was opened and
        "chooses" the given photos and folders in the given folder.
        include_subfolders None leaves the checkbox as the picker opened it.
        """
        opened: list[dict] = []

        class FakeSignal:
            def __init__(self) -> None:
                self.slots = []

            def connect(self, slot) -> None:
                self.slots.append(slot)

        class FakePicker:
            def __init__(self, parent, **kwargs) -> None:
                opened.append(kwargs)
                self.current_folder = folder
                self.finished = FakeSignal()
                self._include = (
                    kwargs.get("include_subfolders", False)
                    if include_subfolders is None
                    else include_subfolders
                )

            def setWindowModality(self, modality) -> None:
                pass

            def show(self) -> None:
                # Closes at once, as if the user chose (or cancelled).
                result = QDialog.Accepted if accept else QDialog.Rejected
                for slot in self.finished.slots:
                    slot(result)

            def selected_paths(self):
                return list(chosen)

            def selected_folders(self):
                return list(chosen_folders)

            def include_subfolders(self):
                return self._include

        return patch("gui.main_window.PhotoPickerDialog", FakePicker), opened

    def test_pickers_open_in_the_folder_photos_were_last_chosen_from(self) -> None:
        folder = self._photo_folder()
        picker, opened = self._fake_picker(chosen=[folder / "a.jpg"], folder=folder)

        with picker, patch.object(
            self.window, "_default_photo_directory", return_value=Path("/pictures")
        ):
            chosen = []
            self.window._pick_photo_files("Add Photos", chosen.append)
            self.window._pick_photo_files("Add Photos", chosen.append)
            self.window._pick_photo_file("Use the Location from a Photo", chosen.append)

        self.assertEqual(
            [entry["start_folder"] for entry in opened], [Path("/pictures"), folder, folder]
        )
        # Choosing a photo's location uses the picker's one-photo mode.
        self.assertEqual([entry["single"] for entry in opened], [False, False, True])
        self.assertEqual(chosen, [[folder / "a.jpg"], [folder / "a.jpg"], folder / "a.jpg"])

    def test_add_photos_picker_knows_the_photos_already_in_the_list(self) -> None:
        picker, opened = self._fake_picker(chosen=[], folder=None, accept=False)
        chosen = []
        with picker:
            self.window._pick_photo_files("Add Photos", chosen.append)

        # Cancelled: nothing chosen.
        self.assertEqual(chosen, [])

        self.assertEqual(opened[0]["title"], "Add Photos")
        self.assertEqual(opened[0]["in_list"], set(self.paths))

    def _folder_tree(self) -> Path:
        """trip/a.jpg, trip/b.jpg, trip/day2/c.jpg."""
        folder = self._photo_folder()
        (folder / "day2").mkdir()
        for path in (folder / "a.jpg", folder / "b.jpg", folder / "day2" / "c.jpg"):
            path.write_bytes(b"")
        return folder

    def test_choosing_a_folder_adds_the_photos_in_it(self) -> None:
        folder = self._folder_tree()
        loose = Path("/tmp/loose.jpg")
        picker, _opened = self._fake_picker(
            chosen=[loose], chosen_folders=[folder], folder=folder.parent, include_subfolders=False
        )

        chosen = []
        with picker:
            self.window._pick_photo_files("Add Photos", chosen.append)

        # Photos chosen one by one first, then the folder's own photos.
        self.assertEqual(chosen, [[loose, folder / "a.jpg", folder / "b.jpg"]])

    def test_choosing_a_folder_with_subfolders_adds_every_photo_inside(self) -> None:
        folder = self._folder_tree()
        picker, _opened = self._fake_picker(
            chosen=[], chosen_folders=[folder], folder=folder.parent, include_subfolders=True
        )

        chosen = []
        with picker:
            self.window._pick_photo_files("Add Photos", chosen.append)

        self.assertEqual(chosen, [[folder / "a.jpg", folder / "b.jpg", folder / "day2" / "c.jpg"]])

    def test_choosing_a_folder_without_photos_says_so(self) -> None:
        folder = self._photo_folder()
        picker, _opened = self._fake_picker(chosen=[], chosen_folders=[folder], folder=folder.parent)

        chosen = []
        with picker:
            self.window._pick_photo_files("Add Photos", chosen.append)

        self.assertEqual(chosen, [])
        self.assertEqual(self.window._last_status_message, "No photos found in that folder.")

    def test_subfolders_checkbox_is_remembered_while_the_app_runs(self) -> None:
        picker, opened = self._fake_picker(chosen=[], folder=None, accept=False, include_subfolders=True)
        with picker:
            self.window._pick_photo_files("Add Photos", lambda _paths: None)
        later, opened_later = self._fake_picker(chosen=[], folder=None, accept=False)
        with later:
            self.window._pick_photo_files("Add Photos", lambda _paths: None)

        self.assertFalse(opened[0]["include_subfolders"])
        self.assertTrue(opened_later[0]["include_subfolders"])

        # Not saved: a new session starts with it off.
        reopened = MainWindow(settings=QSettings(str(self.settings_path), QSettings.IniFormat))
        self.addCleanup(reopened.close)
        self.assertFalse(reopened._picker_include_subfolders)

    def test_last_folder_is_remembered_between_sessions(self) -> None:
        folder = self._photo_folder()
        self.window._remember_photo_folder(folder)

        reopened = MainWindow(settings=QSettings(str(self.settings_path), QSettings.IniFormat))
        self.addCleanup(reopened.close)

        self.assertEqual(reopened._photo_picker_start_folder(), folder)

    def test_missing_last_folder_falls_back_to_pictures(self) -> None:
        self.window._remember_photo_folder(Path("/folder/that/was/deleted"))

        with patch.object(self.window, "_default_photo_directory", return_value=Path("/pictures")):
            self.assertEqual(self.window._photo_picker_start_folder(), Path("/pictures"))

    def test_cancelling_the_picker_remembers_the_folder_browsed_to(self) -> None:
        folder = self._photo_folder()
        picker, _opened = self._fake_picker(chosen=[], folder=folder, accept=False)

        chosen = []
        with picker:
            self.window._pick_photo_files("Add Photos", chosen.append)

        self.assertEqual(chosen, [])
        self.assertEqual(self.window._photo_picker_start_folder(), folder)

    # --- Show filter --------------------------------------------------------

    def test_show_filter_hides_photos_headings_and_counts(self) -> None:
        self.gps_by_path[self.paths[1]] = (41.0, -112.0)
        self.window.populate_list()
        self.assertEqual(self.window.grid_filter_buttons["all"].text(), "All (2)")
        self.assertEqual(self.window.grid_filter_buttons["needs"].text(), "Needs GPS (1)")
        self.assertEqual(self.window.grid_filter_buttons["has"].text(), "Has GPS (1)")

        self.window.set_grid_filter("needs")
        self.assertEqual(self._visible_paths(), [self.paths[0]])
        self.assertEqual(self._visible_headings(), ["Photos without GPS Coordinates (1)"])

        self.window.set_grid_filter("has")
        self.assertEqual(self._visible_paths(), [self.paths[1]])
        self.assertEqual(self._visible_headings(), ["Photos with GPS Coordinates (1)"])

        self.window.set_grid_filter("all")
        self.assertEqual(self._visible_paths(), self.paths)

    def _choose_photos(self, paths: list[Path]) -> None:
        with patch.object(self.window, "_pick_photo_files", side_effect=_choosing(paths)):
            self.window.add_photos_button.click()

    def test_loaded_photos_open_on_needs_gps(self) -> None:
        with_gps = Path("/tmp/has-gps.jpg")
        self.gps_by_path[with_gps] = (41.0, -112.0)
        self.window.clear_photo_list()

        self._choose_photos([*self.paths, with_gps])

        self.assertEqual(self.window._grid_filter, "needs")
        self.assertTrue(self.window.grid_filter_buttons["needs"].isChecked())
        self.assertEqual(self._visible_paths(), self.paths)

    def test_loaded_photos_open_on_all_when_none_need_gps(self) -> None:
        self.window.clear_photo_list()
        self.window.set_grid_filter("needs")
        with_gps = Path("/tmp/has-gps.jpg")
        self.gps_by_path[with_gps] = (41.0, -112.0)

        self._choose_photos([with_gps])

        self.assertEqual(self.window._grid_filter, "all")
        self.assertTrue(self.window.grid_filter_buttons["all"].isChecked())

    def test_adding_to_a_list_keeps_the_show_filter(self) -> None:
        self.window.set_grid_filter("has")
        new_path = Path("/tmp/new-photo.jpg")
        self.gps_by_path[new_path] = (None, None)

        self._choose_photos([new_path])

        self.assertEqual(self.window._grid_filter, "has")

    def test_filter_is_kept_when_the_grid_redraws_after_apply(self) -> None:
        self.window.set_grid_filter("all")
        self.window.select_all_photos()
        self._set_location(*self.location)

        self.window.apply_coordinates_to_selected()

        self.assertEqual(self.window._grid_filter, "all")

    def test_select_all_only_selects_photos_shown(self) -> None:
        self.gps_by_path[self.paths[1]] = (41.0, -112.0)
        self.window.populate_list()
        self.window.set_grid_filter("needs")

        self.window.select_all_photos()

        self.assertEqual(self.window.get_selected_paths(), [self.paths[0]])

    def test_hidden_photos_are_never_acted_on(self) -> None:
        self.gps_by_path[self.paths[1]] = (41.0, -112.0)
        self.window.populate_list()
        # Ctrl+A in the grid selects everything, including hidden items.
        self.window.set_grid_filter("needs")
        self.window.list_widget.selectAll()

        self.assertEqual(self.window.get_selected_paths(), [self.paths[0]])

    def test_filter_shows_message_when_nothing_matches(self) -> None:
        self.window.set_grid_filter("has")

        self.assertEqual(self._visible_paths(), [])
        self.assertEqual(self.window.list_widget.empty_message, "None of these photos have GPS yet.")

        self.window.set_grid_filter("all")
        self.assertEqual(self.window.list_widget.empty_message, "")

    # --- Inspector ------------------------------------------------------------

    def test_single_photo_with_gps_offers_copy(self) -> None:
        self.gps_by_path[self.paths[0]] = (41.0, -112.0)
        self.window.populate_list()

        self._select_paths([self.paths[0]])

        self.assertEqual(self.window.selection_title_label.text(), "1 Photo Selected")
        self.assertEqual(
            self.window.selection_gps_label.text(), "photo-one.jpg · GPS: 41.000000, -112.000000"
        )
        self.assertFalse(self.window.copy_location_button.isHidden())
        self.assertTrue(self.window.copy_location_button.isEnabled())
        self.assertTrue(self.window.copy_action.isEnabled())

        self.window.copy_location_button.click()
        self.assertEqual(QApplication.clipboard().text(), "41.000000, -112.000000")
        # Selecting a photo never fills New Location by itself.
        self.assertIsNone(self._new_location())

    def test_single_photo_without_gps_cannot_copy(self) -> None:
        self._select_paths([self.paths[0]])

        self.assertEqual(self.window.selection_gps_label.text(), "photo-one.jpg · No GPS")
        self.assertFalse(self.window.copy_location_button.isEnabled())
        self.assertFalse(self.window.copy_action.isEnabled())

    def test_multiple_selection_summarizes_gps(self) -> None:
        self.gps_by_path[self.paths[0]] = (41.0, -112.0)
        self.window.populate_list()

        self.window.select_all_photos()

        self.assertEqual(self.window.selection_title_label.text(), "2 Photos Selected")
        self.assertEqual(self.window.selection_gps_label.text(), "1 without GPS · 1 with GPS")
        self.assertTrue(self.window.copy_location_button.isHidden())
        self.assertFalse(self.window.copy_action.isEnabled())
        self.assertEqual(self.window.remove_gps_button.text(), "Remove GPS from Selected 1 Photo")
        self.assertTrue(self.window.remove_gps_button.isEnabled())

    def test_apply_button_label_hint_and_overwrite_warning(self) -> None:
        self.gps_by_path[self.paths[0]] = (41.0, -112.0)
        self.window.populate_list()
        self.window.select_all_photos()
        self.assertFalse(self.window.apply_button.isEnabled())
        self.assertIn("Set a new location", self.window.apply_hint_label.text())

        self._set_location(*self.location)

        self.assertTrue(self.window.apply_button.isEnabled())
        self.assertEqual(self.window.apply_button.text(), "Apply Location to 2 Photos")
        self.assertEqual(
            self.window.apply_hint_label.text(),
            "1 photo already has GPS, which will be replaced.",
        )
        self.assertEqual(self.window.apply_hint_label.property("tone"), "warning")

    # --- Location source: pick from the Photo List, right-click, card -----

    def _item_for(self, path: Path):
        return self.window._grid_items_by_path[str(path)]

    def _click_item(self, path: Path, button=Qt.LeftButton) -> None:
        grid = self.window.list_widget
        center = grid.visualItemRect(self._item_for(path)).center()
        QTest.mouseClick(grid.viewport(), button, Qt.NoModifier, center)

    # --- A photo is the source or being changed, never both ---------------

    def _two_with_gps(self) -> None:
        self.gps_by_path[self.paths[0]] = (41.0, -112.0)
        self.gps_by_path[self.paths[1]] = (42.0, -113.0)
        self.window.populate_list()

    def test_the_location_source_cannot_be_selected(self) -> None:
        self._two_with_gps()
        self._select_paths([self.paths[0]])
        self.window.use_location_from_path(self.paths[0])

        # Becoming the source deselected it; clicks and Select All skip it.
        self.assertEqual(self.window.get_selected_paths(), [])
        self._click_item(self.paths[0])
        self.assertEqual(self.window.get_selected_paths(), [])
        self.window.select_all_photos()
        self.assertEqual(self.window.get_selected_paths(), [self.paths[1]])

    def test_the_source_is_selectable_again_once_released(self) -> None:
        self._two_with_gps()
        for release in (
            lambda: self.window.source_card_clear.click(),
            lambda: self.window.clear_location_button.click(),
            lambda: self.window.latitude_input.setText("40.1"),
            lambda: self.window.use_location_from_path(self.paths[1]),
        ):
            with self.subTest():
                self.window.list_widget.clearSelection()
                self.window.use_location_from_path(self.paths[0])
                release()
                self._click_item(self.paths[0])
                self.assertIn(self.paths[0], self.window.get_selected_paths())

    def test_clicking_the_source_then_releasing_it_leaves_it_deselected(self) -> None:
        # Clicking the source used to record a hidden selection that showed
        # up once Clear (or another way) made it selectable again.
        self._two_with_gps()
        for release in (
            lambda: self.window.clear_location_button.click(),
            lambda: self.window.use_location_from_path(self.paths[1]),
        ):
            with self.subTest():
                self.window.list_widget.clearSelection()
                self.window.use_location_from_path(self.paths[0])
                self._click_item(self.paths[0])
                release()
                self.assertNotIn(self.paths[0], self.window.get_selected_paths())

    def test_a_selected_photo_can_be_picked_as_the_source_and_is_deselected(self) -> None:
        self._two_with_gps()
        self._select_paths([self.paths[0], self.paths[1]])

        self.window.start_picking_location()
        self.assertIsNone(self._item_for(self.paths[0]).data(PICK_DISABLED_ROLE), "selected photos can be picked")
        self.window.pick_location_from_item(self._item_for(self.paths[0]))

        self.assertFalse(self.window.is_picking_location)
        self.assertEqual(self.window._location_source, self.paths[0])
        self.assertEqual(self.window.get_selected_paths(), [self.paths[1]], "the source is deselected, the rest stay")

    def test_pick_button_stays_on_when_every_photo_with_gps_is_selected(self) -> None:
        # A selected photo can be picked as the source (it is deselected then).
        self.gps_by_path[self.paths[0]] = (41.0, -112.0)
        self.window.populate_list()
        self._select_paths([self.paths[0]])
        self.assertTrue(self.window.pick_location_button.isEnabled())

    def test_the_coordinate_fields_keep_their_hint_after_edits(self) -> None:
        from gui.widgets.editor_panel import COORDINATE_FIELD_TIP
        self.assertEqual(self.window.latitude_input.toolTip(), COORDINATE_FIELD_TIP)
        self.window.latitude_input.setText("40.5")
        self.window.validate_latitude_field()
        self.assertEqual(self.window.latitude_input.toolTip(), COORDINATE_FIELD_TIP, "a valid value keeps the hint")
        self.window.latitude_input.setText("not a latitude")
        self.window.validate_latitude_field()
        self.assertIn("Invalid latitude", self.window.latitude_input.toolTip())
        self.window.clear_location_button.click()
        self.assertEqual(self.window.latitude_input.toolTip(), COORDINATE_FIELD_TIP, "Clear brings the hint back")
        self.assertEqual(self.window.longitude_input.toolTip(), COORDINATE_FIELD_TIP)

    def test_the_file_picker_offers_selected_photos_too(self) -> None:
        self._two_with_gps()
        self._select_paths([self.paths[0]])
        options = {}

        def picker(_title, _on_chosen, **kwargs):
            options.update(kwargs)

        with patch.object(self.window, "_pick_photo_file", side_effect=picker):
            self.window.location_from_photo_button.click()

        self.assertNotIn("blocked", options)

    def test_date_tab_time_source_stays_selectable(self) -> None:
        # The Date & Time tab keeps its own rules: the location source is
        # only off-limits on the Location tab.
        self._two_with_gps()
        self.window.use_location_from_path(self.paths[0])
        self.window.editor_tabs.setCurrentIndex(1)
        self.window.select_browser_paths([self.paths[0]])
        self.assertIn(self.paths[0], self.window.get_selected_paths())

    def test_pick_from_grid_sets_source_without_changing_selection(self) -> None:
        self.gps_by_path[self.paths[1]] = (41.0, -112.0)
        self.window.populate_list()
        self._select_paths([self.paths[0]])

        self.window.pick_location_button.click()
        self.assertTrue(self.window.is_picking_location)
        self.assertFalse(self.window.pick_banner.isHidden())

        self._click_item(self.paths[1])

        self.assertFalse(self.window.is_picking_location)
        self.assertTrue(self.window.pick_banner.isHidden())
        self.assertEqual(self._new_location(), (41.0, -112.0))
        self.assertEqual(self.window.get_selected_paths(), [self.paths[0]])
        self.assertFalse(self.window.source_card.isHidden())
        self.assertEqual(self.window.source_card_title.text(), "From photo-two.jpg")
        self.assertTrue(self._item_for(self.paths[1]).data(SOURCE_ROLE))
        self.assertFalse(self._item_for(self.paths[0]).data(SOURCE_ROLE))
        # Picking hid photo-one temporarily (Has GPS) but kept it selected.
        self.assertFalse(self._item_for(self.paths[0]).isHidden())
        self.assertEqual(self.window.selection_title_label.text(), "1 Photo Selected")

    def test_pick_mode_hides_and_dims_photos_without_gps(self) -> None:
        self.gps_by_path[self.paths[1]] = (41.0, -112.0)
        self.window.populate_list()

        self.window.pick_location_button.click()

        self.assertEqual(self.window.pick_location_button.text(), "Cancel")
        self.assertEqual(self._visible_paths(), [self.paths[1]])
        self.assertTrue(self._item_for(self.paths[0]).data(PICK_DISABLED_ROLE))
        self.assertFalse(self._item_for(self.paths[1]).data(PICK_DISABLED_ROLE))

        # Clicking empty grid space picks nothing.
        QTest.mouseClick(self.window.list_widget.viewport(), Qt.LeftButton, Qt.NoModifier,
                         self.window.list_widget.viewport().rect().bottomRight() - QPoint(5, 5))
        self.assertTrue(self.window.is_picking_location)
        self.assertIsNone(self._new_location())

    def test_pick_mode_locks_everything_but_the_allowed_controls(self) -> None:
        self.gps_by_path[self.paths[1]] = (41.0, -112.0)
        self.window.populate_list()
        self._select_paths([self.paths[0]])
        self._set_location(*self.location)
        self._set_clipboard("40.1, -111.2")

        self.window.start_picking_location()

        window = self.window
        for widget in (
            window.select_all_button,
            window.deselect_all_button,
            window.remove_from_list_button,
            window.grid_filter_buttons["needs"],
            window.latitude_input,
            window.longitude_input,
            window.paste_coordinates_button,
            window.location_from_photo_button,
            window.clear_location_button,
            window.apply_button,
            window.remove_gps_button,
        ):
            self.assertFalse(widget.isEnabled(), widget)
        for action in (window.select_all_action, window.paste_action, window.undo_action):
            self.assertFalse(action.isEnabled())
        # The view stays on Has GPS while picking.
        for button in window.grid_filter_buttons.values():
            self.assertFalse(button.isEnabled())
        for widget in (
            window.add_photos_button,
            window.clear_list_button,
            window.pick_location_button,
        ):
            self.assertTrue(widget.isEnabled(), widget)

        # The lock survives things that recompute button states.
        window.update_details_panel()
        self._set_clipboard("41.5, -112.5")
        self.assertFalse(window.apply_button.isEnabled())
        self.assertFalse(window.paste_coordinates_button.isEnabled())

        window.pick_location_button.click()  # Cancel

        self.assertFalse(window.is_picking_location)
        self.assertTrue(window.apply_button.isEnabled())
        self.assertTrue(window.select_all_button.isEnabled())
        for widget in (
            window.latitude_input,
            window.longitude_input,
            window.location_from_photo_button,
            window.source_card_clear,
            window.grid_filter_buttons["needs"],
            window.clear_location_button,
            window.deselect_all_button,
        ):
            self.assertTrue(widget.isEnabled(), widget)
        self.assertFalse(self._item_for(self.paths[0]).data(PICK_DISABLED_ROLE))

    def _give_all_photos_gps(self) -> None:
        self.gps_by_path[self.paths[0]] = (41.0, -112.0)
        self.gps_by_path[self.paths[1]] = (42.0, -113.0)
        self.window.populate_list()

    def test_picking_keeps_the_photos_selected_to_change(self) -> None:
        self.gps_by_path[self.paths[1]] = (41.0, -112.0)
        self.window.populate_list()
        self.window.set_grid_filter("needs")
        self._select_paths([self.paths[0]])

        self.window.start_picking_location()
        self.window.pick_location_from_item(self._item_for(self.paths[1]))

        self.assertEqual(self.window.get_selected_paths(), [self.paths[0]])

    def test_switching_views_keeps_the_selection(self) -> None:
        self.gps_by_path[self.paths[1]] = (41.0, -112.0)
        self.window.populate_list()
        self.window.set_grid_filter("needs")
        self._select_paths([self.paths[0]])

        self.window.set_grid_filter("has")
        # Hidden, but still selected and still counted as a photo to change.
        self.assertEqual(self.window.get_selected_paths(), [self.paths[0]])

        self.window.set_grid_filter("all")
        self.assertTrue(self._item_for(self.paths[0]).isSelected())
        self.assertEqual(self.window.get_selected_paths(), [self.paths[0]])

    # --- Only Show Selected Photos ------------------------------------------

    def test_only_selected_needs_a_selection_to_turn_on(self) -> None:
        button = self.window.only_selected_button
        self.assertFalse(button.isEnabled())

        self._select_paths([self.paths[0]])

        self.assertTrue(button.isEnabled())

    def test_only_selected_shows_the_selection(self) -> None:
        self._select_paths([self.paths[1]])

        self.window.only_selected_button.click()

        self.assertTrue(self.window.is_only_selected)
        self.assertEqual(self._visible_paths(), [self.paths[1]])
        # No view is shown as chosen, but the view buttons can be clicked.
        for button in self.window.grid_filter_buttons.values():
            self.assertFalse(button.isChecked())
            self.assertTrue(button.isEnabled())
        self.assertFalse(self.window.select_all_button.isEnabled())

        self.window.only_selected_button.click()

        self.assertFalse(self.window.is_only_selected)
        self.assertEqual(self._visible_paths(), self.paths)
        for button in self.window.grid_filter_buttons.values():
            self.assertTrue(button.isEnabled())

    def test_clicking_a_view_turns_only_selected_off(self) -> None:
        self.gps_by_path[self.paths[1]] = (41.0, -112.0)
        self.window.populate_list()
        self._select_paths([self.paths[0]])
        self.window.only_selected_button.click()

        self.window.grid_filter_buttons["has"].click()

        self.assertFalse(self.window.is_only_selected)
        self.assertFalse(self.window.only_selected_button.isChecked())
        self.assertEqual(self.window._grid_filter, "has")
        self.assertTrue(self.window.grid_filter_buttons["has"].isChecked())
        self.assertEqual(self._visible_paths(), [self.paths[1]])
        # The selection is kept.
        self.assertEqual(self.window.get_selected_paths(), [self.paths[0]])

    def test_group_divider_shows_only_between_two_groups(self) -> None:
        self.gps_by_path[self.paths[1]] = (41.0, -112.0)
        self.window.populate_list()
        gps_header = next(
            item for item in self.window._group_header_items
            if item.data(Qt.UserRole + 4) == "gps"
        )
        divider = self.window._group_header_divider(gps_header)

        self.window.set_grid_filter("all")
        self.assertFalse(divider.isHidden())

        self.window.set_grid_filter("has")
        self.assertTrue(divider.isHidden())

    def test_clicks_still_hit_photos_after_a_hidden_thumbnail_loads(self) -> None:
        paths = self._load_photos(6, with_gps={5})
        self.window.set_grid_filter("needs")
        grid = self.window.list_widget
        hidden = self._item_for(paths[5])
        first = self._item_for(paths[0])
        grid.doItemsLayout()
        QApplication.processEvents()
        # Give the hidden photo a real-looking (wide) thumbnail the way a
        # background batch does.
        wide = QPixmap(128, 60)
        wide.fill(Qt.darkGreen)
        self.window._pending_thumbnail_items = {str(paths[5]): (hidden, True)}
        self.window._thumbnail_total = 1
        with patch.object(
            self.window.thumbnail_loader, "icon_from_image", return_value=QIcon(wide)
        ):
            self.window._apply_thumbnail_batch(
                (self.window._thumbnail_generation, {paths[5]: None})
            )
        QApplication.processEvents()

        rect = grid.visualItemRect(first)
        self.assertIs(grid.itemAt(QPoint(rect.center().x(), rect.top() + 10)), first)

    def test_deselecting_in_only_selected_fades_the_photo_in_place(self) -> None:
        self._select_paths(self.paths)
        self.window.only_selected_button.click()
        item = self._item_for(self.paths[0])

        self._press(self.paths[0])

        self.assertFalse(item.isSelected())
        self.assertEqual(self._visible_paths(), self.paths)
        self.assertTrue(item.data(FADED_ROLE))
        self.assertEqual(self.window.get_selected_paths(), [self.paths[1]])

        # Clicking it again brings it back.
        self._press(self.paths[0])
        self.assertTrue(item.isSelected())
        self.assertFalse(item.data(FADED_ROLE))

    def test_only_selected_stays_on_with_nothing_selected(self) -> None:
        self._select_paths(self.paths)
        self.window.only_selected_button.click()

        self.window.deselect_all_button.click()

        self.assertTrue(self.window.is_only_selected)
        self.assertEqual(self._visible_paths(), self.paths)
        # It can always be turned off.
        self.assertTrue(self.window.only_selected_button.isEnabled())

    def test_only_selected_turns_off_when_the_list_is_cleared(self) -> None:
        self._select_paths(self.paths)
        self.window.only_selected_button.click()

        self.window.clear_list_button.click()

        self.assertFalse(self.window.is_only_selected)
        self.assertFalse(self.window.only_selected_button.isChecked())

    def test_picking_returns_to_only_selected(self) -> None:
        self.gps_by_path[self.paths[1]] = (41.0, -112.0)
        self.window.populate_list()
        self._select_paths([self.paths[0]])
        self.window.only_selected_button.click()

        self.window.start_picking_location()
        self.assertFalse(self.window.is_only_selected)
        self.assertEqual(self.window._grid_filter, "has")
        self.window.pick_location_from_item(self._item_for(self.paths[1]))

        self.assertTrue(self.window.is_only_selected)
        self.assertEqual(self._visible_paths(), [self.paths[0]])

    def test_picking_shows_has_gps_then_returns_to_the_previous_view(self) -> None:
        self.gps_by_path[self.paths[1]] = (41.0, -112.0)
        self.window.populate_list()
        self.window.set_grid_filter("needs")

        self.window.start_picking_location()

        self.assertEqual(self.window._grid_filter, "has")
        for button in self.window.grid_filter_buttons.values():
            self.assertFalse(button.isEnabled())

        self.window.pick_location_from_item(self._item_for(self.paths[1]))

        self.assertFalse(self.window.is_picking_location)
        self.assertEqual(self.window._grid_filter, "needs")
        for button in self.window.grid_filter_buttons.values():
            self.assertTrue(button.isEnabled())

    def test_pick_mode_with_mixed_photos_shows_has_gps_and_disables_all(self) -> None:
        self.gps_by_path[self.paths[1]] = (41.0, -112.0)
        self.window.populate_list()

        self.window.start_picking_location()

        self.assertEqual(self.window._grid_filter, "has")
        self.assertTrue(self.window.grid_filter_buttons["has"].isChecked())
        self.assertFalse(self.window.grid_filter_buttons["all"].isEnabled())
        self.assertFalse(self.window.grid_filter_buttons["needs"].isEnabled())

        self.window.stop_picking_location()

        # Back to the filter from before picking, with every filter usable.
        self.assertEqual(self.window._grid_filter, "all")
        self.assertTrue(self.window.grid_filter_buttons["all"].isEnabled())
        self.assertTrue(self.window.grid_filter_buttons["needs"].isEnabled())

    def test_pick_button_is_off_when_no_photo_has_gps(self) -> None:
        button = self.window.pick_location_button
        self.assertFalse(button.isEnabled())
        self.assertIn("No photo in the Photo List has GPS", button.toolTip())

        self.window.start_picking_location()
        self.assertFalse(self.window.is_picking_location)

        self.gps_by_path[self.paths[1]] = (41.0, -112.0)
        self.window.populate_list()
        self.assertTrue(button.isEnabled())

    def test_empty_grid_message_outside_pick_mode(self) -> None:
        self.window.clear_list_action.trigger()

        self.assertEqual(
            self.window.list_widget.empty_message,
            'Click "+ Add Photos" to get started.',
        )

    def test_hidden_photos_leave_no_marks_in_the_grid_corner(self) -> None:
        self.gps_by_path[self.paths[1]] = (41.0, -112.0)
        self.window.populate_list()
        grid = self.window.list_widget
        corner = QRect(0, 0, 40, 20)
        before = grid.viewport().grab(corner).toImage()

        # Pick mode hides photo-one (no GPS) and marks it "No GPS".
        self.window.start_picking_location()
        self.assertTrue(self._item_for(self.paths[0]).isHidden())
        self.assertTrue(self._item_for(self.paths[0]).data(PICK_DISABLED_ROLE))

        self.assertEqual(grid.viewport().grab(corner).toImage(), before)

    def test_selection_is_kept_while_pick_mode_hides_it(self) -> None:
        self.gps_by_path[self.paths[1]] = (41.0, -112.0)
        self.window.populate_list()
        self._select_paths([self.paths[0]])

        self.window.start_picking_location()

        self.assertTrue(self._item_for(self.paths[0]).isHidden())
        self.assertEqual(self.window.get_selected_paths(), [self.paths[0]])
        self.assertEqual(self.window.selection_title_label.text(), "1 Photo Selected")

        self.window.stop_picking_location()

        self.assertFalse(self._item_for(self.paths[0]).isHidden())
        self.assertEqual(self.window.get_selected_paths(), [self.paths[0]])

    def test_pick_mode_stops_when_no_photo_with_gps_is_left(self) -> None:
        self._give_all_photos_gps()
        self.window.start_picking_location()

        for path in self.paths:
            self.gps_by_path[path] = (None, None)
        self.window.populate_list()

        self.assertFalse(self.window.is_picking_location)

    def test_add_photos_and_clear_list_work_while_picking(self) -> None:
        self.gps_by_path[self.paths[1]] = (41.0, -112.0)
        self.window.populate_list()
        self.window.start_picking_location()
        new_path = Path("/tmp/new-photo.jpg")
        self.gps_by_path[new_path] = (None, None)

        with patch.object(self.window, "_pick_photo_files", side_effect=_choosing([new_path])):
            self.window.add_photos_button.click()

        self.assertEqual(self.window.session.selected_paths, [*self.paths, new_path])
        self.assertTrue(self.window.is_picking_location)
        self.assertEqual(self.window._grid_filter, "has")
        self.assertFalse(self.window.apply_button.isEnabled())

        self.window.clear_list_button.click()

        # Nothing left to copy from, so picking ends.
        self.assertEqual(self.window.session.selected_paths, [])
        self.assertFalse(self.window.is_picking_location)

    def test_escape_and_cancel_stop_picking(self) -> None:
        self._give_all_photos_gps()
        self.window.start_picking_location()
        # Window shortcuts only reach the active window.
        self.window.activateWindow()
        QTest.qWaitForWindowActive(self.window)
        self.window.list_widget.setFocus()
        QTest.keyClick(self.window.list_widget, Qt.Key_Escape)
        self.assertFalse(self.window.is_picking_location)

        self.window.pick_location_button.click()
        self.assertEqual(self.window.pick_location_button.text(), "Cancel")
        self.window.pick_location_button.click()
        self.assertFalse(self.window.is_picking_location)
        self.assertFalse(self.window.pick_location_button.isChecked())
        self.assertEqual(
            self.window.pick_location_button.text(), "From a Photo in the Photo List"
        )

    def test_right_click_does_not_change_selection(self) -> None:
        self._select_paths([self.paths[0]])

        with patch.object(self.window, "show_context_menu"):
            self._click_item(self.paths[1], Qt.RightButton)

        self.assertEqual(self.window.get_selected_paths(), [self.paths[0]])

    def test_right_click_menu_opens_without_blocking_and_its_actions_work(self) -> None:
        from PySide6.QtWidgets import QMenu

        self.gps_by_path[self.paths[1]] = (41.0, -112.0)
        self.window.populate_list()

        # Without patching: the menu must not block (a blocking menu would
        # hang this test). Called as Qt's right-click signal calls it.
        position = self.window.list_widget.visualItemRect(self._item_for(self.paths[1])).center()
        self.window.show_context_menu(position)

        menus = [widget for widget in QApplication.topLevelWidgets() if isinstance(widget, QMenu) and widget.isVisible()]
        self.assertEqual(len(menus), 1)
        menu = menus[0]
        use_action = next(action for action in menu.actions() if action.text() == "Use This Location")
        use_action.trigger()
        menu.close()

        self.assertEqual(self._new_location(), (41.0, -112.0))

    def test_context_menu_use_this_location_sets_source(self) -> None:
        self.gps_by_path[self.paths[1]] = (41.0, -112.0)
        self.window.populate_list()

        self.assertTrue(self.window.use_location_from_path(self.paths[1]))

        self.assertEqual(self._new_location(), (41.0, -112.0))
        self.assertTrue(self._item_for(self.paths[1]).data(SOURCE_ROLE))
        self.assertFalse(self.window.use_location_from_path(self.paths[0]))

    def test_editing_fields_by_hand_drops_the_source(self) -> None:
        self.gps_by_path[self.paths[1]] = (41.0, -112.0)
        self.window.populate_list()
        self.window.use_location_from_path(self.paths[1])

        self.window.latitude_input.setText("41.5")

        self.assertTrue(self.window.source_card.isHidden())
        self.assertFalse(self._item_for(self.paths[1]).data(SOURCE_ROLE))

    def test_source_card_clear_button_empties_location(self) -> None:
        self.gps_by_path[self.paths[1]] = (41.0, -112.0)
        self.window.populate_list()
        self.window.use_location_from_path(self.paths[1])

        self.window.source_card_clear.click()

        self.assertIsNone(self._new_location())
        self.assertTrue(self.window.source_card.isHidden())

    def test_source_marker_survives_applying(self) -> None:
        self.gps_by_path[self.paths[1]] = (41.0, -112.0)
        self.window.populate_list()
        self.window.use_location_from_path(self.paths[1])
        self._select_paths([self.paths[0]])

        self.window.apply_coordinates_to_selected()

        self.assertEqual(self.window.exiftool.writes, [(self.paths[0], 41.0, -112.0)])
        self.assertTrue(self._item_for(self.paths[1]).data(SOURCE_ROLE))

    def test_grid_tiles_cannot_be_dragged_around(self) -> None:
        self.assertEqual(self.window.list_widget.movement(), QListWidget.Static)
        self.assertFalse(self.window.list_widget.dragEnabled())

    # --- New location fields ----------------------------------------------

    def test_coordinate_pair_typed_in_one_field_splits_across_both(self) -> None:
        self.window.latitude_input.setText("40.486325, -111.813415")

        self.assertEqual(self.window.latitude_input.text(), "40.486325")
        self.assertEqual(self.window.longitude_input.text(), "-111.813415")

    def test_coordinate_pair_supports_dms(self) -> None:
        self.window.latitude_input.setText('40°42\'51"N, 74°00\'21"W')

        self.assertEqual(self.window.latitude_input.text(), '40°42\'51"N')
        self.assertEqual(self.window.longitude_input.text(), '74°00\'21"W')
        self._assert_coordinates_almost_equal(
            self._new_location(),
            (40.714166666666664, -74.00583333333333),
        )

    def test_coordinate_pair_supports_spaced_dms(self) -> None:
        self.window.latitude_input.setText('40° 42\' 51" N, 74° 0\' 21" W')

        self.assertEqual(self.window.latitude_input.text(), '40° 42\' 51" N')
        self._assert_coordinates_almost_equal(
            self._new_location(),
            (40.714166666666664, -74.00583333333333),
        )

    def test_coordinate_pair_supports_decimal_minutes(self) -> None:
        self.window.latitude_input.setText("40°42.850'N, 74°00.360'W")

        self._assert_coordinates_almost_equal(self._new_location(), (40.714166666666664, -74.006))

    def test_paste_button_fills_fields_from_clipboard(self) -> None:
        self._set_clipboard("40.486325, -111.813415")
        self.assertTrue(self.window.paste_coordinates_button.isEnabled())

        self.window.paste_coordinates_button.click()

        self.assertEqual(self._new_location(), self.location)

    def test_paste_button_is_disabled_without_coordinates_on_clipboard(self) -> None:
        self._set_clipboard("40.486325, -111.813415")
        self._set_clipboard("not coordinates")

        self.assertFalse(self.window.paste_coordinates_button.isEnabled())
        self.assertFalse(self.window.paste_action.isEnabled())

    def test_paste_button_waits_while_another_program_holds_the_clipboard(self) -> None:
        # On Windows the program that changed the clipboard may still have it
        # open; the check is retried instead of reading (and warning) at once.
        busy = True
        with patch.object(location_editor, "clipboard_is_busy", side_effect=lambda: busy):
            QApplication.clipboard().setText("40.486325, -111.813415")
            while self.window._clipboard_check_retries < 2:
                QTest.qWait(20)
            self.assertFalse(self.window.paste_coordinates_button.isEnabled())

            busy = False
            self._wait_for_clipboard_check()

        self.assertTrue(self.window.paste_coordinates_button.isEnabled())
        self.assertTrue(self.window.paste_action.isEnabled())

    def test_inspector_refresh_does_not_read_the_clipboard(self) -> None:
        # Reading it on every refresh is what collided with other programs on
        # Windows: the Paste button uses the state read after the last change.
        self._set_clipboard("40.486325, -111.813415")
        QTest.qWait(2 * location_editor.CLIPBOARD_CHECK_DELAY_MS)

        with patch.object(location_editor.QApplication, "clipboard") as clipboard:
            self._set_location(*self.location)
            self.window.update_details_panel()
            self._select_paths([self.paths[0]])

        clipboard.assert_not_called()
        self.assertTrue(self.window.paste_coordinates_button.isEnabled())

    def test_invalid_clipboard_paste_shows_message(self) -> None:
        QApplication.clipboard().setText("not coordinates")

        self.window.paste_coordinates_from_clipboard()

        self.assertIsNone(self._new_location())
        self.assertIn("doesn't contain coordinates", self.window.browser_hint.text())

    def test_clear_button_empties_fields(self) -> None:
        self._set_location(*self.location)
        self.assertTrue(self.window.clear_location_button.isEnabled())

        self.window.clear_location_button.click()

        self.assertEqual(self.window.latitude_input.text(), "")
        self.assertEqual(self.window.longitude_input.text(), "")
        self.assertFalse(self.window.clear_location_button.isEnabled())

    def test_location_from_a_photo_file(self) -> None:
        with patch.object(self.window, "_pick_photo_file", side_effect=_choosing(self.source_path)):
            self.window.location_from_photo_button.click()

        self.assertEqual(self._new_location(), self.location)
        self.assertIn("source.jpg", self.window.browser_hint.text())
        self.assertEqual(self.window.source_card_title.text(), "From source.jpg")

    def _browse_photo_capturing_dialogs(self, path: Path) -> list[tuple[str, list[str]]]:
        shown: list[tuple[str, list[str]]] = []

        def fake_show(dialog):
            shown.append((dialog.text(), [button.text() for button in dialog.buttons()]))

        with patch.object(self.window, "_pick_photo_file", side_effect=_choosing(path)), patch.object(
            QMessageBox, "show", new=fake_show
        ):
            self.window.location_from_photo_button.click()
        return shown

    def test_browsing_a_photo_without_gps_shows_a_message(self) -> None:
        self._set_location(*self.location)

        shown = self._browse_photo_capturing_dialogs(self.paths[0])

        self.assertEqual(len(shown), 1)
        text, buttons = shown[0]
        self.assertEqual(text, "Selected Photo has no GPS Coordinates")
        self.assertEqual(len(buttons), 1)  # just OK
        # The location already entered is left alone.
        self.assertEqual(self._new_location(), self.location)

    def test_browsing_a_photo_with_only_half_its_gps_shows_the_message(self) -> None:
        half = Path("/tmp/half-gps.jpg")
        self.gps_by_path[half] = (41.0, None)

        shown = self._browse_photo_capturing_dialogs(half)

        self.assertEqual([text for text, _ in shown], ["Selected Photo has no GPS Coordinates"])
        self.assertIsNone(self._new_location())

    def test_browsing_an_unreadable_photo_shows_a_message(self) -> None:
        broken = Path("/tmp/broken.jpg")
        self._set_location(*self.location)

        with patch.object(
            self.window.workflow,
            "read_photo_info",
            return_value=PhotoInfo(path=broken, file_type="JPG", gps_error="File is damaged"),
        ):
            shown = self._browse_photo_capturing_dialogs(broken)

        self.assertEqual(len(shown), 1)
        text, buttons = shown[0]
        self.assertEqual(text, "Could not read GPS from broken.jpg:\nFile is damaged")
        self.assertEqual(len(buttons), 1)
        self.assertEqual(self._new_location(), self.location)

    def test_browsing_a_photo_with_gps_shows_no_message(self) -> None:
        shown = self._browse_photo_capturing_dialogs(self.source_path)

        self.assertEqual(shown, [])
        self.assertEqual(self._new_location(), self.location)

    def test_invalid_location_explains_and_blocks_apply(self) -> None:
        self.window.select_all_photos()
        self.window.set_location_fields("95", "-111")

        self.assertFalse(self.window.apply_button.isEnabled())
        self.assertIn("isn't valid", self.window.apply_hint_label.text())
        self.assertEqual(self.window.apply_hint_label.property("tone"), "error")

    # --- Apply --------------------------------------------------------------

    def test_apply_writes_location_to_selected_photos_and_reports(self) -> None:
        self.window.select_all_photos()
        self._set_location(*self.location)

        self.window.apply_coordinates_to_selected()

        self.assertCountEqual(
            self.window.exiftool.writes,
            [(path, *self.location) for path in self.paths],
        )
        hint = self.window.browser_hint.text()
        self.assertIn("Applied GPS to 2 photos.", hint)
        self.assertIn('href="undo"', hint)
        self.assertEqual(self.window.browser_hint.property("tone"), "success")
        # The changed photos are deselected, so the next Apply can't
        # include them again by accident.
        self.assertEqual(self.window.get_selected_paths(), [])

    def test_backups_made_by_apply_stay_out_of_the_list(self) -> None:
        # A backup at the old location next to the moved photo looked like the
        # photo hadn't moved, so backups are never added to the Photo List.
        backup = Path("/tmp/photo-one_original.jpg")
        self.gps_by_path[self.paths[0]] = (41.0, -112.0)
        self.gps_by_path[backup] = (41.0, -112.0)
        self.window.populate_list()
        self.window.select_browser_paths([self.paths[0]])
        self._set_location(*self.location)
        self.window.exiftool.take_created_backups = lambda: [backup]
        dialog_patch, _ = self._answer_overwrite_dialog("Replace")

        with dialog_patch:
            self.window.apply_coordinates_to_selected()

        self.assertNotIn(backup, self.window.session.selected_paths)
        self.assertIn("Saved a backup of the original next to it.", self.window.browser_hint.text())

    def test_undo_deletes_the_backups_the_change_made_and_redo_makes_them_again(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        backup = Path(temp_dir.name) / "photo-one_original.jpg"
        self.gps_by_path[self.paths[0]] = (41.0, -112.0)
        self.gps_by_path[backup] = (41.0, -112.0)
        self.window.populate_list()
        self.window.select_browser_paths([self.paths[0]])
        self._set_location(*self.location)

        def make_backup():
            backup.write_bytes(b"original")
            return [backup]

        self.window.exiftool.take_created_backups = make_backup
        dialog_patch, _ = self._answer_overwrite_dialog("Replace")
        with dialog_patch:
            self.window.apply_coordinates_to_selected()
        self.assertTrue(backup.exists())
        self.assertNotIn(backup, self.window.session.selected_paths)

        with patch.object(Path, "exists", return_value=True):
            self.window.undo_gps_edit()

        self.assertFalse(backup.is_file())

        # Redo makes the backup again; the next undo deletes it again.
        with patch.object(Path, "exists", return_value=True):
            self.window.redo_gps_edit()
        self.assertTrue(backup.is_file())
        self.assertNotIn(backup, self.window.session.selected_paths)
        self.window.exiftool.take_created_backups = lambda: []
        with patch.object(Path, "exists", return_value=True):
            self.window.undo_gps_edit()
        self.assertFalse(backup.is_file())

    def test_undo_never_makes_a_backup(self) -> None:
        # A photo without GPS gets a location (no backup: nothing to lose).
        # Undoing it removes that location, which with backups on used to
        # "back up" the location being removed as <name>_original.
        writer = self.window.exiftool
        writer.keep_backups = True
        backups_on_while = {}
        clear_gps = writer.clear_gps

        def recording_clear(path):
            backups_on_while["clear"] = writer.keep_backups
            clear_gps(path)

        writer.clear_gps = recording_clear
        self.window.select_browser_paths([self.paths[0]])
        self._set_location(*self.location)
        self.window.apply_coordinates_to_selected()

        with patch.object(Path, "exists", return_value=True):
            self.window.undo_gps_edit()

        self.assertEqual(backups_on_while, {"clear": False})
        # Back on afterwards, for the next change.
        self.assertTrue(writer.keep_backups)

    def test_undo_leaves_older_backups_alone(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        older = Path(temp_dir.name) / "photo-one_original.jpg"
        older.write_bytes(b"from an earlier session")
        self.window.select_all_photos()
        self._set_location(*self.location)
        self.window.apply_coordinates_to_selected()

        with patch.object(Path, "exists", return_value=True):
            self.window.undo_gps_edit()

        self.assertEqual(older.read_bytes(), b"from an earlier session")

    def test_apply_keeps_only_failed_photos_selected(self) -> None:
        self.window.select_all_photos()
        self._set_location(*self.location)
        self.window.exiftool.failures[self.paths[1]] = RuntimeError("locked")

        with patch.object(self.window, "_report_write_failures"):
            self.window.apply_coordinates_to_selected()

        self.assertEqual(self.window.get_selected_paths(), [self.paths[1]])

    def test_undo_brings_back_the_selection_from_before_apply(self) -> None:
        self.window.select_all_photos()
        self._set_location(*self.location)
        self.window.apply_coordinates_to_selected()
        self.assertEqual(self.window.get_selected_paths(), [])

        # Undo leaves out files that no longer exist; these test files are
        # made up, so pretend they exist (as the other undo tests do).
        with patch.object(Path, "exists", return_value=True):
            self.window.undo_gps_edit()

        self.assertCountEqual(self.window.get_selected_paths(), self.paths)

    def test_skipped_photos_are_deselected_too(self) -> None:
        self._select_one_with_gps_and_one_without()
        dialog_patch, _ = self._answer_overwrite_dialog("Skip Photos with GPS")

        with dialog_patch:
            self.window.apply_coordinates_to_selected()

        self.assertEqual(self.window.get_selected_paths(), [])

    def test_cancelled_apply_keeps_the_selection(self) -> None:
        self._select_one_with_gps_and_one_without()
        dialog_patch, _ = self._answer_overwrite_dialog("Cancel")

        with dialog_patch:
            self.window.apply_coordinates_to_selected()

        self.assertCountEqual(self.window.get_selected_paths(), self.paths)

    def test_apply_only_touches_selected_photos(self) -> None:
        self._select_paths([self.paths[1]])
        self._set_location(*self.location)

        self.window.apply_coordinates_to_selected()

        self.assertEqual(self.window.exiftool.writes, [(self.paths[1], *self.location)])

    def test_apply_requires_photo_selection(self) -> None:
        self._set_location(*self.location)

        self.window.apply_coordinates_to_selected()

        self.assertEqual(self.window.exiftool.writes, [])
        self.assertIn("Select the photos to change", self.window.browser_hint.text())

    def test_apply_requires_valid_coordinates(self) -> None:
        self.window.select_all_photos()
        self.window.set_location_fields("north", "west")

        self.window.apply_coordinates_to_selected()

        self.assertEqual(self.window.exiftool.writes, [])

    def _answer_overwrite_dialog(self, button_text: str | None):
        """
        Patch the overwrite dialog so it "clicks" the named button (None
        closes it without a choice). Returns the patch and a list that
        collects the dialog's button labels.
        """
        seen_buttons: list[str] = []

        def fake_show(dialog):
            self._last_dialog_text = dialog.text()
            seen_buttons.extend(button.text() for button in dialog.buttons())
            for button in dialog.buttons():
                if button.text() == button_text:
                    button.click()
                    return
            # No button: closed another way (Esc or the window's close box).
            dialog.reject()

        # A plain function on the class becomes a method, so it receives the dialog.
        return patch.object(QMessageBox, "show", new=fake_show), seen_buttons

    def _select_one_with_gps_and_one_without(self) -> None:
        self.gps_by_path[self.paths[0]] = (41.0, -112.0)
        self.window.populate_list()
        self.window.select_all_photos()
        self._set_location(*self.location)

    def test_overwrite_dialog_offers_cancel_skip_and_replace(self) -> None:
        self._select_one_with_gps_and_one_without()
        dialog_patch, buttons = self._answer_overwrite_dialog(None)

        with dialog_patch:
            self.window.apply_coordinates_to_selected()

        self.assertIn("Cancel", buttons)
        self.assertIn("Skip Photos with GPS", buttons)
        self.assertIn("Replace", buttons)
        self.assertEqual(
            self._last_dialog_text,
            "1 photo already has GPS Coordinates. Choose Skip to keep the existing "
            "GPS data, Replace to overwrite them. Click Edit → Undo if you "
            "accidentally overwrite GPS data.",
        )

    def test_apply_cancels_when_overwrite_dialog_is_cancelled(self) -> None:
        self._select_one_with_gps_and_one_without()
        dialog_patch, _ = self._answer_overwrite_dialog("Cancel")

        with dialog_patch:
            self.window.apply_coordinates_to_selected()

        self.assertEqual(self.window.exiftool.writes, [])
        self.assertIn("Nothing was changed", self.window.browser_hint.text())

    def test_apply_replaces_existing_gps_when_confirmed(self) -> None:
        self._select_one_with_gps_and_one_without()
        dialog_patch, _ = self._answer_overwrite_dialog("Replace")

        with dialog_patch:
            self.window.apply_coordinates_to_selected()

        self.assertCountEqual(
            self.window.exiftool.writes,
            [(path, *self.location) for path in self.paths],
        )

    def test_skip_updates_only_photos_without_gps(self) -> None:
        self._select_one_with_gps_and_one_without()
        dialog_patch, _ = self._answer_overwrite_dialog("Skip Photos with GPS")

        with dialog_patch:
            self.window.apply_coordinates_to_selected()

        self.assertEqual(self.window.exiftool.writes, [(self.paths[1], *self.location)])
        self.assertEqual(self.gps_by_path[self.paths[0]], (41.0, -112.0))
        hint = self.window.browser_hint.text()
        self.assertIn("Applied GPS to 1 photo.", hint)
        self.assertIn("Skipped 1 that already has GPS.", hint)
        # Undo only covers the photo that changed.
        self.assertEqual(self.window.gps_history.undo_states(), {self.paths[1]: (None, None)})

    def test_no_skip_button_when_every_selected_photo_has_gps(self) -> None:
        self.gps_by_path[self.paths[0]] = (41.0, -112.0)
        self.gps_by_path[self.paths[1]] = (42.0, -113.0)
        self.window.populate_list()
        self.window.select_all_photos()
        self._set_location(*self.location)
        dialog_patch, buttons = self._answer_overwrite_dialog("Cancel")

        with dialog_patch:
            self.window.apply_coordinates_to_selected()

        self.assertNotIn("Skip Photos with GPS", buttons)
        self.assertIn("Replace", buttons)
        self.assertEqual(
            self._last_dialog_text,
            "2 photos already have GPS Coordinates. Choose Replace to overwrite "
            "them. Click Edit → Undo if you accidentally overwrite GPS data.",
        )

    def test_apply_reports_partial_write_failures(self) -> None:
        self.window.select_all_photos()
        self._set_location(*self.location)
        self.window.exiftool.failures[self.paths[1]] = RuntimeError("disk full")

        with patch.object(self.window, "_report_write_failures") as report_mock:
            self.window.apply_coordinates_to_selected()

        self.assertEqual(self.window.exiftool.writes, [(self.paths[0], *self.location)])
        report_mock.assert_called_once_with("apply GPS to", ["photo-two.jpg: disk full"])
        # Only the file that changed can be undone.
        self.assertEqual(self.window.gps_history.undo_states(), {self.paths[0]: (None, None)})

    def test_write_failure_dialog_lists_each_file(self) -> None:
        with patch("gui.main_window.QMessageBox.show") as show_mock, patch(
            "gui.main_window.QMessageBox.setDetailedText"
        ) as details_mock:
            self.window._report_write_failures("apply GPS to", ["a.jpg: locked"])

        show_mock.assert_called_once()
        details_mock.assert_called_once_with("a.jpg: locked")

    def test_no_failure_dialog_when_everything_succeeds(self) -> None:
        with patch("gui.main_window.QMessageBox.show") as show_mock:
            self.window._report_write_failures("apply GPS to", [])

        show_mock.assert_not_called()

    # --- Undo / redo ------------------------------------------------------

    def test_undo_and_redo_apply(self) -> None:
        self.window.select_all_photos()
        self._set_location(*self.location)
        self.window.apply_coordinates_to_selected()
        self.assertTrue(self.window.undo_action.isEnabled())
        self.assertFalse(self.window.redo_action.isEnabled())

        self.window.undo_action.trigger()

        self.assertEqual(self.gps_by_path[self.paths[0]], (None, None))
        self.assertEqual(self.gps_by_path[self.paths[1]], (None, None))
        self.assertFalse(self.window.undo_action.isEnabled())
        self.assertTrue(self.window.redo_action.isEnabled())

        self.window.redo_action.trigger()

        self.assertEqual(self.gps_by_path[self.paths[0]], self.location)
        self.assertEqual(self.gps_by_path[self.paths[1]], self.location)

    def test_undo_link_in_status_row_undoes_apply(self) -> None:
        self.window.select_all_photos()
        self._set_location(*self.location)
        self.window.apply_coordinates_to_selected()

        self.window.browser_hint.linkActivated.emit("undo")

        self.assertEqual(self.gps_by_path[self.paths[0]], (None, None))
        self.assertTrue(self.window.redo_action.isEnabled())
        self.assertNotIn('href="undo"', self.window.browser_hint.text())

    def test_status_row_hides_when_the_message_clears(self) -> None:
        self.window._set_status_message("Something happened.", "success")
        self.assertIn("Something happened.", self.window.browser_hint.text())
        self.assertFalse(self.window.loading_indicator.isHidden())

        self.window._clear_status_message()

        self.assertEqual(self.window.browser_hint.text(), "")
        self.assertEqual(self.window.browser_hint.property("tone"), "info")
        self.assertTrue(self.window.loading_indicator.isHidden())

    def test_undo_puts_the_photo_list_back_too(self) -> None:
        self._select_paths([self.paths[0]])
        self._set_location(*self.location)
        self.window.apply_coordinates_to_selected()

        # Change the list after the edit: add a photo, remove another.
        new_path = Path("/tmp/new-photo.jpg")
        self.gps_by_path[new_path] = (None, None)
        self._choose_photos([new_path])
        self._select_paths([self.paths[1]])
        self.window.remove_selected_from_list()
        self.assertEqual(self.window.session.selected_paths, [self.paths[0], new_path])
        self.assertTrue(self.window.undo_action.isEnabled())

        with patch.object(Path, "exists", return_value=True):
            self.window.undo_gps_edit()

        self.assertEqual(self.gps_by_path[self.paths[0]], (None, None))
        self.assertEqual(self.window.session.selected_paths, self.paths)
        self.assertEqual(self.window.get_selected_paths(), [self.paths[0]])

        with patch.object(Path, "exists", return_value=True):
            self.window.redo_gps_edit()

        self._assert_coordinates_almost_equal(self.gps_by_path[self.paths[0]], self.location)
        self.assertEqual(self.window.session.selected_paths, self.paths)

    def test_undo_leaves_out_photos_that_no_longer_exist(self) -> None:
        self.window.select_all_photos()
        self._set_location(*self.location)
        self.window.apply_coordinates_to_selected()

        # The test photos are not real files, so none "exist" any more.
        self.window.undo_gps_edit()

        self.assertEqual(self.window.session.selected_paths, [])

    def test_undo_reports_files_that_could_not_be_restored(self) -> None:
        self.window.select_all_photos()
        self._set_location(*self.location)
        self.window.apply_coordinates_to_selected()
        self.window.exiftool.failures[self.paths[0]] = RuntimeError("read-only")

        with patch.object(self.window, "_report_write_failures") as report_mock:
            self.window.undo_action.trigger()

        report_mock.assert_called_once_with(
            "undo the GPS change for",
            ["photo-one.jpg: read-only"],
        )
        # The other file was still restored.
        self.assertEqual(self.gps_by_path[self.paths[1]], (None, None))
        self.assertTrue(self.window.redo_action.isEnabled())

    # --- Remove GPS -------------------------------------------------------

    def _confirm_remove_gps(self, answer=QMessageBox.Ok) -> None:
        def fake_show(dialog):
            # "Click" the answer; the work continues when the dialog closes.
            dialog.button(answer).click()

        with patch.object(QMessageBox, "show", new=fake_show):
            self.window.remove_gps_from_selected()

    def test_remove_gps_waits_for_the_real_dialog_without_blocking(self) -> None:
        self.gps_by_path[self.paths[0]] = (41.0, -112.0)
        self.window.populate_list()
        self.window.select_all_photos()

        self.window.remove_gps_from_selected()

        # The dialog is open and the code that opened it has returned.
        dialog = self.window._open_messages[-1]
        self.assertTrue(dialog.isVisible())
        self.assertEqual(self.window.exiftool.clears, [])

        QTest.mouseClick(dialog.button(QMessageBox.Ok), Qt.LeftButton)

        self.assertEqual(self.window.exiftool.clears, [self.paths[0]])
        self.assertEqual(self.window._open_messages, [])

    def test_remove_gps_clears_selected_photos_after_confirming(self) -> None:
        self.gps_by_path[self.paths[0]] = (41.0, -112.0)
        self.window.populate_list()
        self.window.select_all_photos()
        self.window.loader.calls.clear()

        self._confirm_remove_gps()

        self.assertEqual(self.window.exiftool.clears, [self.paths[0]])
        self.assertEqual(self.gps_by_path[self.paths[0]], (None, None))
        self.assertEqual(self.window.loader.calls, self.paths)
        self.assertIn("Removed GPS from 1 photo.", self.window.browser_hint.text())
        self.assertTrue(self.window.undo_action.isEnabled())
        self.assertEqual(self.window.get_selected_paths(), [])

        self.window.undo_action.trigger()
        self.assertEqual(self.gps_by_path[self.paths[0]], (41.0, -112.0))

        self.window.redo_action.trigger()
        self.assertEqual(self.gps_by_path[self.paths[0]], (None, None))

    def test_remove_gps_does_nothing_when_cancelled(self) -> None:
        self.gps_by_path[self.paths[0]] = (41.0, -112.0)
        self.window.populate_list()
        self.window.select_all_photos()

        self._confirm_remove_gps(QMessageBox.Cancel)

        self.assertEqual(self.window.exiftool.clears, [])

    def test_remove_gps_continues_past_a_failed_file(self) -> None:
        self.gps_by_path[self.paths[0]] = (41.0, -112.0)
        self.gps_by_path[self.paths[1]] = (42.0, -113.0)
        self.window.populate_list()
        self.window.select_all_photos()
        self.window.exiftool.failures[self.paths[0]] = RuntimeError("locked")

        with patch.object(self.window, "_report_write_failures") as report_mock:
            self._confirm_remove_gps()

        self.assertEqual(self.window.exiftool.clears, [self.paths[1]])
        self.assertEqual(self.gps_by_path[self.paths[0]], (41.0, -112.0))
        report_mock.assert_called_once_with("remove GPS from", ["photo-one.jpg: locked"])
        # The state carries the altitude too (None: the photo had none).
        self.assertEqual(self.window.gps_history.undo_states(), {self.paths[1]: (42.0, -113.0, None)})

    def _group_headings(self, *, visible_only: bool = False) -> list[str]:
        list_widget = self.window.list_widget
        headings = []
        for row in range(list_widget.count()):
            item = list_widget.item(row)
            widget = list_widget.itemWidget(item)
            if widget is not None and not (visible_only and item.isHidden()):
                headings.append(widget.findChild(QLabel, "thumbnailGroupHeader").text())
        return headings

    def _visible_headings(self) -> list[str]:
        return self._group_headings(visible_only=True)

    def test_grid_has_heading_for_each_gps_group(self) -> None:
        self.gps_by_path[self.paths[1]] = (41.0, -112.0)
        self.window.populate_list()

        self.assertEqual(
            self._group_headings(),
            [
                "Photos without GPS Coordinates (1)",
                "Photos with GPS Coordinates (1)",
            ],
        )

    def test_no_heading_for_an_empty_group(self) -> None:
        self.assertEqual(self._group_headings(), ["Photos without GPS Coordinates (2)"])

    def _open_settings(self):
        self.window.open_settings()
        dialog = self.window._settings_dialog
        # An open modal dialog would block the mouse in later tests.
        self.addCleanup(dialog.close)
        return dialog

    @staticmethod
    def _click_checkbox(checkbox) -> None:
        # On the box itself: the widget is wider than its box and label.
        QTest.mouseClick(checkbox, Qt.LeftButton, Qt.NoModifier, QPoint(8, checkbox.height() // 2))

    def test_keep_backups_option_is_saved_and_applied(self) -> None:
        dialog = self._open_settings()
        self.assertEqual(dialog.windowModality(), Qt.ApplicationModal)
        self.assertFalse(dialog.keep_backups_check.isChecked())

        self._click_checkbox(dialog.keep_backups_check)
        QTest.mouseClick(dialog.save_button, Qt.LeftButton)

        self.assertTrue(self.window.workflow.writer.keep_backups)
        self.assertTrue(self.settings.value("keep_backup_copies", type=bool))

        reopened = MainWindow(settings=QSettings(str(self.settings_path), QSettings.IniFormat))
        self.addCleanup(reopened.close)
        self.assertTrue(reopened.keep_backups)
        self.assertTrue(reopened.workflow.writer.keep_backups)

    def test_units_option_defaults_to_feet_and_is_saved(self) -> None:
        dialog = self._open_settings()
        self.assertTrue(dialog.feet_radio.isChecked())
        self.assertTrue(self.window.use_feet)

        self._click_checkbox(dialog.metres_radio)
        self.assertTrue(dialog.save_button.isEnabled())
        QTest.mouseClick(dialog.save_button, Qt.LeftButton)

        self.assertFalse(self.window.use_feet)
        self.assertFalse(self.settings.value("units/feet", type=bool))
        reopened = MainWindow(settings=QSettings(str(self.settings_path), QSettings.IniFormat))
        self.addCleanup(reopened.close)
        self.assertFalse(reopened.use_feet)

    def test_the_esri_steps_are_folded_up_until_asked_for(self) -> None:
        dialog = self._open_settings()
        self.assertFalse(dialog.esri_help.isVisible())
        self.assertFalse(dialog.help_toggle.isChecked())
        height = dialog.height()

        QTest.mouseClick(dialog.help_toggle, Qt.LeftButton)
        QTest.qWait(50)  # the layout resizes the window on the next pass
        self.assertTrue(dialog.esri_help.isVisible())
        self.assertGreater(dialog.height(), height, "the window grows for the steps")
        self.assertFalse(dialog.save_button.isEnabled(), "opening the steps changes no setting")

        QTest.mouseClick(dialog.help_toggle, Qt.LeftButton)
        QTest.qWait(50)
        self.assertFalse(dialog.esri_help.isVisible())
        self.assertEqual(dialog.height(), height, "and shrinks back")

    def test_the_units_segment_is_exclusive(self) -> None:
        dialog = self._open_settings()
        self.assertTrue(dialog.feet_radio.isChecked())
        self.assertFalse(dialog.metres_radio.isChecked())
        QTest.mouseClick(dialog.metres_radio, Qt.LeftButton)
        self.assertFalse(dialog.feet_radio.isChecked())
        self.assertFalse(dialog.use_feet())
        # Clicking the chosen one again keeps it chosen (a segment, not a toggle).
        QTest.mouseClick(dialog.metres_radio, Qt.LeftButton)
        self.assertTrue(dialog.metres_radio.isChecked())

    def test_save_is_off_until_a_setting_changes(self) -> None:
        dialog = self._open_settings()
        self.assertFalse(dialog.save_button.isEnabled())

        self._click_checkbox(dialog.keep_backups_check)
        self.assertTrue(dialog.save_button.isEnabled())

        # Changed back: nothing to save again.
        self._click_checkbox(dialog.keep_backups_check)
        self.assertFalse(dialog.save_button.isEnabled())

        dialog.esri_key_input.setText("some-key")
        self.assertTrue(dialog.save_button.isEnabled())

    def test_cancelled_settings_change_nothing(self) -> None:
        dialog = self._open_settings()
        self._click_checkbox(dialog.keep_backups_check)
        dialog.esri_key_input.setText("some-key")

        QTest.mouseClick(dialog.cancel_button, Qt.LeftButton)

        self.assertFalse(getattr(self.window.workflow.writer, "keep_backups", False))
        self.assertIsNone(self.settings.value("keep_backup_copies"))
        self.assertIsNone(self.settings.value("map/esri_api_key"))

    def test_settings_is_in_the_edit_menu(self) -> None:
        from PySide6.QtWidgets import QMenu

        self.assertEqual(self.window.settings_action.text(), "Settings...")
        edit_menu = next(
            menu for menu in self.window.menuBar().findChildren(QMenu) if menu.title() == "&Edit"
        )
        self.assertIn(self.window.settings_action, edit_menu.actions())

    def test_every_settings_button_has_a_hover_hint(self) -> None:
        from PySide6.QtWidgets import QPushButton

        dialog = self._open_settings()
        missing = [
            button.text()
            for button in dialog.findChildren(QPushButton)
            if not button.toolTip()
        ]
        self.assertEqual(missing, [])



if __name__ == "__main__":
    unittest.main()
