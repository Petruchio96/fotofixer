import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QListWidget,
    QListWidgetItem,
)

from core.models import PhotoInfo
from gui.presenters.thumbnail_items import (
    build_thumbnail_item_data,
    build_thumbnail_item_data_list,
    build_tooltip_text,
    reselect_paths,
)


class ThumbnailItemServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_build_tooltip_text_with_gps(self) -> None:
        self.assertEqual(
            build_tooltip_text("photo.jpg", 40.5, -111.8),
            "photo.jpg\nGPS: 40.500000, -111.800000",
        )

    def test_build_tooltip_text_without_gps(self) -> None:
        self.assertEqual(build_tooltip_text("photo.jpg", 40.5, -111.8, 2050.0), "photo.jpg\nGPS: 40.500000, -111.800000\nAltitude: 6,726 ft")
        self.assertEqual(build_tooltip_text("photo.jpg", 40.5, -111.8, 2050.0, feet=False), "photo.jpg\nGPS: 40.500000, -111.800000\nAltitude: 2,050 m")
        self.assertEqual(build_tooltip_text("photo.jpg", None, None, 2050.0), "photo.jpg\nNo GPS", "no altitude line without GPS")
        self.assertEqual(build_tooltip_text("photo.jpg", None, None), "photo.jpg\nNo GPS")

    def test_build_thumbnail_item_data_maps_photo_info_to_display_fields(self) -> None:
        photo_info = PhotoInfo(
            path=Path("/tmp/photo.jpg"),
            file_type="JPG",
            current_latitude=40.5,
            current_longitude=-111.8,
        )

        item_data = build_thumbnail_item_data(photo_info)

        self.assertEqual(item_data.path, Path("/tmp/photo.jpg"))
        self.assertEqual(item_data.filename, "photo.jpg")
        self.assertTrue(item_data.has_gps)
        self.assertEqual(item_data.latitude, 40.5)
        self.assertEqual(item_data.longitude, -111.8)
        self.assertEqual(item_data.tooltip, "photo.jpg\nGPS: 40.500000, -111.800000")

    def test_build_thumbnail_item_data_list_preserves_order(self) -> None:
        photo_infos = [
            PhotoInfo(
                path=Path("/tmp/two.jpg"),
                file_type="JPG",
                current_latitude=40.5,
                current_longitude=-111.8,
            ),
            PhotoInfo(path=Path("/tmp/one.jpg"), file_type="JPG"),
            PhotoInfo(path=Path("/tmp/Three.jpg"), file_type="JPG"),
        ]

        item_data = build_thumbnail_item_data_list(photo_infos)

        self.assertEqual(
            [entry.filename for entry in item_data],
            ["one.jpg", "Three.jpg", "two.jpg"],
        )

    def test_build_thumbnail_item_data_list_places_files_without_gps_first(self) -> None:
        photo_infos = [
            PhotoInfo(
                path=Path("/tmp/with-gps.jpg"),
                file_type="JPG",
                current_latitude=40.5,
                current_longitude=-111.8,
            ),
            PhotoInfo(path=Path("/tmp/without-gps.jpg"), file_type="JPG"),
        ]

        item_data = build_thumbnail_item_data_list(photo_infos)

        self.assertEqual(
            [(entry.filename, entry.has_gps) for entry in item_data],
            [("without-gps.jpg", False), ("with-gps.jpg", True)],
        )

    def test_reselect_paths_restores_matching_items_only(self) -> None:
        widget = QListWidget()
        widget.setSelectionMode(QListWidget.ExtendedSelection)

        for name in ["one.jpg", "two.jpg", "three.jpg"]:
            item = QListWidgetItem(name)
            # The app stores str(path), which uses backslashes on Windows.
            item.setData(Qt.UserRole, str(Path("/tmp") / name))
            widget.addItem(item)

        header = QListWidgetItem("Files with GPS Coordinates")
        header.setData(Qt.UserRole, None)
        widget.addItem(header)

        reselect_paths(widget, [Path("/tmp/one.jpg"), Path("/tmp/three.jpg")])

        selected = [widget.item(index).text() for index in range(widget.count()) if widget.item(index).isSelected()]
        self.assertEqual(selected, ["one.jpg", "three.jpg"])


if __name__ == "__main__":
    unittest.main()
