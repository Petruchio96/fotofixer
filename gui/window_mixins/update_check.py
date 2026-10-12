"""
MainWindow's part of the update check: the Help menu item, the orange
banner, the Check for Updates window, the once-a-day start-up check, and
the hand-over to the installer when the app quits.

The network and the rules live in gui/update_checker.py and
core/updates.py. Nothing here touches the network when the window is
built: the automatic check starts from app.py (start_update_check_later),
so tests that build a MainWindow never reach GitHub, and they replace
_create_update_fetcher with a fake like the map's _create_tile_fetcher.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices

from core.updates import (
    RELEASES_PAGE_URL,
    Asset,
    InstallKind,
    ReleaseInfo,
    UpdateMode,
    UpdatePlan,
    cleanup_download_dir,
    current_version,
    detect_install_kind,
    format_version,
    install_target,
    is_trusted_page_url,
    pick_asset,
    update_plan,
)
from gui import error_log
from gui.update_checker import (
    CHECK_ON_START_SETTING,
    CURRENT,
    FAILURE_MESSAGES,
    NEWER,
    CheckResult,
    NetworkUpdateFetcher,
    UpdateChecker,
    UpdateFetcher,
    UpdateInstaller,
)
from gui.widgets.update_banner import UpdateBanner
from gui.widgets.update_dialog import UpdateDialog

# The automatic check waits until loading photos has had its turn.
STARTUP_CHECK_DELAY_MS = 5000
# Downloads go to the system's temp folder, in a folder of their own.
UPDATE_DIR_NAME = "Photo GPS Editor update"
# What the installer or the update script did, next to the error log.
UPDATE_LOG_NAME = "update-log.txt"

BUSY_MESSAGE = "Finish the current change first, then press Update again."
RESTART_NOTE = "Updating closes the app and reopens it. The undo history is lost."

# The Update button's hover hint, per install kind.
INSTALL_HINTS = {
    InstallKind.WINDOWS_INSTALLED: "Download version {version}, install it, and reopen the app",
    InstallKind.LINUX_APPIMAGE: "Download version {version}, replace this AppImage with it, and reopen the app",
    InstallKind.LINUX_FOLDER: "Download version {version}, replace the app's folder with it, and reopen the app",
    InstallKind.MAC_APP: "Download version {version}, replace the app with it, and reopen it",
}


class UpdateCheckMixin:
    """Mixed into MainWindow (gui/main_window.py)."""

    # --- building ---

    def _init_update_check(self) -> None:
        """State only; the parts that talk to GitHub are built when first needed."""
        self._update_fetcher: UpdateFetcher | None = None
        self._update_checker: UpdateChecker | None = None
        self._update_installer: UpdateInstaller | None = None
        self._update_dialog: UpdateDialog | None = None
        # Set when the download is verified and the app closes to install it;
        # app.py then calls launch_pending_update() after the event loop ends.
        self.pending_update_launch = False
        executable = Path(sys.executable)
        self._install_kind = detect_install_kind(
            frozen=bool(getattr(sys, "frozen", False)),
            platform=sys.platform,
            executable=executable,
            environ=os.environ,
        )
        self._install_target = install_target(self._install_kind, executable, os.environ)

    def _build_update_banner(self) -> UpdateBanner:
        self.update_banner = UpdateBanner()
        self.update_banner.whats_new_requested.connect(self._show_whats_new)
        self.update_banner.action_requested.connect(self._start_update)
        self.update_banner.skip_requested.connect(self._skip_update)
        self.update_banner.dismissed.connect(self._dismiss_update_banner)
        return self.update_banner

    def _build_update_menu(self, help_menu) -> None:
        self.check_updates_action = QAction("Check for Updates...", self)
        self.check_updates_action.triggered.connect(self.check_for_updates)
        help_menu.addAction(self.check_updates_action)

    def _create_update_fetcher(self) -> UpdateFetcher:
        """
        The GitHub client. Tests replace this so they never use the network.
        """
        return NetworkUpdateFetcher(
            user_agent=(
                f"PhotoGPSEditor/{self.app_version} "
                "(+https://github.com/Petruchio96/photo-gps-editor)"
            ),
            parent=self,
        )

    def _update_fetcher_instance(self) -> UpdateFetcher:
        if self._update_fetcher is None:
            self._update_fetcher = self._create_update_fetcher()
        return self._update_fetcher

    def _checker(self) -> UpdateChecker:
        if self._update_checker is None:
            self._update_checker = UpdateChecker(
                fetcher=self._update_fetcher_instance(),
                settings=self.settings,
                current_version=current_version(self.app_version),
                parent=self,
            )
        return self._update_checker

    def _installer(self) -> UpdateInstaller:
        if self._update_installer is None:
            installer = UpdateInstaller(
                fetcher=self._update_fetcher_instance(),
                kind=self._install_kind,
                download_dir=self._update_download_dir(),
                log_path=error_log.log_path().parent / UPDATE_LOG_NAME,
                parent=self,
            )
            installer.progress.connect(self._update_progress)
            installer.failed.connect(self._update_failed)
            installer.cancelled.connect(self._update_cancelled)
            installer.ready.connect(self._update_ready)
            self._update_installer = installer
        return self._update_installer

    def _update_download_dir(self) -> Path:
        temp = QStandardPaths.writableLocation(QStandardPaths.TempLocation)
        return Path(temp or Path.home()) / UPDATE_DIR_NAME

    # --- the setting ---

    @property
    def check_updates_on_start(self) -> bool:
        return self.settings.value(CHECK_ON_START_SETTING, True, type=bool)

    def set_check_updates_on_start(self, on: bool) -> None:
        self.settings.setValue(CHECK_ON_START_SETTING, on)

    # --- checking ---

    def start_update_check_later(self) -> None:
        """
        From app.py once the window is shown: tidy up after any earlier
        update, then check in a few seconds (once a day, if the setting is on).
        """
        cleanup_download_dir(self._update_download_dir())
        QTimer.singleShot(STARTUP_CHECK_DELAY_MS, self, self._start_automatic_update_check)

    def _start_automatic_update_check(self) -> None:
        if not self.isVisible() or not self.check_updates_on_start:
            return
        checker = self._checker()
        if not checker.is_due():
            return
        checker.check(self._handle_automatic_result)

    def _handle_automatic_result(self, result: CheckResult) -> None:
        # Quiet unless there is something new; failures went to the error log.
        if result.status != NEWER:
            return
        checker = self._checker()
        if checker.is_skipped(result.release) or checker.is_dismissed(result.release):
            return
        self._show_update_banner(result.release)

    def check_for_updates(self) -> None:
        """Help > Check for Updates: always asks, and always answers in the window."""
        dialog = self._open_update_dialog()
        dialog.show_checking()
        self._checker().check(self._handle_manual_result)

    def _handle_manual_result(self, result: CheckResult) -> None:
        dialog = self._update_dialog
        if dialog is None:
            # Closed before GitHub answered.
            return
        if result.status == NEWER:
            self._show_release_in_dialog(dialog, result.release)
            checker = self._checker()
            if not checker.is_skipped(result.release):
                self._show_update_banner(result.release)
        elif result.status == CURRENT:
            dialog.show_up_to_date(format_version(self._checker().current_version))
        else:
            dialog.show_error(FAILURE_MESSAGES[result.status])

    # --- what to offer ---

    def _plan_for(self, release: ReleaseInfo) -> tuple[UpdatePlan, Asset | None]:
        asset = pick_asset(release, self._install_kind)
        return update_plan(self._install_kind, self._install_target, asset), asset

    def _offer_for(self, release: ReleaseInfo) -> tuple[UpdateMode, str, str, str]:
        """The button's label and hover hint, and a note under the notes."""
        plan, _asset = self._plan_for(release)
        version = format_version(release.version)
        if plan.mode == UpdateMode.INSTALL:
            hint = INSTALL_HINTS[self._install_kind].format(version=version)
            return plan.mode, "Update", hint, RESTART_NOTE
        if plan.mode == UpdateMode.DOWNLOAD:
            return (
                plan.mode,
                "Download",
                f"Open the release page in your browser ({plan.reason})",
                f"This copy can't update itself: {plan.reason}.",
            )
        return plan.mode, "", "", ""

    def _current_text(self) -> str:
        return format_version(self._checker().current_version)

    def _show_update_banner(self, release: ReleaseInfo) -> None:
        mode, label, hint, _note = self._offer_for(release)
        self.update_banner.set_release(release, self._current_text(), mode, label, hint)

    def _show_release_in_dialog(self, dialog: UpdateDialog, release: ReleaseInfo) -> None:
        mode, label, hint, note = self._offer_for(release)
        dialog.show_release(release, self._current_text(), mode, label, hint, note)

    # --- the window ---

    def _open_update_dialog(self) -> UpdateDialog:
        if self._update_dialog is not None:
            self._update_dialog.raise_()
            return self._update_dialog
        dialog = UpdateDialog(self)
        dialog.action_requested.connect(self._start_update)
        dialog.skip_requested.connect(self._skip_update)
        dialog.cancel_requested.connect(self._cancel_update_download)

        def closed(_result: int) -> None:
            if self._update_dialog is dialog:
                self._update_dialog = None
            # Closed (Esc) while downloading: stop the download too.
            self._cancel_update_download()
            dialog.deleteLater()

        dialog.finished.connect(closed)
        # Modal and show(), not exec() (see MainWindow.show_message).
        dialog.setWindowModality(Qt.ApplicationModal)
        dialog.show()
        self._update_dialog = dialog
        return dialog

    def _show_whats_new(self) -> None:
        release = self._checker().latest
        if release is None:
            return
        self._show_release_in_dialog(self._open_update_dialog(), release)

    def _skip_update(self) -> None:
        release = self._checker().latest
        if release is None:
            return
        self._checker().skip(release)
        self.update_banner.hide()
        if self._update_dialog is not None:
            self._update_dialog.reject()

    def _dismiss_update_banner(self) -> None:
        release = self._checker().latest
        if release is not None:
            self._checker().dismiss(release)
        self.update_banner.hide()

    # --- updating ---

    def _start_update(self) -> None:
        """The Update (or Download) button, in the banner or the window."""
        release = self._checker().latest
        if release is None:
            return
        plan, asset = self._plan_for(release)
        if plan.mode == UpdateMode.DOWNLOAD:
            self._open_release_page(release)
            return
        if plan.mode != UpdateMode.INSTALL or asset is None:
            return
        dialog = self._open_update_dialog()
        if self._input_blocker is not None:
            # Writing to the photos: don't close the app in the middle of it.
            self._show_release_in_dialog(dialog, release)
            dialog.show_error(BUSY_MESSAGE)
            return
        self._show_release_in_dialog(dialog, release)
        dialog.show_progress(0, asset.size)
        self._installer().start(asset)

    def _open_release_page(self, release: ReleaseInfo) -> None:
        url = release.page_url if is_trusted_page_url(release.page_url) else RELEASES_PAGE_URL
        self._open_url(url)

    def _open_url(self, url: str) -> None:
        """In the browser. Tests replace this."""
        QDesktopServices.openUrl(QUrl(url))

    def _update_progress(self, received: int, total: int) -> None:
        if self._update_dialog is not None:
            self._update_dialog.show_progress(received, total)

    def _update_failed(self, text: str) -> None:
        if self._update_dialog is not None:
            self._update_dialog.show_error(text)

    def _update_cancelled(self) -> None:
        dialog = self._update_dialog
        release = self._checker().latest
        if dialog is not None and release is not None:
            self._show_release_in_dialog(dialog, release)

    def _cancel_update_download(self) -> None:
        if self._update_installer is not None and self._update_installer.is_downloading:
            self._update_installer.cancel()

    def _update_ready(self) -> None:
        """Downloaded and verified: close the app; the installer takes over."""
        dialog = self._update_dialog
        if self._input_blocker is not None:
            if dialog is not None:
                dialog.show_error(BUSY_MESSAGE)
            return
        if dialog is not None:
            dialog.show_closing()
        self.pending_update_launch = True
        self.close()
        if self.isVisible():
            # closeEvent refused (a write started meanwhile).
            self.pending_update_launch = False
            if self._update_dialog is not None:
                self._update_dialog.show_error(BUSY_MESSAGE)

    def launch_pending_update(self) -> None:
        """
        From app.py after the event loop has ended: start Setup or the
        update script. ExifTool is closed first so nothing of ours is still
        running from the install folder.
        """
        if not self.pending_update_launch:
            return
        self.pending_update_launch = False
        close = getattr(self.exiftool, "close", None)
        if callable(close):
            close()
        self._installer().launch(target=self._install_target, app_pid=os.getpid())
