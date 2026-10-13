import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import qWarning
from PySide6.QtWidgets import QApplication

from gui import error_log


class ErrorLogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.log = Path(temp_dir.name) / "logs" / error_log.LOG_NAME
        # Put the global hooks back afterwards.
        saved = (sys.excepthook, error_log._log_file)
        self.addCleanup(self._restore, saved)

    def _restore(self, saved) -> None:
        import faulthandler

        faulthandler.disable()
        error_log.qInstallMessageHandler(None)
        if error_log._log_file is not None and error_log._log_file is not saved[1]:
            error_log._log_file.close()
        sys.excepthook, error_log._log_file = saved

    def test_unexpected_errors_are_logged_and_reported(self) -> None:
        shown = []
        with patch.object(error_log, "log_path", return_value=self.log), \
                patch.object(error_log.QMessageBox, "show", new=lambda dialog: shown.append(dialog.text())), \
                patch.object(sys, "__stderr__", None):
            self.assertEqual(error_log.install(), self.log)
            try:
                raise ValueError("picker broke")
            except ValueError:
                sys.excepthook(*sys.exc_info())

        text = self.log.read_text(encoding="utf-8")
        self.assertIn("FotoFixer started", text)
        self.assertIn("ValueError: picker broke", text)
        self.assertEqual(len(shown), 1)
        self.assertIn(str(self.log), shown[0])
        error_log._open_message.done(0)
        self.assertIsNone(error_log._open_message)

    def test_log_writes_a_note_without_a_pop_up(self) -> None:
        shown = []
        with patch.object(error_log, "log_path", return_value=self.log),                 patch.object(error_log.QMessageBox, "show", new=lambda dialog: shown.append(dialog)),                 patch.object(sys, "__stderr__", None):
            error_log.install()
            error_log.log("Update check: offline")

        self.assertIn("Update check: offline", self.log.read_text(encoding="utf-8"))
        self.assertEqual(shown, [])

    def test_qt_messages_are_logged(self) -> None:
        with patch.object(error_log, "log_path", return_value=self.log), \
                patch.object(sys, "__stderr__", None):
            error_log.install()
            qWarning("something odd")

        self.assertIn("Qt warning: something odd", self.log.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
