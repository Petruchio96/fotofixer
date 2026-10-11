"""
Progress row shown under the thumbnail grid while photos load.

Why this file exists:
    Loading many photos, especially from a network share, takes a few
    seconds. This row tells the user what is happening and how far along it is.

How it avoids flashing on quick loads:
    - It only appears if loading is still going after SHOW_DELAY_MS.
    - Once visible, it stays at least MIN_VISIBLE_MS, then fades out over
      FADE_MS, so it never blinks on and straight back off.

It shares a spot with the status text under the grid (a QStackedWidget). The
window hides that spot when there is neither a message nor loading to show.
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QElapsedTimer,
    QPropertyAnimation,
    QTimer,
    Signal,
)
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

# Delays are in milliseconds. Tune these after trying real loads.
SHOW_DELAY_MS = 500
MIN_VISIBLE_MS = 500
FADE_MS = 200


class LoadingIndicator(QStackedWidget):
    """
    Swaps between the normal hint text and a progress row.

    Usage:
        begin("Loading thumbnails…", total=83)   # starts the show timer
        set_progress(45, 83)
        finish()                                  # hides (after the minimums)
    """

    cancel_requested = Signal()
    # Emitted when the progress row appears or goes away.
    showing_changed = Signal()

    def __init__(self, hint_label: QLabel) -> None:
        super().__init__()
        self.hint_label = hint_label
        self.addWidget(hint_label)

        self.progress_row = QWidget()
        self.progress_row.setObjectName("loadingRow")
        row_layout = QHBoxLayout(self.progress_row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(12)

        text_and_bar = QVBoxLayout()
        text_and_bar.setSpacing(4)
        self.status_label = QLabel()
        self.status_label.setObjectName("loadingText")
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("loadingBar")
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        text_and_bar.addWidget(self.status_label)
        text_and_bar.addWidget(self.progress_bar)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("loadingCancel")
        self.cancel_button.setToolTip("Stop loading the photos")
        self.cancel_button.clicked.connect(self.cancel_requested)

        row_layout.addLayout(text_and_bar, 1)
        row_layout.addWidget(self.cancel_button)
        self.addWidget(self.progress_row)

        # Fade-out support.
        self._opacity = QGraphicsOpacityEffect(self.progress_row)
        self._opacity.setOpacity(1.0)
        self.progress_row.setGraphicsEffect(self._opacity)
        self._fade = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade.setDuration(FADE_MS)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)
        self._fade.finished.connect(self._fade_finished)

        self._show_timer = QTimer(self)
        self._show_timer.setSingleShot(True)
        self._show_timer.timeout.connect(self._show_now)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._start_fade)

        self._visible_clock = QElapsedTimer()
        self._active = False
        self._showing = False

    @property
    def is_showing(self) -> bool:
        """True while the progress row (not the hint) is on screen."""
        return self._showing

    def begin(self, text: str, total: int | None = None, *, cancellable: bool = True) -> None:
        """
        Start (or continue) a loading phase.

        Args:
            text:
                What is happening, for example "Reading GPS data…".
            total:
                Number of steps, or None for a bar that just keeps moving.
            cancellable:
                Show the Cancel button (not while writing to the photos: a
                change stopped halfway would be hard to undo).
        """
        self.cancel_button.setVisible(cancellable)
        self._active = True
        self._hide_timer.stop()
        self._set_text_and_range(text, total)

        if self._showing:
            # Already visible (e.g. moving from GPS to thumbnails): cancel any
            # fade in progress and carry on.
            self._fade.stop()
            self._opacity.setOpacity(1.0)
        elif not self._show_timer.isActive():
            self._show_timer.start(SHOW_DELAY_MS)

    def set_progress(self, done: int, total: int, text: str | None = None) -> None:
        if text is not None:
            self.status_label.setText(text)
        self.progress_bar.setRange(0, max(total, 1))
        self.progress_bar.setValue(done)

    def finish(self) -> None:
        """
        Loading is done. Hide now if never shown, or after the minimum time.
        """
        self._active = False
        self._show_timer.stop()
        if not self._showing:
            return

        remaining = max(0, MIN_VISIBLE_MS - self._visible_clock.elapsed())
        self._hide_timer.start(remaining)

    def _set_text_and_range(self, text: str, total: int | None) -> None:
        self.status_label.setText(text)
        if total is None:
            # A (0, 0) range makes Qt show a "busy" animation.
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, max(total, 1))
            self.progress_bar.setValue(0)

    def _show_now(self) -> None:
        if not self._active:
            return
        self._fade.stop()
        self._opacity.setOpacity(1.0)
        self.setCurrentWidget(self.progress_row)
        self._showing = True
        self._visible_clock.start()
        self.showing_changed.emit()

    def _start_fade(self) -> None:
        if self._active:
            return
        self._fade.stop()
        self._fade.setStartValue(self._opacity.opacity())
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _fade_finished(self) -> None:
        if self._active:
            # A new load started during the fade; stay visible.
            self._opacity.setOpacity(1.0)
            return
        self.setCurrentWidget(self.hint_label)
        self._opacity.setOpacity(1.0)
        self._showing = False
        self.showing_changed.emit()
