import os
import shutil
import subprocess
import sys

from PySide6.QtCore import QSettings
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox, QStyleFactory

from core.exiftool_wrapper import ExifToolWrapper
from core.runtime_paths import resource_path
from gui import error_log
from gui.gc_guard import GuiThreadGarbageCollector
from gui.main_window import MainWindow
from gui.settings_migration import copy_settings_from_old_name

MISSING_EXIFTOOL_MESSAGE = (
    "FotoFixer needs ExifTool to read and write photo metadata, "
    "but ExifTool could not be found.\n\n"
    "Install ExifTool from https://exiftool.org "
    "(on Debian, Ubuntu, or Linux Mint: sudo apt install libimage-exiftool-perl), "
    "then start FotoFixer again."
)


# Where Linux desktops keep the mouse pointer size and theme, checked in order.
DESKTOP_INTERFACE_SCHEMAS = ("org.cinnamon.desktop.interface", "org.gnome.desktop.interface")


def _gsettings_value(schema: str, key: str) -> str:
    """
    One gsettings value as text without quotes, or "" if it can't be read.
    """
    try:
        result = subprocess.run(
            ["gsettings", "get", schema, key],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip().strip("'")


def match_desktop_cursor() -> None:
    """
    Use the desktop's mouse pointer size and theme on Linux.

    Cinnamon and GNOME keep them in gsettings, which only GTK apps read. Qt
    reads XCURSOR_SIZE / XCURSOR_THEME (or Xcursor.size in the X settings)
    and otherwise works the size out from the font DPI, which can make the
    pointer a little smaller inside the app. Must run before QApplication.
    Settings the user made themselves (the environment variables) win.
    """
    if not sys.platform.startswith("linux") or shutil.which("gsettings") is None:
        return
    for schema in DESKTOP_INTERFACE_SCHEMAS:
        size = _gsettings_value(schema, "cursor-size")
        if not size.isdigit() or int(size) <= 0:
            continue
        os.environ.setdefault("XCURSOR_SIZE", size)
        theme = _gsettings_value(schema, "cursor-theme")
        if theme:
            os.environ.setdefault("XCURSOR_THEME", theme)
        return


def exiftool_is_ready() -> bool:
    """
    Check for ExifTool before the main window opens.

    Without ExifTool every photo would fail to load with a low-level
    "file not found" error, so show one clear message instead.
    """
    if ExifToolWrapper().is_available():
        return True

    QMessageBox.critical(None, "ExifTool Not Found", MISSING_EXIFTOOL_MESSAGE)
    return False


def main() -> int:
    match_desktop_cursor()
    app = QApplication(sys.argv)
    app.setApplicationName("FotoFixer")
    app.setOrganizationName("FotoFixer")
    # Renamed from Photo GPS Editor in 1.9.0: bring its settings over once.
    copy_settings_from_old_name(QSettings())
    app.setStyle(QStyleFactory.create("Fusion"))
    app.setWindowIcon(QIcon(str(resource_path("assets/app_icon_128.png"))))
    error_log.install()
    # Keep the reference: it runs garbage collection for the app's lifetime.
    garbage_collector = GuiThreadGarbageCollector(app)  # noqa: F841

    if not exiftool_is_ready():
        return 1

    window = MainWindow()
    window.show()
    # Backstop for quits that skip the window's close (e.g. system logout):
    # background work must stop before Qt shuts down.
    app.aboutToQuit.connect(window.stop_background_work)
    # Once a day, a few seconds in: is there a newer release on GitHub?
    window.start_update_check_later()

    exit_code = app.exec()
    # If the window closed to install an update, start the installer now
    # that nothing of ours is running (it reopens the app when done).
    window.launch_pending_update()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
