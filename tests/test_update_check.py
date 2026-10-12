"""
The update check in the main window, with a fake GitHub: the banner, the
Check for Updates window, Skip, once a day, the download, and the
hand-over to the installer. Never touches the network.
"""

import datetime
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QDialog, QMenu, QPushButton

from core import updates
from core.updates import (
    LINUX_APPIMAGE_ASSET,
    LINUX_TARBALL_ASSET,
    MACOS_ZIP_ASSET,
    WINDOWS_SETUP_ASSET,
    InstallKind,
)
from gui import update_checker
from gui.main_window import MainWindow
from gui.update_checker import (
    CHECK_ON_START_SETTING,
    DOWNLOAD_CANCELLED,
    DOWNLOAD_OK,
    LAST_CHECK_SETTING,
    SKIPPED_VERSION_SETTING,
    UpdateFetcher,
)
from gui.window_mixins import update_check

PAGE_URL = "https://github.com/Petruchio96/photo-gps-editor/releases/tag/v9.0.0"
DOWNLOAD_DATA = b"setup " * 5000


def release_json(tag: str = "v9.0.0", *, data: bytes = DOWNLOAD_DATA, asset_url: str | None = None) -> str:
    """GitHub's answer for a release with all four files."""
    digest = "sha256:" + hashlib.sha256(data).hexdigest()
    assets = []
    for name in (WINDOWS_SETUP_ASSET, MACOS_ZIP_ASSET, LINUX_APPIMAGE_ASSET, LINUX_TARBALL_ASSET):
        assets.append({
            "name": name,
            "browser_download_url": asset_url or f"https://github.com/Petruchio96/photo-gps-editor/releases/download/{tag}/{name}",
            "size": len(data),
            "digest": digest,
        })
    return json.dumps({
        "tag_name": tag,
        "name": f"Version {tag[1:]}",
        "body": "## What's new\n- Faster everything.",
        "html_url": PAGE_URL,
        "assets": assets,
    })


class FakeUpdateFetcher(UpdateFetcher):
    """Answers at once, from the attributes set by the test."""

    def __init__(self) -> None:
        super().__init__()
        self.release_requests: list[str] = []
        self.downloads: list[tuple[str, Path]] = []
        self.status = 200
        self.body = release_json()
        self.answer_at_once = True
        self.download_data = DOWNLOAD_DATA
        self.download_outcome = DOWNLOAD_OK
        self._pending_download = None

    def fetch_release(self, url: str) -> None:
        self.release_requests.append(url)
        if self.answer_at_once:
            self.answer()

    def answer(self) -> None:
        self.release_finished.emit(self.status, self.body)

    def download(self, url: str, destination: Path, verifier) -> None:
        self.downloads.append((url, destination))
        self._pending_download = (destination, verifier)
        if self.answer_at_once:
            self.finish_download()

    def finish_download(self) -> None:
        destination, verifier = self._pending_download
        self._pending_download = None
        if self.download_outcome == DOWNLOAD_OK:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(self.download_data)
            verifier.update(self.download_data)
            self.download_progress.emit(len(self.download_data), len(self.download_data))
        self.download_finished.emit(self.download_outcome, "fake")

    def cancel(self) -> None:
        if self._pending_download is not None:
            self._pending_download = None
            self.download_finished.emit(DOWNLOAD_CANCELLED, "fake")

    def is_busy(self) -> bool:
        return self._pending_download is not None


class UpdateCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.settings = QSettings(str(self.root / "settings.ini"), QSettings.IniFormat)
        self.fetcher = FakeUpdateFetcher()
        self.spawned: list[tuple] = []

        self.window = MainWindow(settings=self.settings)
        self.window._create_update_fetcher = lambda: self.fetcher
        self.window._update_download_dir = lambda: self.root / "update"
        self.opened_urls: list[str] = []
        self.window._open_url = self.opened_urls.append
        # An installed Windows copy unless a test says otherwise.
        self.window._install_kind = InstallKind.WINDOWS_INSTALLED
        self.window._install_target = self.root / "Photo GPS Editor.exe"
        self.window.show()

    def tearDown(self) -> None:
        self.window.close()

    def _automatic_check(self) -> None:
        self.window._start_automatic_update_check()

    def _dialog(self):
        return self.window._update_dialog

    def _spawn(self, command, **kwargs) -> None:
        self.spawned.append((command, kwargs))

    # --- the banner ---

    def test_banner_shows_for_a_newer_version(self) -> None:
        self._automatic_check()

        banner = self.window.update_banner
        self.assertTrue(banner.isVisible())
        self.assertIn("Version 9.0.0 is available", banner.text_label.text())
        self.assertIn("you have 1.8.0", banner.text_label.text())
        self.assertEqual(banner.action_button.text(), "Update")
        self.assertIn("install it", banner.action_button.toolTip())
        self.assertEqual(self.fetcher.release_requests, [updates.LATEST_RELEASE_API_URL])
        for button in banner.findChildren(QPushButton):
            self.assertTrue(button.toolTip(), button.text())

    def test_banner_stays_hidden_for_the_same_or_an_older_version(self) -> None:
        for tag in ("v1.8.0", "v1.0.0"):
            self.fetcher.body = release_json(tag)
            self.settings.remove(LAST_CHECK_SETTING)
            self._automatic_check()
            self.assertFalse(self.window.update_banner.isVisible(), tag)
        self.assertEqual(len(self.fetcher.release_requests), 2)

    def test_skip_hides_this_version_but_not_a_newer_one(self) -> None:
        self._automatic_check()
        self.window.update_banner.skip_button.click()

        self.assertFalse(self.window.update_banner.isVisible())
        self.assertEqual(self.settings.value(SKIPPED_VERSION_SETTING, "", type=str), "v9.0.0")

        self.settings.remove(LAST_CHECK_SETTING)
        self._automatic_check()
        self.assertFalse(self.window.update_banner.isVisible())

        self.fetcher.body = release_json("v9.1.0")
        self.settings.remove(LAST_CHECK_SETTING)
        self._automatic_check()
        self.assertTrue(self.window.update_banner.isVisible())
        self.assertIn("9.1.0", self.window.update_banner.text_label.text())

    def test_close_hides_the_banner_until_the_next_start(self) -> None:
        self._automatic_check()
        self.window.update_banner.close_button.click()

        self.assertFalse(self.window.update_banner.isVisible())
        self.settings.remove(LAST_CHECK_SETTING)
        self._automatic_check()
        self.assertFalse(self.window.update_banner.isVisible())
        # Not remembered as skipped: a new session shows it again.
        self.assertEqual(self.settings.value(SKIPPED_VERSION_SETTING, "", type=str), "")

    # --- when it checks ---

    def test_checks_once_a_day(self) -> None:
        today = datetime.datetime.now().isoformat(timespec="seconds")
        self.settings.setValue(LAST_CHECK_SETTING, today)
        self._automatic_check()
        self.assertEqual(self.fetcher.release_requests, [])

        yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).isoformat(timespec="seconds")
        self.settings.setValue(LAST_CHECK_SETTING, yesterday)
        self._automatic_check()
        self.assertEqual(len(self.fetcher.release_requests), 1)
        # Today's check is on record.
        self.assertTrue(self.settings.value(LAST_CHECK_SETTING, "", type=str).startswith(today[:10]))

    def test_offline_does_not_count_as_todays_check(self) -> None:
        self.fetcher.status = 0
        self.fetcher.body = "Host not found"
        with patch.object(update_checker.error_log, "log") as log:
            self._automatic_check()
        self.assertFalse(self.window.update_banner.isVisible())
        self.assertEqual(self.settings.value(LAST_CHECK_SETTING, "", type=str), "")
        log.assert_called_once()
        self.assertIn("offline", log.call_args.args[0])

    def test_setting_off_skips_the_automatic_check(self) -> None:
        self.settings.setValue(CHECK_ON_START_SETTING, False)
        self._automatic_check()
        self.assertEqual(self.fetcher.release_requests, [])
        # The menu item still checks.
        self.window.check_for_updates()
        self.assertEqual(len(self.fetcher.release_requests), 1)

    def test_a_second_check_waits_for_the_first(self) -> None:
        self.fetcher.answer_at_once = False
        self.window.check_for_updates()
        self._automatic_check()
        self.assertEqual(len(self.fetcher.release_requests), 1)
        self.assertIn("Checking", self._dialog().headline.text())

        self.fetcher.answer()
        self.assertIn("Version 9.0.0 is available", self._dialog().headline.text())
        self.assertTrue(self.window.update_banner.isVisible())

    def test_pretend_version_makes_the_app_think_it_is_old(self) -> None:
        self.fetcher.body = release_json("v1.7.0")
        with patch.dict(os.environ, {updates.PRETEND_VERSION_ENV: "1.0.0"}):
            self._automatic_check()
        banner = self.window.update_banner
        self.assertTrue(banner.isVisible())
        self.assertIn("you have 1.0.0", banner.text_label.text())

    # --- the window ---

    def test_help_menu_has_check_for_updates(self) -> None:
        help_menu = next(
            menu for menu in self.window.menuBar().findChildren(QMenu) if menu.title() == "&Help"
        )
        actions = help_menu.actions()
        self.assertIn(self.window.check_updates_action, actions)
        self.assertLess(actions.index(self.window.check_updates_action), actions.index(self.window.about_action))

    def test_manual_check_shows_up_to_date(self) -> None:
        self.fetcher.body = release_json("v1.8.0")
        self.window.check_for_updates()
        dialog = self._dialog()
        self.assertTrue(dialog.isVisible())
        self.assertIn("up to date (version 1.8.0)", dialog.headline.text())
        self.assertFalse(dialog.action_button.isVisible())
        self.assertFalse(self.window.update_banner.isVisible())

    def test_manual_check_offline_says_so(self) -> None:
        self.fetcher.status = 0
        with patch.object(update_checker.error_log, "log"):
            self.window.check_for_updates()
        self.assertEqual(self._dialog().error_label.text(), update_checker.FAILURE_MESSAGES[update_checker.OFFLINE])
        self.assertTrue(self._dialog().error_label.isVisible())

    def test_manual_check_rate_limited_says_so(self) -> None:
        self.fetcher.status = 403
        self.fetcher.body = '{"message": "API rate limit exceeded"}'
        with patch.object(update_checker.error_log, "log"):
            self.window.check_for_updates()
        self.assertIn("busy", self._dialog().error_label.text())

    def test_manual_check_shows_the_release_notes(self) -> None:
        self.window.check_for_updates()
        dialog = self._dialog()
        self.assertIn("Faster everything", dialog.notes_label.text())
        self.assertTrue(dialog.notes_area.isVisible())
        self.assertEqual(dialog.action_button.text(), "Update")
        self.assertIn("undo history is lost", dialog.note_label.text())
        for button in dialog.findChildren(QPushButton):
            self.assertTrue(button.toolTip(), button.text())

    def test_whats_new_opens_the_window_from_the_banner(self) -> None:
        self._automatic_check()
        self.window.update_banner.whats_new_button.click()
        self.assertIn("Faster everything", self._dialog().notes_label.text())

    def test_skip_from_the_window_closes_it_and_the_banner(self) -> None:
        self._automatic_check()
        self.window.update_banner.whats_new_button.click()
        dialog = self._dialog()
        dialog.skip_button.click()
        self.assertFalse(dialog.isVisible())
        self.assertIsNone(self._dialog())
        self.assertFalse(self.window.update_banner.isVisible())
        self.assertEqual(self.settings.value(SKIPPED_VERSION_SETTING, "", type=str), "v9.0.0")

    # --- what each copy is offered ---

    def test_button_per_install_kind(self) -> None:
        writable_target = self.root / "apps" / "Photo_GPS_Editor-x86_64.AppImage"
        writable_target.parent.mkdir()
        writable_target.write_bytes(b"old")
        cases = [
            (InstallKind.WINDOWS_INSTALLED, self.root / "x.exe", "Update", "install it"),
            (InstallKind.LINUX_APPIMAGE, writable_target, "Update", "replace this AppImage"),
            (InstallKind.LINUX_FOLDER, writable_target.parent, "Update", "replace the app's folder"),
            (InstallKind.MAC_APP, self.root / "apps" / "Photo GPS Editor.app", "Update", "replace the app"),
            (InstallKind.WINDOWS_PORTABLE, None, "Download", "run the new Setup"),
            (InstallKind.MAC_TRANSLOCATED, None, "Download", "Applications"),
            (InstallKind.LINUX_FOLDER, None, "Download", "laid out"),
        ]
        for kind, target, label, hint_part in cases:
            self.window._install_kind = kind
            self.window._install_target = target
            self.settings.remove(LAST_CHECK_SETTING)
            self._automatic_check()
            banner = self.window.update_banner
            self.assertEqual(banner.action_button.text(), label, kind)
            self.assertIn(hint_part, banner.action_button.toolTip(), kind)
            self.assertTrue(banner.action_button.isVisible(), kind)

    def test_source_copies_only_get_a_notice(self) -> None:
        self.window._install_kind = InstallKind.SOURCE
        self.window._install_target = None
        self._automatic_check()
        banner = self.window.update_banner
        self.assertTrue(banner.isVisible())
        self.assertIn("Pull the latest code", banner.text_label.text())
        self.assertFalse(banner.action_button.isVisible())
        self.assertFalse(banner.skip_button.isVisible())
        banner.whats_new_button.click()
        self.assertFalse(self._dialog().action_button.isVisible())
        self.assertIn("Pull the latest code", self._dialog().note_label.text())

    def test_download_button_opens_the_release_page(self) -> None:
        self.window._install_kind = InstallKind.WINDOWS_PORTABLE
        self.window._install_target = None
        self._automatic_check()
        self.window.update_banner.action_button.click()
        self.assertEqual(self.opened_urls, [PAGE_URL])
        self.assertEqual(self.fetcher.downloads, [])

    # --- updating ---

    def test_update_downloads_verifies_and_closes_the_app(self) -> None:
        self._automatic_check()
        self.window.update_banner.action_button.click()

        self.assertEqual(len(self.fetcher.downloads), 1)
        url, destination = self.fetcher.downloads[0]
        self.assertTrue(url.endswith(WINDOWS_SETUP_ASSET))
        self.assertEqual(destination, self.root / "update" / WINDOWS_SETUP_ASSET)
        self.assertTrue(destination.exists())
        self.assertTrue(self.window.pending_update_launch)
        self.assertFalse(self.window.isVisible())

        self.window._installer()._spawn = self._spawn
        self.window.launch_pending_update()
        self.assertFalse(self.window.pending_update_launch)
        (command, kwargs), = self.spawned
        self.assertEqual(command[0], str(destination))
        self.assertIn("/SILENT", command)
        self.assertIn("/CLOSEAPPLICATIONS", command)
        self.assertIn("creationflags", kwargs)
        # Only once.
        self.window.launch_pending_update()
        self.assertEqual(len(self.spawned), 1)

    def test_posix_update_runs_the_script_detached(self) -> None:
        target = self.root / "apps" / "Photo_GPS_Editor-x86_64.AppImage"
        target.parent.mkdir()
        target.write_bytes(b"old")
        self.window._install_kind = InstallKind.LINUX_APPIMAGE
        self.window._install_target = target
        self._automatic_check()
        self.window.update_banner.action_button.click()
        self.assertTrue(self.window.pending_update_launch)

        self.window._installer()._spawn = self._spawn
        self.window.launch_pending_update()
        (command, kwargs), = self.spawned
        self.assertEqual(command[0], "/bin/sh")
        script = Path(command[1]).read_text(encoding="utf-8")
        self.assertIn(f"kill -0 {os.getpid()}", script)
        self.assertIn(target.name, script)
        self.assertTrue(kwargs["start_new_session"])

    def test_damaged_download_is_refused_and_deleted(self) -> None:
        self.fetcher.download_data = b"not what GitHub promised"
        self._automatic_check()
        with patch.object(update_checker.error_log, "log") as log:
            self.window.update_banner.action_button.click()

        dialog = self._dialog()
        self.assertEqual(dialog.error_label.text(), update_checker.DAMAGED_MESSAGE)
        self.assertTrue(dialog.action_button.isVisible())
        self.assertFalse((self.root / "update" / WINDOWS_SETUP_ASSET).exists())
        self.assertFalse(self.window.pending_update_launch)
        self.assertTrue(self.window.isVisible())
        self.assertIn("damaged", log.call_args.args[0])

    def test_untrusted_download_address_is_refused(self) -> None:
        self.fetcher.body = release_json(asset_url="https://evil.example/setup.exe")
        self._automatic_check()
        with patch.object(update_checker.error_log, "log"):
            self.window.update_banner.action_button.click()
        self.assertIn("unexpected address", self._dialog().error_label.text())
        self.assertEqual(self.fetcher.downloads, [])

    def test_cancel_stops_the_download(self) -> None:
        self.fetcher.answer_at_once = False
        self.window.check_for_updates()
        self.fetcher.answer()
        dialog = self._dialog()
        dialog.action_button.click()
        self.assertTrue(dialog.progress_bar.isVisible())
        self.assertTrue(dialog.cancel_button.isVisible())
        self.assertFalse(dialog.action_button.isVisible())

        dialog.cancel_button.click()
        self.assertFalse(dialog.progress_bar.isVisible())
        self.assertTrue(dialog.action_button.isVisible())
        self.assertFalse(self.window.pending_update_launch)
        self.assertFalse((self.root / "update" / WINDOWS_SETUP_ASSET).exists())

    def test_closing_the_window_stops_the_download(self) -> None:
        self.fetcher.answer_at_once = False
        self.window.check_for_updates()
        self.fetcher.answer()
        dialog = self._dialog()
        dialog.action_button.click()
        self.assertTrue(self.fetcher.is_busy())
        dialog.reject()
        self.assertFalse(self.fetcher.is_busy())
        self.assertIsNone(self._dialog())

    def test_update_waits_for_a_write_in_progress(self) -> None:
        self._automatic_check()
        self.window._input_blocker = object()
        try:
            self.window.update_banner.action_button.click()
            self.assertEqual(self._dialog().error_label.text(), update_check.BUSY_MESSAGE)
            self.assertEqual(self.fetcher.downloads, [])
            self.assertTrue(self.window.isVisible())
        finally:
            self.window._input_blocker = None

    # --- settings ---

    def test_settings_checkbox_controls_the_automatic_check(self) -> None:
        self.window.open_settings()
        dialog = self.window._settings_dialog
        self.assertTrue(dialog.check_updates_check.isChecked())
        self.assertFalse(dialog.save_button.isEnabled())
        dialog.check_updates_check.setChecked(False)
        self.assertTrue(dialog.save_button.isEnabled())
        dialog.done(QDialog.Accepted)

        self.assertFalse(self.window.check_updates_on_start)
        self.assertFalse(self.settings.value(CHECK_ON_START_SETTING, True, type=bool))
        self._automatic_check()
        self.assertEqual(self.fetcher.release_requests, [])


if __name__ == "__main__":
    unittest.main()
