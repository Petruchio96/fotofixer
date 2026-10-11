"""
A clearer edge for the app's extra windows on Windows 11.

Windows 11 draws a very faint 1-pixel border around windows, so the map,
the picker, and Settings were hard to tell apart from the main window behind
them. The system lets an app pick that border's color; a soft slate keeps it
subtle but visible. Linux and macOS window managers already draw a shadow or
edge, so nothing changes there.

Windows 10, and some virtual machines, refuse the border color setting (and
often draw no shadow either), which left the map indistinguishable from the
main window. There the app draws the slate edge itself, just inside the
window (WindowEdge).
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

# DwmSetWindowAttribute's "border color" setting (Windows 11, build 22000+).
DWMWA_BORDER_COLOR = 34

# The border color: slate, the same as the app's disabled-button gray.
BORDER_RGB = (0x8F, 0xA1, 0xB4)


class WindowEdge(QWidget):
    """
    A 1-pixel slate frame drawn just inside a window's edges, for Windows
    versions that refuse the border color. It sits on top of the window's
    contents, follows its size, and lets every click through.
    """

    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self.setObjectName("windowEdge")
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setGeometry(window.rect())
        window.installEventFilter(self)
        self.raise_()
        self.show()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        # Follow the window's size, and stay above widgets added later.
        if watched is self.parentWidget() and event.type() in (QEvent.Resize, QEvent.Show):
            self.setGeometry(self.parentWidget().rect())
            self.raise_()
        return False

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        pen = QPen(QColor(*BORDER_RGB))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))


def apply_window_border(widget: QWidget) -> None:
    """
    Give a top-level window a visible slate border on Windows: the system's
    border color on Windows 11, or a WindowEdge where Windows refuses it.
    Does nothing elsewhere, and never raises: the border is a nicety.
    """
    if sys.platform != "win32":
        return
    if widget.findChild(WindowEdge, "windowEdge", Qt.FindDirectChildrenOnly) is not None:
        return
    if not _set_system_border_color(widget):
        WindowEdge(widget)


def _set_system_border_color(widget: QWidget) -> bool:
    """
    Ask Windows 11 to draw the window's border in slate. Returns whether
    Windows accepted it (Windows 10 answers with an error code).
    """
    try:
        import ctypes

        red, green, blue = BORDER_RGB
        # Windows COLORREF is 0x00BBGGRR.
        color = ctypes.c_uint(red | (green << 8) | (blue << 16))
        result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(int(widget.winId())),
            ctypes.c_uint(DWMWA_BORDER_COLOR),
            ctypes.byref(color),
            ctypes.sizeof(color),
        )
    except Exception:
        # No DWM at all.
        return False
    # An HRESULT: 0 (S_OK) means the color was set.
    return result == 0
