import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QSettings

from gui.settings_migration import COPIED_KEY, copy_settings_from_old_name


class SettingsMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.old = QSettings(str(Path(folder.name) / "old.ini"), QSettings.IniFormat)
        self.new = QSettings(str(Path(folder.name) / "new.ini"), QSettings.IniFormat)
        self.old.setValue("keepBackups", True)
        self.old.setValue("map/esriKey", "abc123")
        self.old.setValue("lastPhotoFolder", "/home/me/Pictures")

    def test_first_start_copies_the_old_settings(self) -> None:
        self.assertEqual(copy_settings_from_old_name(self.new, self.old), 3)
        self.assertEqual(self.new.value("map/esriKey"), "abc123")
        self.assertTrue(self.new.value("keepBackups", type=bool))
        self.assertEqual(self.new.value("lastPhotoFolder"), "/home/me/Pictures")
        # The old settings are left as they were.
        self.assertEqual(self.old.value("map/esriKey"), "abc123")

    def test_only_once(self) -> None:
        copy_settings_from_old_name(self.new, self.old)
        self.new.setValue("map/esriKey", "changed later")
        self.assertEqual(copy_settings_from_old_name(self.new, self.old), 0)
        self.assertEqual(self.new.value("map/esriKey"), "changed later")

    def test_new_settings_of_its_own_are_never_replaced(self) -> None:
        self.new.setValue("map/esriKey", "already set")
        self.assertEqual(copy_settings_from_old_name(self.new, self.old), 0)
        self.assertEqual(self.new.value("map/esriKey"), "already set")

    def test_nothing_to_copy_is_remembered_too(self) -> None:
        self.old.clear()
        self.assertEqual(copy_settings_from_old_name(self.new, self.old), 0)
        self.assertTrue(self.new.value(COPIED_KEY, type=bool))


if __name__ == "__main__":
    unittest.main()
