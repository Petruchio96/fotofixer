"""
Record errors and crashes to a log file.

Why this file exists:
    The Windows and macOS builds have no console, so an error that would
    print a message on Linux leaves no trace there, and a hard crash just
    closes the window. This writes every unexpected error, and the Python
    call stack of any hard crash, to a log file the user can send in.

    Unexpected errors in the app's own code also get a pop-up saying where
    the log is; the app keeps running.
"""

from __future__ import annotations

import datetime
import faulthandler
import os
import sys
import threading
import traceback
from pathlib import Path

from PySide6.QtCore import QtMsgType, QStandardPaths, Qt, QTimer, qInstallMessageHandler
from PySide6.QtWidgets import QApplication, QMessageBox

LOG_NAME = "error-log.txt"

# Kept open for the app's lifetime: faulthandler writes to it during a crash,
# when there is no chance to open a file.
_log_file = None
_showing_message = False
# The error message box open right now (see _show_message).
_open_message = None


def log_path() -> Path:
    folder = QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)
    return Path(folder or Path.home()) / LOG_NAME


def _write(text: str) -> None:
    if _log_file is None:
        return
    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    _log_file.write(f"\n=== {stamp} ===\n{text}\n")
    _log_file.flush()


def log(text: str) -> None:
    """
    Note something in the log without a pop-up: things worth a trace when
    looking into a problem, like a failed update check.
    """
    _write(text)


def _show_message(summary: str) -> None:
    """
    Tell the user, without blocking: QMessageBox.warning() would run a
    second event loop right where the error happened (background results
    arriving inside such a loop crashed the Windows build). One at a time.
    """
    global _showing_message, _open_message
    if _showing_message or QApplication.instance() is None:
        return
    _showing_message = True
    dialog = QMessageBox(QMessageBox.Warning, "Something Went Wrong", (
        f"{summary}\n\nThe details were saved to:\n{log_path()}\n\n"
        "Photo GPS Editor will keep running, but please send that file "
        "with a description of what you were doing."
    ), QMessageBox.Ok)

    def closed(_result: int) -> None:
        global _showing_message, _open_message
        _showing_message = False
        _open_message = None

    dialog.finished.connect(closed)
    # Kept until it closes, so Python doesn't delete it while it's open.
    _open_message = dialog
    dialog.setWindowModality(Qt.ApplicationModal)
    dialog.show()


def _handle_exception(exc_type, exc_value, exc_traceback) -> None:
    details = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    _write(details)
    if sys.__stderr__ is not None:
        sys.__stderr__.write(details)
    summary = f"{exc_type.__name__}: {exc_value}"
    if threading.current_thread() is threading.main_thread():
        _show_message(summary)
    else:
        # Pop-ups belong on the GUI thread.
        QTimer.singleShot(0, lambda: _show_message(summary))


def _handle_thread_exception(args) -> None:
    _handle_exception(args.exc_type, args.exc_value, args.exc_traceback)


_QT_MESSAGE_LABELS = {
    QtMsgType.QtWarningMsg: "Qt warning",
    QtMsgType.QtCriticalMsg: "Qt critical",
    QtMsgType.QtFatalMsg: "Qt fatal",
}


def _handle_qt_message(message_type, context, message: str) -> None:
    """
    Qt's own warnings and errors. A Qt abort ("fatal") says why here, just
    before the crash itself is logged.
    """
    label = _QT_MESSAGE_LABELS.get(message_type)
    if label is not None:
        _write(f"{label}: {message}")
    if sys.__stderr__ is not None:
        sys.__stderr__.write(f"{message}\n")


def install() -> Path | None:
    """
    Start logging. Call once, after the QApplication exists (the log folder
    depends on the application name). Returns the log file's path, or None if
    it couldn't be opened (the app then runs without a log).
    """
    global _log_file
    path = log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _log_file = open(path, "a", encoding="utf-8", errors="replace")
    except OSError:
        return None

    # Crash reports carry no time of their own, so note when the app started.
    _write("Photo GPS Editor started")
    # Hard crashes: the Python call stack of every thread.
    faulthandler.enable(file=_log_file, all_threads=True)
    qInstallMessageHandler(_handle_qt_message)
    sys.excepthook = _handle_exception
    threading.excepthook = _handle_thread_exception
    # Windowed builds have no console; send stray output to the log.
    if sys.stderr is None:
        sys.stderr = _log_file
        # Also the low-level error output, where Python and the C runtime
        # write the reason for an abort ("Fatal Python error: ...") just
        # before it happens. Without a console that text is otherwise lost.
        try:
            os.dup2(_log_file.fileno(), 2)
        except OSError:
            pass
    if sys.stdout is None:
        sys.stdout = _log_file
    return path
