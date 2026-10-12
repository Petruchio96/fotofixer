"""
The Windows-only look (gui/styles.py and the widgets that use it). The
platform-dependent parts are checked on Windows only; the rest everywhere.
"""

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication

from gui import styles
from gui.widgets.icons import ICON_SIZE, map_icon


class WindowsLookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_windows_stylesheet_is_only_added_on_windows(self) -> None:
        self.assertEqual(
            styles.WINDOWS_STYLESHEET in styles.APP_STYLESHEET,
            sys.platform == "win32",
        )

    def test_map_icon_text_gap_widens_the_icon(self) -> None:
        # Sizes come back in device pixels (the icons are drawn at 2x).
        plain = map_icon("#1f5fc4").actualSize(QSize(64, 64))
        padded = map_icon("#1f5fc4", text_gap=4).actualSize(QSize(64, 64))
        scale = plain.width() // ICON_SIZE

        self.assertEqual(plain.height(), plain.width())
        self.assertEqual(padded.height(), plain.height())
        self.assertEqual(padded.width(), plain.width() + 4 * scale)


if __name__ == "__main__":
    unittest.main()
