import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QCheckBox, QPushButton, QTreeWidgetItem

from core.models import PhotoInfo
from core.places import Place
from gui.background import BackgroundRunner
from gui.widgets.photo_picker import HAS_GPS_ROLE, IS_FOLDER_ROLE, PATH_ROLE, PhotoPickerDialog
from gui.widgets.thumbnail_delegate import IN_LIST_ROLE, SHIMMER_ROLE
from services.models import WorkflowSession


class FakeWorkflow:
    """Reads GPS from a dict instead of the files."""

    def __init__(self, gps_paths: set[Path]) -> None:
        self.gps_paths = gps_paths

    def refresh_photo_workflow(self, session: WorkflowSession) -> WorkflowSession:
        infos = {}
        for path in session.selected_paths:
            has_gps = path in self.gps_paths
            infos[path] = PhotoInfo(
                path=path,
                file_type="JPG",
                current_latitude=40.0 if has_gps else None,
                current_longitude=-111.0 if has_gps else None,
            )
        session.loaded_photo_infos = infos
        return session


class FakeThumbnailLoader:
    def __init__(self) -> None:
        self.loaded: list[Path] = []

    def cached_icon(self, path: Path, has_gps: bool = False):
        return None

    def load_images(self, paths: list[Path]) -> dict:
        self.loaded.extend(paths)
        return {path: None for path in paths}

    def icon_from_image(self, path: Path, has_gps: bool, image) -> QIcon:
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.blue if has_gps else Qt.lightGray)
        return QIcon(pixmap)


class PhotoPickerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.root = Path(temp_dir.name)
        self.trip = self.root / "Trip"
        self.year = self.trip / "2019"
        self.year.mkdir(parents=True)
        for name in ("a.jpg", "b.jpg", "c.jpg", "notes.txt"):
            (self.trip / name).write_bytes(b"")
        (self.year / "d.jpg").write_bytes(b"")
        self.other = self.root / "Other"
        self.other.mkdir()

        self.thumbnails = FakeThumbnailLoader()
        self.background = BackgroundRunner()
        self.background.run_inline = True

    def _open(
        self,
        start: Path,
        in_list: set[Path] = frozenset(),
        single: bool = False,
        include_subfolders: bool = False,
    ) -> PhotoPickerDialog:
        dialog = PhotoPickerDialog(
            None,
            title="Add Photos",
            start_folder=start,
            in_list=set(in_list),
            workflow=FakeWorkflow({self.trip / "b.jpg"}),
            thumbnail_loader=self.thumbnails,
            background=self.background,
            place_sections=[
                ("My Computer", [Place("Home", self.root)]),
                ("Bookmarks", [Place("My Trip", self.trip), Place("Other", self.other)]),
            ],
            single=single,
            include_subfolders=include_subfolders,
        )
        self.addCleanup(dialog.close)
        dialog.show()
        return dialog

    def _grid_names(self, dialog: PhotoPickerDialog) -> list[str]:
        # A folder tile's text has its contents on a second line.
        return [dialog.grid.item(row).text().split("\n")[0] for row in range(dialog.grid.count())]

    def _grid_item(self, dialog: PhotoPickerDialog, name: str):
        return next(
            dialog.grid.item(row)
            for row in range(dialog.grid.count())
            if dialog.grid.item(row).text().split("\n")[0] == name
        )

    def _click(self, dialog: PhotoPickerDialog, name: str, modifier=Qt.NoModifier) -> None:
        item = self._grid_item(dialog, name)
        QTest.mouseClick(
            dialog.grid.viewport(),
            Qt.LeftButton,
            modifier,
            dialog.grid.visualItemRect(item).center(),
        )

    def _double_click(self, dialog: PhotoPickerDialog, name: str) -> None:
        # A real double-click is a click and then a double-click event; Qt's
        # test helper sends only the double-click event.
        self._click(dialog, name)
        item = self._grid_item(dialog, name)
        QTest.mouseDClick(
            dialog.grid.viewport(),
            Qt.LeftButton,
            Qt.NoModifier,
            dialog.grid.visualItemRect(item).center(),
        )

    def _tree_item(self, dialog: PhotoPickerDialog, name: str):
        return dialog.tree.findItems(name, Qt.MatchExactly | Qt.MatchRecursive)[0]

    def test_shows_the_folders_subfolders_then_its_photos(self) -> None:
        dialog = self._open(self.trip)

        # Subfolders first, then photos; no other files.
        self.assertEqual(self._grid_names(dialog), ["2019", "a.jpg", "b.jpg", "c.jpg"])
        self.assertTrue(self._grid_item(dialog, "2019").data(IS_FOLDER_ROLE))
        self.assertFalse(self._grid_item(dialog, "a.jpg").data(IS_FOLDER_ROLE))
        # What is inside each subfolder, under its name.
        self.assertEqual(self._grid_item(dialog, "2019").text(), "2019\n1 photo")
        self.assertEqual(dialog.folder_summary_label.text(), "")
        self.assertEqual(dialog.path_box.text(), str(self.trip))
        self.assertEqual(self.thumbnails.loaded, [self.trip / "a.jpg", self.trip / "b.jpg", self.trip / "c.jpg"])

    def test_photos_already_in_the_list_cannot_be_selected(self) -> None:
        dialog = self._open(self.trip, in_list={self.trip / "a.jpg"})
        item = self._grid_item(dialog, "a.jpg")

        self.assertTrue(item.data(IN_LIST_ROLE))

        self._click(dialog, "a.jpg")
        dialog.select_all_button.click()

        self.assertFalse(item.isSelected())
        self.assertEqual(dialog.selected_paths(), [self.trip / "b.jpg", self.trip / "c.jpg"])
        self.assertEqual(dialog.selected_folders(), [self.year])

    def test_clicking_photos_selects_them_and_updates_add(self) -> None:
        dialog = self._open(self.trip)
        self.assertFalse(dialog.add_button.isEnabled())
        self.assertFalse(dialog.selection_bar.property("active"))

        self._click(dialog, "a.jpg")
        self._click(dialog, "c.jpg", Qt.ShiftModifier)

        self.assertEqual(dialog.selected_paths(), [self.trip / name for name in ("a.jpg", "b.jpg", "c.jpg")])
        self.assertEqual(dialog.add_button.text(), "Add 3 Photos to Photo List")
        self.assertTrue(dialog.selection_bar.property("active"))

        self._click(dialog, "b.jpg")
        self.assertEqual(dialog.add_button.text(), "Add 2 Photos to Photo List")

        dialog.deselect_all_button.click()
        self.assertEqual(dialog.selected_paths(), [])
        self.assertFalse(dialog.add_button.isEnabled())

    def test_tree_shows_places_and_highlights_the_folder(self) -> None:
        dialog = self._open(self.trip)

        sections = [dialog.tree.topLevelItem(index).text(0) for index in range(dialog.tree.topLevelItemCount())]
        self.assertEqual(sections, ["My Computer", "Bookmarks"])
        # The closest place holding the folder is highlighted.
        self.assertEqual(dialog.tree.currentItem().text(0), "My Trip")

    def test_clicking_a_folder_in_the_tree_opens_it(self) -> None:
        dialog = self._open(self.trip)
        other = self._tree_item(dialog, "Other")

        dialog.tree.itemClicked.emit(other, 0)

        self.assertEqual(dialog.current_folder, self.other)
        self.assertEqual(self._grid_names(dialog), [])
        self.assertIn("No photos or folders in this folder", dialog.empty_label.text())

    def test_expanding_a_folder_lists_its_subfolders(self) -> None:
        dialog = self._open(self.other)
        trip = self._tree_item(dialog, "My Trip")

        trip.setExpanded(True)

        self.assertEqual([trip.child(index).text(0) for index in range(trip.childCount())], ["2019"])

    def test_only_folders_with_subfolders_get_an_expand_arrow(self) -> None:
        dialog = self._open(self.other)
        trip = self._tree_item(dialog, "My Trip")
        other = self._tree_item(dialog, "Other")

        self.assertEqual(trip.childIndicatorPolicy(), QTreeWidgetItem.ShowIndicator)
        self.assertEqual(other.childIndicatorPolicy(), QTreeWidgetItem.DontShowIndicator)

        trip.setExpanded(True)
        year = trip.child(0)
        self.assertEqual(year.childIndicatorPolicy(), QTreeWidgetItem.DontShowIndicator)

    def test_opening_a_nested_folder_opens_the_tree_down_to_it(self) -> None:
        dialog = self._open(self.year)

        current = dialog.tree.currentItem()
        self.assertEqual(current.text(0), "2019")
        self.assertEqual(current.data(0, PATH_ROLE), str(self.year))
        self.assertEqual(self._grid_names(dialog), ["d.jpg"])

    def test_path_box_opens_a_typed_folder(self) -> None:
        dialog = self._open(self.trip)

        dialog.path_box.setText(str(self.year))
        dialog.path_box.returnPressed.emit()
        self.assertEqual(dialog.current_folder, self.year)

        dialog.path_box.setText(str(self.root / "missing"))
        dialog.path_box.returnPressed.emit()
        self.assertEqual(dialog.current_folder, self.year)
        self.assertTrue(dialog.path_box.property("error"))

    def test_enter_in_the_path_box_does_not_add_photos(self) -> None:
        dialog = self._open(self.trip)
        self._click(dialog, "a.jpg")

        dialog.path_box.setText(str(self.year))
        QTest.keyClick(dialog.path_box, Qt.Key_Return)

        self.assertTrue(dialog.isVisible())
        self.assertEqual(dialog.current_folder, self.year)

    def test_back_forward_and_up(self) -> None:
        dialog = self._open(self.trip)
        self.assertFalse(dialog.back_button.isEnabled())

        dialog.open_folder(self.year)
        dialog.back_button.click()
        self.assertEqual(dialog.current_folder, self.trip)

        dialog.forward_button.click()
        self.assertEqual(dialog.current_folder, self.year)

        dialog.up_button.click()
        self.assertEqual(dialog.current_folder, self.trip)

    def test_late_results_after_changing_folders_are_ignored(self) -> None:
        dialog = self._open(self.trip)
        generation = dialog._generation
        dialog.open_folder(self.year)

        # A thumbnail batch from the folder shown before arrives late.
        dialog._apply_thumbnails((generation, {self.trip / "a.jpg": None}))

        self.assertEqual(self._grid_names(dialog), ["d.jpg"])

    def test_photos_show_as_placeholders_before_their_thumbnails(self) -> None:
        background = self.background
        background.run_inline = False
        self.addCleanup(background.shutdown)
        dialog = self._open(self.trip)

        # Wait only for the folder listing; thumbnails are still on their way.
        for _ in range(100):
            QApplication.processEvents()
            if dialog.grid.count():
                break
            QTest.qWait(10)
        self.assertEqual(self._grid_names(dialog), ["2019", "a.jpg", "b.jpg", "c.jpg"])
        photo_a = self._grid_item(dialog, "a.jpg")
        photo_b = self._grid_item(dialog, "b.jpg")

        for _ in range(200):
            QApplication.processEvents()
            if not any(dialog.grid.item(row).data(SHIMMER_ROLE) for row in range(dialog.grid.count())):
                break
            QTest.qWait(10)
        self.assertFalse(photo_a.data(SHIMMER_ROLE))
        # GPS badges arrive in a second pass after the thumbnails: wait for
        # it too (a slow machine may not have it yet).
        for _ in range(200):
            QApplication.processEvents()
            if photo_b.data(HAS_GPS_ROLE):
                break
            QTest.qWait(10)
        self.assertTrue(photo_b.data(HAS_GPS_ROLE))
        self.assertFalse(photo_a.data(HAS_GPS_ROLE))

    def test_one_photo_mode_chooses_a_single_photo(self) -> None:
        dialog = self._open(self.trip, in_list={self.trip / "a.jpg"}, single=True)
        self.assertFalse(dialog.select_all_button.isVisibleTo(dialog))
        # Photos in the Photo List can still be used as a location.
        self.assertFalse(self._grid_item(dialog, "a.jpg").data(IN_LIST_ROLE))

        self._click(dialog, "a.jpg")
        self._click(dialog, "c.jpg", Qt.ShiftModifier)

        self.assertEqual(dialog.selected_paths(), [self.trip / "c.jpg"])
        self.assertEqual(dialog.add_button.text(), "Use This Photo's Location")

    def test_double_click_chooses_the_photo_in_one_photo_mode(self) -> None:
        dialog = self._open(self.trip, single=True)

        self._double_click(dialog, "b.jpg")

        self.assertEqual(dialog.result(), PhotoPickerDialog.Accepted)
        self.assertEqual(dialog.selected_paths(), [self.trip / "b.jpg"])

    def test_every_button_has_a_hover_hint(self) -> None:
        dialog = self._open(self.trip)

        controls = [*dialog.findChildren(QPushButton), *dialog.findChildren(QCheckBox)]
        missing = [control.text() for control in controls if not control.toolTip()]
        self.assertEqual(missing, [])

    # --- Folders ------------------------------------------------------------

    def test_selecting_a_folder_shows_the_subfolders_checkbox(self) -> None:
        dialog = self._open(self.trip)
        self.assertFalse(dialog.subfolders_check.isVisible())

        self._click(dialog, "2019")

        self.assertEqual(dialog.selected_folders(), [self.year])
        self.assertEqual(dialog.selected_paths(), [])
        self.assertTrue(dialog.subfolders_check.isVisible())
        self.assertFalse(dialog.include_subfolders())
        self.assertEqual(dialog.selection_count_label.text(), "1 folder selected")
        self.assertEqual(dialog.add_button.text(), "Add 1 Folder to Photo List")

        self._click(dialog, "2019")
        self.assertFalse(dialog.subfolders_check.isVisible())

    def test_subfolders_checkbox_starts_as_given(self) -> None:
        dialog = self._open(self.trip, include_subfolders=True)
        self._click(dialog, "2019")

        self.assertTrue(dialog.include_subfolders())
        dialog.subfolders_check.click()
        self.assertFalse(dialog.include_subfolders())

    def test_add_button_counts_photos_and_folders(self) -> None:
        dialog = self._open(self.trip)

        self._click(dialog, "2019")
        self._click(dialog, "a.jpg")
        self._click(dialog, "b.jpg")

        self.assertEqual(dialog.selection_count_label.text(), "2 photos and 1 folder selected")
        self.assertEqual(dialog.add_button.text(), "Add 2 Photos and 1 Folder to Photo List")

    def test_double_clicking_a_folder_opens_it_and_keeps_the_selection(self) -> None:
        dialog = self._open(self.trip)
        self._click(dialog, "a.jpg")

        self._double_click(dialog, "2019")

        self.assertEqual(dialog.current_folder, self.year)
        self.assertEqual(dialog.tree.currentItem().data(0, PATH_ROLE), str(self.year))
        self.assertEqual(self._grid_names(dialog), ["d.jpg"])
        # Opening the folder didn't select it, and a.jpg is still selected.
        self.assertEqual(dialog.selected_folders(), [])
        self.assertEqual(dialog.selected_paths(), [self.trip / "a.jpg"])

    def test_selection_stays_while_moving_between_folders(self) -> None:
        dialog = self._open(self.trip)
        self._click(dialog, "a.jpg")
        dialog.open_folder(self.year)
        self._click(dialog, "d.jpg")

        self.assertEqual(dialog.selected_paths(), [self.trip / "a.jpg", self.year / "d.jpg"])
        self.assertEqual(dialog.add_button.text(), "Add 2 Photos to Photo List")

        # Back in the first folder, a.jpg shows as selected again.
        dialog.up_button.click()
        self.assertTrue(self._grid_item(dialog, "a.jpg").isSelected())
        self.assertFalse(self._grid_item(dialog, "b.jpg").isSelected())
        self.assertEqual(dialog.selected_paths(), [self.trip / "a.jpg", self.year / "d.jpg"])

        # Deselect All clears every folder.
        dialog.deselect_all_button.click()
        self.assertEqual(dialog.selected_paths(), [])
        dialog.open_folder(self.year)
        self.assertFalse(self._grid_item(dialog, "d.jpg").isSelected())

    def _marked(self, dialog: PhotoPickerDialog) -> set[str]:
        return {
            item.text(0)
            for item in dialog.tree.findItems("", Qt.MatchContains | Qt.MatchRecursive)
            if dialog._tree_item_marked(item)
        }

    def test_tree_marks_folders_holding_selected_photos(self) -> None:
        dialog = self._open(self.year)
        self._click(dialog, "d.jpg")
        dialog.open_folder(self.other)

        # 2019 holds d.jpg and shows in the tree (My Trip is expanded), so
        # only 2019 is marked. Home holds My Trip too, but My Trip is its own
        # place in the tree, so Home isn't marked either.
        self.assertTrue(self._tree_item(dialog, "My Trip").isExpanded())
        self.assertEqual(self._marked(dialog), {"2019"})

        # With 2019 hidden, the dot moves up to My Trip.
        self._tree_item(dialog, "My Trip").setExpanded(False)
        self.assertEqual(self._marked(dialog), {"My Trip"})
        self._tree_item(dialog, "My Trip").setExpanded(True)

        # The folder shown is marked too when it holds a selected photo.
        dialog.open_folder(self.year)
        self.assertTrue(dialog._tree_item_marked(dialog.tree.currentItem()))

    def test_a_folder_is_marked_for_its_own_photos_even_when_expanded(self) -> None:
        dialog = self._open(self.year)
        self._click(dialog, "d.jpg")
        dialog.open_folder(self.trip)
        self._click(dialog, "a.jpg")

        self.assertTrue(self._tree_item(dialog, "My Trip").isExpanded())
        self.assertEqual(self._marked(dialog), {"My Trip", "2019"})

    def test_selected_folders_dont_mark_the_tree(self) -> None:
        dialog = self._open(self.trip)
        self._click(dialog, "2019")

        self.assertEqual(self._marked(dialog), set())

        self._click(dialog, "a.jpg")
        self.assertEqual(self._marked(dialog), {"My Trip"})

    def test_one_photo_mode_opens_folders_but_cannot_choose_them(self) -> None:
        dialog = self._open(self.trip, single=True)

        self._click(dialog, "2019")
        self.assertEqual(dialog.selected_folders(), [])
        self.assertFalse(dialog.subfolders_check.isVisible())

        self._double_click(dialog, "2019")
        self.assertEqual(dialog.current_folder, self.year)
        self.assertNotEqual(dialog.result(), PhotoPickerDialog.Accepted)

    def test_late_folder_contents_after_changing_folders_are_ignored(self) -> None:
        dialog = self._open(self.trip)
        generation = dialog._generation
        dialog.open_folder(self.root)

        dialog._apply_folder_summaries((generation, {self.year: (9, 9)}))

        self.assertNotIn("9 photos", " ".join(self._grid_names(dialog)))


if __name__ == "__main__":
    unittest.main()
