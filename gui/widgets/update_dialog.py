"""
Help > Check for Updates, and the banner's What's New: one small window
that shows the check's result, the release notes, and the download's
progress. Shown with show() (never exec(): see MainWindow.show_message).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.updates import ReleaseInfo, UpdateMode, format_version
from gui.window_frame import apply_window_border

NOTES_MAX_HEIGHT = 320


def _megabytes(byte_count: int) -> str:
    return f"{byte_count / 1_000_000:.0f}"


class UpdateDialog(QDialog):
    """
    States, one method each: checking, up to date, a release (with its
    notes and the action button), downloading (progress and Cancel), or
    an error. The main window drives it and reacts to its signals.
    """

    action_requested = Signal()
    skip_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Check for Updates")
        self.setFixedWidth(560)
        self.release: ReleaseInfo | None = None

        self.headline = QLabel()
        self.headline.setObjectName("updateHeadline")
        self.headline.setWordWrap(True)

        self.note_label = QLabel()
        self.note_label.setObjectName("settingsHelp")
        self.note_label.setWordWrap(True)
        self.note_label.hide()

        # The release notes: Markdown from GitHub, scrollable when long.
        self.notes_label = QLabel()
        self.notes_label.setObjectName("updateNotes")
        self.notes_label.setWordWrap(True)
        self.notes_label.setTextFormat(Qt.TextFormat.MarkdownText)
        self.notes_label.setOpenExternalLinks(True)
        self.notes_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.notes_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.notes_area = QScrollArea()
        self.notes_area.setObjectName("updateNotesArea")
        self.notes_area.setWidgetResizable(True)
        self.notes_area.setWidget(self.notes_label)
        self.notes_area.setMaximumHeight(NOTES_MAX_HEIGHT)
        self.notes_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.notes_area.hide()

        self.progress_label = QLabel()
        self.progress_label.setObjectName("settingsHelp")
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("loadingBar")
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.progress_label.hide()
        self.progress_bar.hide()

        self.error_label = QLabel()
        self.error_label.setObjectName("updateError")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        self.skip_button = QPushButton("Skip This Version")
        self.skip_button.setProperty("tone", "neutral")
        self.skip_button.clicked.connect(self.skip_requested)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setProperty("tone", "danger")
        self.cancel_button.setToolTip("Stop the download")
        self.cancel_button.clicked.connect(self.cancel_requested)
        self.close_button = QPushButton("Close")
        self.close_button.setProperty("tone", "neutral")
        self.close_button.setToolTip("Close this window")
        self.close_button.clicked.connect(self.reject)
        self.action_button = QPushButton("Update")
        self.action_button.setObjectName("accentButton")
        self.action_button.clicked.connect(self.action_requested)
        buttons = QHBoxLayout()
        buttons.addWidget(self.skip_button)
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.close_button)
        buttons.addWidget(self.action_button)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addWidget(self.headline)
        layout.addWidget(self.notes_area)
        layout.addWidget(self.note_label)
        layout.addWidget(self.progress_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.error_label)
        layout.addLayout(buttons)
        self.show_checking()

    # --- states ---

    def _reset(self) -> None:
        for widget in (self.notes_area, self.note_label, self.progress_label, self.progress_bar, self.error_label):
            widget.hide()
        self.skip_button.hide()
        self.cancel_button.hide()
        self.action_button.hide()
        self.close_button.show()
        self.close_button.setEnabled(True)

    def show_checking(self) -> None:
        self._reset()
        self.release = None
        self.headline.setText("Checking for updates…")
        self.adjustSize()

    def show_up_to_date(self, current: str) -> None:
        self._reset()
        self.release = None
        self.headline.setText(f"You're up to date (version {current}).")
        self.adjustSize()

    def show_release(
        self,
        release: ReleaseInfo,
        current: str,
        mode: UpdateMode,
        action_label: str,
        action_hint: str,
        note: str = "",
    ) -> None:
        """A newer version: its notes and what can be done about it."""
        self._reset()
        self.release = release
        version = format_version(release.version)
        self.headline.setText(f"<b>Version {version} is available</b> (you have {current}).")
        self.notes_label.setText(release.notes or "No release notes.")
        self.notes_area.show()
        if mode == UpdateMode.NOTICE:
            note = "Pull the latest code to update."
        if note:
            self.note_label.setText(note)
            self.note_label.show()
        if mode != UpdateMode.NOTICE:
            self.skip_button.setToolTip(f"Don't mention version {version} again (a newer one will still show)")
            self.skip_button.show()
            self.action_button.setText(action_label)
            self.action_button.setToolTip(action_hint)
            self.action_button.setEnabled(True)
            self.action_button.show()
        self.adjustSize()

    def show_progress(self, received: int, total: int) -> None:
        """Downloading: the bar fills, Cancel is the only way out."""
        if not self.progress_bar.isVisible():
            self.notes_area.hide()
            self.note_label.hide()
            self.error_label.hide()
            self.skip_button.hide()
            self.action_button.hide()
            self.close_button.hide()
            self.cancel_button.show()
            self.progress_label.show()
            self.progress_bar.show()
        if total > 0:
            self.progress_bar.setRange(0, 1000)
            self.progress_bar.setValue(int(1000 * received / total))
            self.progress_label.setText(f"Downloading… {_megabytes(received)} of {_megabytes(total)} MB")
        else:
            # No size known yet: a busy bar.
            self.progress_bar.setRange(0, 0)
            self.progress_label.setText(f"Downloading… {_megabytes(received)} MB")
        self.adjustSize()

    def show_verifying(self) -> None:
        self.progress_label.setText("Checking the download…")
        self.cancel_button.setEnabled(False)

    def show_closing(self) -> None:
        self.progress_label.setText("Installing… the app will close and reopen.")
        self.cancel_button.hide()

    def show_error(self, text: str) -> None:
        """Something went wrong; the release (if known) can be tried again."""
        self.progress_label.hide()
        self.progress_bar.hide()
        self.cancel_button.hide()
        self.cancel_button.setEnabled(True)
        self.close_button.show()
        self.error_label.setText(text)
        self.error_label.show()
        if self.release is not None:
            self.notes_area.show()
            self.skip_button.show()
            self.action_button.setEnabled(True)
            self.action_button.show()
        self.adjustSize()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # A clearer edge on Windows 11 (see gui/window_frame.py).
        apply_window_border(self)
