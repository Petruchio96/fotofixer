import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QHelpEvent
from PySide6.QtWidgets import QApplication, QListWidget, QListWidgetItem, QPushButton, QToolTip

from gui.hints import HINT_WIDTH, LINE_SLACK, install_hint_wrapping, wrap_hint


class WrapHintTests(unittest.TestCase):
    def test_short_hints_are_left_alone(self) -> None:
        self.assertEqual(wrap_hint("Zoom in (or scroll the mouse wheel)"), "Zoom in (or scroll the mouse wheel)")

    def test_a_long_hint_wraps_onto_balanced_lines_within_the_width(self) -> None:
        hint = (
            "Click this, then click a photo with GPS in the Photo List to copy "
            "its location. A selected photo becomes the source and is deselected."
        )
        lines = wrap_hint(hint).split("\n")
        self.assertEqual(len(lines), 3)
        self.assertTrue(all(len(line) <= HINT_WIDTH + LINE_SLACK for line in lines), lines)
        self.assertLess(max(map(len, lines)) - min(map(len, lines)), 20, lines)
        self.assertEqual(" ".join(lines), hint, "every word kept, in order")

    def test_breaks_fall_at_a_sentence_end_when_that_keeps_the_lines_balanced(self) -> None:
        hint = "Open a map: click it, or drag the pin, to set the New Location. Photos in the Photo List with GPS show as dots."
        self.assertEqual(
            wrap_hint(hint),
            "Open a map: click it, or drag the pin, to set the New Location.\nPhotos in the Photo List with GPS show as dots.",
        )

    def test_no_orphan_last_line(self) -> None:
        hint = "Remove the selected photos from this list (Delete key). Files are not changed or deleted."
        lines = wrap_hint(hint).split("\n")
        self.assertEqual(len(lines), 2)
        self.assertGreaterEqual(len(lines[-1]), 12)

    def test_existing_line_breaks_are_kept_and_each_paragraph_wrapped_on_its_own(self) -> None:
        hint = "Type or paste coordinates.\nA pair copied from Google Maps can be pasted into either field as is."
        lines = wrap_hint(hint).split("\n")
        self.assertEqual(lines[0], "Type or paste coordinates.", "the short first paragraph is untouched")
        self.assertEqual(len(lines), 3, "the long second paragraph wraps in two")
        self.assertLess(abs(len(lines[1]) - len(lines[2])), 10, lines)


class HintWrapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        install_hint_wrapping()

    def _hover(self, widget) -> str:
        """Ask the widget for its tooltip the way the mouse does; returns the text shown."""
        QToolTip.hideText()
        event = QHelpEvent(QHelpEvent.ToolTip, QPoint(5, 5), widget.mapToGlobal(QPoint(5, 5)))
        self.app.sendEvent(widget, event)
        return QToolTip.text()

    def test_a_widgets_long_hint_is_shown_wrapped(self) -> None:
        button = QPushButton("Remove GPS")
        hint = "Delete the GPS coordinates stored in the selected photos that have them. You can undo this afterwards."
        button.setToolTip(hint)
        button.show()
        shown = self._hover(button)
        self.assertEqual(shown, wrap_hint(hint))
        self.assertEqual(len(shown.split("\n")), 2)
        self.assertNotIn("\n", button.toolTip(), "the hint itself is unchanged")
        button.close()

    def test_a_list_rows_hint_is_shown_wrapped(self) -> None:
        view = QListWidget()
        item = QListWidgetItem("row")
        item.setToolTip("Taken 2 h 10 min before the track starts. If the camera's clock or zone was wrong, fix it on the Date & Time tab first.")
        view.addItem(item)
        view.show()
        shown = self._hover(view.viewport())
        self.assertIn("\n", shown)
        self.assertTrue(all(len(line) <= HINT_WIDTH + LINE_SLACK for line in shown.split("\n")), shown)
        view.close()


if __name__ == "__main__":
    unittest.main()
