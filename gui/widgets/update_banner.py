"""
The orange notice bar at the top of the main window when a newer version
exists. Orange because something new is on offer (see the color theme in
CLAUDE.md). It never blocks anything: the app works as usual underneath.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton

from core.updates import ReleaseInfo, UpdateMode, format_version


class UpdateBanner(QFrame):
    """
    "Version 1.8.0 is available (you have 1.7.0)" with What's New, the
    action (Update or Download), Skip This Version, and a close button.
    Hidden until set_release() is called.
    """

    whats_new_requested = Signal()
    action_requested = Signal()
    skip_requested = Signal()
    dismissed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("updateBanner")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 8, 8)
        layout.setSpacing(10)

        self.text_label = QLabel()
        self.text_label.setObjectName("updateBannerText")
        self.text_label.setWordWrap(True)
        layout.addWidget(self.text_label, 1)

        self.whats_new_button = QPushButton("What's New")
        self.whats_new_button.setObjectName("updateBannerLink")
        self.whats_new_button.clicked.connect(self.whats_new_requested)
        layout.addWidget(self.whats_new_button)

        self.action_button = QPushButton("Update")
        self.action_button.setObjectName("updateBannerAction")
        self.action_button.clicked.connect(self.action_requested)
        layout.addWidget(self.action_button)

        self.skip_button = QPushButton("Skip This Version")
        self.skip_button.setObjectName("updateBannerLink")
        self.skip_button.clicked.connect(self.skip_requested)
        layout.addWidget(self.skip_button)

        self.close_button = QPushButton("✕")
        self.close_button.setObjectName("updateBannerClose")
        self.close_button.setToolTip("Hide this until the app is next opened")
        self.close_button.clicked.connect(self.dismissed)
        layout.addWidget(self.close_button)

        self._set_hints("")
        self.hide()

    def set_release(
        self,
        release: ReleaseInfo,
        current: str,
        mode: UpdateMode,
        action_label: str,
        action_hint: str,
    ) -> None:
        """Fill the bar in for this release and show it."""
        version = format_version(release.version)
        text = f"<b>Version {version} is available</b> (you have {current})."
        if mode == UpdateMode.NOTICE:
            text += " Pull the latest code to update."
        self.text_label.setText(text)
        self._set_hints(version)
        self.action_button.setText(action_label)
        self.action_button.setToolTip(action_hint)
        self.action_button.setVisible(mode != UpdateMode.NOTICE)
        self.skip_button.setVisible(mode != UpdateMode.NOTICE)
        self.show()

    def _set_hints(self, version: str) -> None:
        label = f"version {version}" if version else "the new version"
        self.whats_new_button.setToolTip(f"Show what changed in {label}")
        self.skip_button.setToolTip(f"Don't mention {label} again (a newer one will still show)")
        self.action_button.setToolTip(f"Download and install {label}")
