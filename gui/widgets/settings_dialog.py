"""
Edit > Settings: the app's options in one window.

    - Backups: keep an untouched copy of each photo before it is first changed.
    - Esri Satellite: the user's own ArcGIS API key. With a key, the map's
      Satellite button shows Esri's worldwide imagery; without one it is
      US Satellite (USGS). Esri's imagery needs a key from the user's own
      free ArcGIS Location Platform account: an open-source app can't keep
      a key of its own secret.
    - Updates: whether the app asks GitHub for a newer version when it opens.

Nothing changes until Save; the main window applies and saves the values.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gui.window_frame import apply_window_border

SIGN_UP_URL = "https://location.arcgis.com/sign-up/"
CREATE_KEY_URL = (
    "https://developers.arcgis.com/documentation/security-and-authentication/"
    "api-key-authentication/tutorials/create-an-api-key/"
)

BACKUPS_HELP = (
    "Before a photo's GPS is first changed, save an untouched copy next to it, with "
    '"_original" added to its name: IMG_0995.jpg is copied to IMG_0995_original.jpg. '
    "Photos that had no GPS aren't copied (adding GPS loses nothing)."
)

# The Esri section's text, in three labels: one long rich-text label is
# measured too short by Qt and its last lines get cut off.
ESRI_INTRO_HTML = (
    "With a key, the map's <b>Satellite</b> button shows Esri's satellite "
    "imagery of the whole world, detailed down to street level. Without one "
    "it shows <b>US Satellite</b> (aerial photos of the United States, no key "
    "needed)."
)
# Numbered lines, not an <ol>: Qt measures lists too short and cuts off
# the last step.
ESRI_STEPS_HTML = (
    "To get a free key from your own ArcGIS account:<br>"
    f'1. <a href="{SIGN_UP_URL}">Sign up for ArcGIS Location Platform</a> (free).<br>'
    "2. In <i>Developer credentials</i>, create <i>API key credentials</i> for a "
    "<i>Public application</i>.<br>"
    "3. Under <i>Privileges</i>, open <i>Location services &gt; Basemaps</i> and turn "
    "on only <i>Static basemap tiles</i>. Choose <i>No item access</i>.<br>"
    "4. Create it, generate the key, and paste it below. "
    f'(<a href="{CREATE_KEY_URL}">Esri\'s instructions</a>)'
)
UPDATES_HELP = (
    "About five seconds after the app opens, at most once a day, it asks GitHub "
    "whether a newer version exists and shows a notice if one does. "
    "Help > Check for Updates always checks."
)

ESRI_NOTE = (
    "The key is saved in this app's settings on this computer. Esri's free plan "
    "includes a monthly allowance of map tiles; your ArcGIS dashboard shows how "
    "much you've used. Keys expire (a year at most): make a new one and paste it here."
)


class SettingsDialog(QDialog):
    """
    The Settings window. After Save, keep_backups(), esri_key(), and
    check_updates() hold the chosen values (esri_key() is "" for no key).
    """

    def __init__(
        self, parent: QWidget, *, keep_backups: bool, esri_key: str, check_updates: bool = True
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setFixedWidth(600)
        # The values the window opened with: Save is off until one changes.
        self._initial = (keep_backups, esri_key.strip(), check_updates)

        # --- Backups ---
        backups_group = QGroupBox("Backups")
        backups_layout = QVBoxLayout(backups_group)
        self.keep_backups_check = QCheckBox("Keep Backup Copies of Originals")
        self.keep_backups_check.setChecked(keep_backups)
        self.keep_backups_check.toggled.connect(self._update_buttons)
        self.keep_backups_check.setToolTip(BACKUPS_HELP)
        backups_help = QLabel(BACKUPS_HELP)
        backups_help.setObjectName("settingsHelp")
        backups_help.setWordWrap(True)
        backups_layout.addWidget(self.keep_backups_check)
        backups_layout.addWidget(backups_help)

        # --- Updates ---
        updates_group = QGroupBox("Updates")
        updates_layout = QVBoxLayout(updates_group)
        self.check_updates_check = QCheckBox("Check for updates when the app starts")
        self.check_updates_check.setChecked(check_updates)
        self.check_updates_check.toggled.connect(self._update_buttons)
        self.check_updates_check.setToolTip(UPDATES_HELP)
        updates_help = QLabel(UPDATES_HELP)
        updates_help.setObjectName("settingsHelp")
        updates_help.setWordWrap(True)
        updates_layout.addWidget(self.check_updates_check)
        updates_layout.addWidget(updates_help)

        # --- Esri Satellite ---
        esri_group = QGroupBox("Esri Satellite Map")
        esri_layout = QVBoxLayout(esri_group)
        esri_layout.setSpacing(10)
        esri_labels = []
        for text, rich in ((ESRI_INTRO_HTML, True), (ESRI_STEPS_HTML, True), (ESRI_NOTE, False)):
            label = QLabel(text)
            label.setObjectName("settingsHelp")
            label.setWordWrap(True)
            if rich:
                label.setTextFormat(Qt.RichText)
                label.setOpenExternalLinks(True)
                label.setTextInteractionFlags(Qt.TextBrowserInteraction)
            esri_labels.append(label)

        self.esri_key_input = QLineEdit(esri_key)
        self.esri_key_input.setPlaceholderText("Paste your ArcGIS API key")
        self.esri_key_input.textChanged.connect(self._update_buttons)
        self.paste_key_button = QPushButton("Paste")
        self.paste_key_button.setProperty("tone", "neutral")
        self.paste_key_button.setToolTip("Paste the key from the clipboard")
        self.paste_key_button.clicked.connect(
            lambda: self.esri_key_input.setText(QApplication.clipboard().text().strip())
        )
        self.remove_key_button = QPushButton("Remove Key")
        self.remove_key_button.setProperty("tone", "danger")
        self.remove_key_button.setToolTip(
            "Empty the key field; after Save the map uses US Satellite"
        )
        self.remove_key_button.clicked.connect(self.esri_key_input.clear)
        key_row = QHBoxLayout()
        key_row.addWidget(self.esri_key_input, 1)
        key_row.addWidget(self.paste_key_button)
        key_row.addWidget(self.remove_key_button)
        for label in esri_labels:
            esri_layout.addWidget(label)
        esri_layout.addLayout(key_row)

        # --- Save / Cancel ---
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setProperty("tone", "neutral")
        self.cancel_button.setToolTip("Close without changing any settings")
        self.cancel_button.clicked.connect(self.reject)
        self.save_button = QPushButton("Save")
        self.save_button.setObjectName("accentButton")
        self.save_button.setToolTip("Save these settings")
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.save_button)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addWidget(backups_group)
        layout.addWidget(updates_group)
        layout.addWidget(esri_group)
        layout.addLayout(buttons)
        self._update_buttons()
        # A fixed width lets the wrapped text work out its height, so the
        # window opens tall enough for all of it.
        self.adjustSize()

    def keep_backups(self) -> bool:
        return self.keep_backups_check.isChecked()

    def esri_key(self) -> str:
        return self.esri_key_input.text().strip()

    def check_updates(self) -> bool:
        return self.check_updates_check.isChecked()

    def _update_buttons(self) -> None:
        self.remove_key_button.setEnabled(bool(self.esri_key_input.text().strip()))
        if hasattr(self, "save_button"):
            changed = (self.keep_backups(), self.esri_key(), self.check_updates()) != self._initial
            self.save_button.setEnabled(changed)
            self.save_button.setToolTip(
                "Save these settings" if changed else "Nothing has changed yet"
            )

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # A clearer edge on Windows 11 (see gui/window_frame.py).
        apply_window_border(self)
