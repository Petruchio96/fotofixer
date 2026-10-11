import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

from gui import window_frame


class WindowFrameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_does_nothing_off_windows(self) -> None:
        widget = QWidget()
        with patch.object(window_frame.sys, "platform", "linux"), patch("ctypes.c_uint") as c_uint:
            window_frame.apply_window_border(widget)
        c_uint.assert_not_called()

    def test_sets_the_border_color_on_windows(self) -> None:
        widget = QWidget()
        dwmapi = MagicMock()
        dwmapi.DwmSetWindowAttribute.return_value = 0  # S_OK
        with patch.object(window_frame.sys, "platform", "win32"), patch(
            "ctypes.windll", create=True
        ) as windll:
            windll.dwmapi = dwmapi
            window_frame.apply_window_border(widget)

        attribute = dwmapi.DwmSetWindowAttribute.call_args.args[1]
        self.assertEqual(attribute.value, window_frame.DWMWA_BORDER_COLOR)
        # Windows drew the border, so the app doesn't draw its own.
        self.assertIsNone(widget.findChild(window_frame.WindowEdge))

    def test_never_raises_when_windows_refuses(self) -> None:
        widget = QWidget()
        with patch.object(window_frame.sys, "platform", "win32"), patch(
            "ctypes.windll", create=True
        ) as windll:
            windll.dwmapi.DwmSetWindowAttribute.side_effect = OSError("no DWM")
            window_frame.apply_window_border(widget)

    def test_draws_its_own_edge_when_windows_refuses_the_color(self) -> None:
        # Windows 10 answers E_INVALIDARG for the border color setting.
        widget = QWidget()
        widget.resize(300, 200)
        widget.show()  # like the map, picker, and Settings (called from showEvent)
        self.addCleanup(widget.close)
        with patch.object(window_frame.sys, "platform", "win32"), patch(
            "ctypes.windll", create=True
        ) as windll:
            windll.dwmapi.DwmSetWindowAttribute.return_value = -2147024809
            window_frame.apply_window_border(widget)
            # Shown again (showEvent calls it each time): still one edge.
            window_frame.apply_window_border(widget)

        edges = widget.findChildren(window_frame.WindowEdge)
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0].geometry(), widget.rect())
        self.assertTrue(edges[0].testAttribute(window_frame.Qt.WA_TransparentForMouseEvents))

        widget.resize(500, 400)
        self.assertEqual(edges[0].geometry(), widget.rect())


if __name__ == "__main__":
    unittest.main()
