"""
Edit > Settings: the app's options in one window.

Laid out like the settings panes of macOS, Windows, and VS Code: no group
boxes, just rows. Each row is its control (a checkbox or the Imperial /
Metric segment) with a bold one-line title beside it and a short grey
description under the title; hairlines separate the rows, and small
uppercase captions (GENERAL, MAP) group them. The rows pack at the top, so
nothing stretches when the window is taller than its contents.

    - Keep backup copies: an untouched copy of each photo before its GPS
      is first changed.
    - Units: altitudes and distances from a GPS track in feet or metres.
    - Updates: whether the app asks GitHub for a newer version when it opens.
    - Esri satellite imagery: the user's own ArcGIS API key. With a key, the
      map's Satellite button shows Esri's worldwide imagery; without one it
      is US Satellite (USGS). An open-source app can't keep a key of its
      own secret, so the key comes from the user's free ArcGIS account; the
      steps to get one are folded behind "How to get a key".

Nothing changes until Save; the main window applies and saves the values.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from gui.window_frame import apply_window_border

SIGN_UP_URL = "https://location.arcgis.com/sign-up/"
CREATE_KEY_URL = (
    "https://developers.arcgis.com/documentation/security-and-authentication/"
    "api-key-authentication/tutorials/create-an-api-key/"
)

# The rows' descriptions (short) and hover hints (fuller).
BACKUPS_HELP = (
    "Before a photo's GPS is first changed, a copy named IMG_0995_original.jpg is "
    "saved next to it. Photos without GPS aren't copied."
)
BACKUPS_HINT = (
    "Before a photo's GPS is first changed, save an untouched copy next to it "
    'as "<name>_original". Photos without GPS aren\'t copied; backups stay out of the list.'
)
UNITS_HELP = "Altitudes and distances from a GPS track."
UNITS_HINT = (
    "Show altitudes and distances from a GPS track (File > Geotag from GPS Track) in {unit}. "
    "Photos always store altitude in metres."
)
UPDATES_HELP = "Asks GitHub once a day. Help > Check for Updates always checks."
UPDATES_HINT = (
    "Shortly after the app opens, at most once a day, it asks GitHub for a newer "
    "version and shows a notice if there is one. Help > Check for Updates always checks."
)

# The Esri row: the description, and the steps behind "How to get a key".
ESRI_INTRO_HTML = (
    "With a free ArcGIS key, the map's <b>Satellite</b> button shows Esri's imagery of "
    "the whole world, down to street level. Without one it shows <b>US Satellite</b> "
    "(USGS aerial photos, United States only)."
)
# Numbered lines, not an <ol>: Qt measures lists too short and cuts off
# the last step.
ESRI_STEPS_HTML = (
    f'1. <a href="{SIGN_UP_URL}">Sign up for ArcGIS Location Platform</a> (free).<br>'
    "2. In <i>Developer credentials</i>, create <i>API key credentials</i> for a "
    "<i>Public application</i>.<br>"
    "3. Under <i>Privileges</i>, open <i>Location services &gt; Basemaps</i> and turn "
    "on only <i>Static basemap tiles</i>. Choose <i>No item access</i>.<br>"
    "4. Create it, generate the key, and paste it above. "
    f'(<a href="{CREATE_KEY_URL}">Esri\'s instructions</a>)'
)
ESRI_NOTE = (
    "The key is saved on this computer only. Esri's free plan includes a monthly "
    "allowance of map tiles (your ArcGIS dashboard shows how much you've used), and "
    "keys expire within a year: make a new one when yours does."
)

# How wide the texts in a row may be (the window's fixed width, less the
# window's margins, the card's padding, and a control beside the text).
DIALOG_WIDTH = 600
ROW_SIDE_PADDING = 16
TEXT_WIDTH = DIALOG_WIDTH - 2 * 12 - 2 * ROW_SIDE_PADDING
CONTROL_GAP = 12


class SettingsDialog(QDialog):
    """
    The Settings window. After Save, keep_backups(), esri_key(),
    check_updates(), and use_feet() hold the chosen values (esri_key() is
    "" for no key).
    """

    def __init__(
        self, parent: QWidget, *, keep_backups: bool, esri_key: str, check_updates: bool = True, use_feet: bool = True
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        # The values the window opened with: Save is off until one changes.
        self._initial = (keep_backups, esri_key.strip(), check_updates, use_feet)
        self._wrapped: list[tuple[QLabel, int]] = []

        # --- GENERAL ---
        self.keep_backups_check = QCheckBox("Keep backup copies of originals")
        self.keep_backups_check.setObjectName("settingTitleCheck")
        self.keep_backups_check.setChecked(keep_backups)
        self.keep_backups_check.toggled.connect(self._update_buttons)
        self.keep_backups_check.setToolTip(BACKUPS_HINT)
        backups_row = self._check_row(self.keep_backups_check, BACKUPS_HELP)

        # Imperial / Metric: a two-button segment like the Photo List's Show
        # filter (orange = chosen). Kept as feet_radio / metres_radio.
        self.feet_radio = QPushButton("Imperial")
        self.metres_radio = QPushButton("Metric")
        self.feet_radio.setToolTip(UNITS_HINT.format(unit="feet"))
        self.metres_radio.setToolTip(UNITS_HINT.format(unit="metres"))
        self.units_group = QButtonGroup(self)
        self.units_group.setExclusive(True)
        for button, segment in ((self.feet_radio, "first"), (self.metres_radio, "last")):
            button.setObjectName("filterButton")
            button.setProperty("segment", segment)
            button.setProperty("accent", "true")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            self.units_group.addButton(button)
        (self.feet_radio if use_feet else self.metres_radio).setChecked(True)
        self.feet_radio.toggled.connect(self._update_buttons)
        segment = QWidget()
        segment_layout = QHBoxLayout(segment)
        segment_layout.setContentsMargins(0, 0, 0, 0)
        segment_layout.setSpacing(0)
        segment_layout.addWidget(self.feet_radio)
        segment_layout.addWidget(self.metres_radio)
        units_row = self._control_row(segment, "Units", UNITS_HELP)

        self.check_updates_check = QCheckBox("Check for updates when the app starts")
        self.check_updates_check.setObjectName("settingTitleCheck")
        self.check_updates_check.setChecked(check_updates)
        self.check_updates_check.toggled.connect(self._update_buttons)
        self.check_updates_check.setToolTip(UPDATES_HINT)
        updates_row = self._check_row(self.check_updates_check, UPDATES_HELP)

        general_card = self._card([backups_row, units_row, updates_row])

        # --- MAP ---
        esri_title = QLabel("Esri satellite imagery")
        esri_title.setObjectName("settingTitle")
        esri_intro = self._description(ESRI_INTRO_HTML, rich=True, width=TEXT_WIDTH)

        self.esri_key_input = QLineEdit(esri_key)
        self.esri_key_input.setPlaceholderText("Paste your ArcGIS API key")
        self.esri_key_input.setToolTip("Your ArcGIS API key; the map's Satellite button uses it")
        self.esri_key_input.textChanged.connect(self._update_buttons)
        self.paste_key_button = QPushButton("Paste")
        self.paste_key_button.setProperty("tone", "neutral")
        self.paste_key_button.setToolTip("Paste the key from the clipboard")
        self.paste_key_button.clicked.connect(
            lambda: self.esri_key_input.setText(QApplication.clipboard().text().strip())
        )
        self.remove_key_button = QPushButton("Remove Key")
        self.remove_key_button.setProperty("tone", "danger")
        self.remove_key_button.setToolTip("Empty the key field; after Save the map uses US Satellite")
        self.remove_key_button.clicked.connect(self.esri_key_input.clear)
        key_row = QHBoxLayout()
        key_row.setSpacing(8)
        key_row.addWidget(self.esri_key_input, 1)
        key_row.addWidget(self.paste_key_button)
        key_row.addWidget(self.remove_key_button)

        # "How to get a key": the steps, folded up until wanted.
        self.help_toggle = QToolButton()
        self.help_toggle.setObjectName("settingsExpander")
        self.help_toggle.setText("How to get a key")
        self.help_toggle.setToolTip("Show or hide the steps to get a free ArcGIS key")
        self.help_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.help_toggle.setArrowType(Qt.RightArrow)
        self.help_toggle.setCheckable(True)
        self.help_toggle.setCursor(Qt.PointingHandCursor)
        self.help_toggle.toggled.connect(self._toggle_help)
        self.esri_help = QWidget()
        help_layout = QVBoxLayout(self.esri_help)
        help_layout.setContentsMargins(18, 0, 0, 0)
        help_layout.setSpacing(6)
        help_layout.addWidget(self._description(ESRI_STEPS_HTML, rich=True, width=TEXT_WIDTH - 18))
        help_layout.addWidget(self._description(ESRI_NOTE, width=TEXT_WIDTH - 18))
        self.esri_help.hide()

        esri_row = QWidget()
        esri_layout = QVBoxLayout(esri_row)
        esri_layout.setContentsMargins(ROW_SIDE_PADDING, 12, ROW_SIDE_PADDING, 12)
        esri_layout.setSpacing(8)
        esri_layout.addWidget(esri_title)
        esri_layout.addWidget(esri_intro)
        esri_layout.addLayout(key_row)
        esri_layout.addWidget(self.help_toggle, 0, Qt.AlignLeft)
        esri_layout.addWidget(self.esri_help)
        map_card = self._card([esri_row])

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
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)
        # The window is always exactly as tall as its contents.
        layout.setSizeConstraint(QLayout.SetFixedSize)
        layout.addWidget(self._caption("GENERAL"))
        layout.addWidget(general_card)
        layout.addSpacing(10)
        layout.addWidget(self._caption("MAP"))
        layout.addWidget(map_card)
        # Spare height goes here, never into the rows.
        layout.addStretch(1)
        layout.addSpacing(6)
        layout.addLayout(buttons)
        self._update_buttons()
        # A word-wrapped label's size hint ignores the width it will get,
        # so each gets exactly its height at its width (the window's width
        # is fixed) before the window sizes itself to its contents.
        for label, width in self._wrapped:
            label.setFixedHeight(label.heightForWidth(width))
        self.adjustSize()

    # --- Building blocks --------------------------------------------------------

    @staticmethod
    def _caption(text: str) -> QLabel:
        caption = QLabel(text)
        caption.setObjectName("settingsCaption")
        return caption

    @staticmethod
    def _card(rows: list[QWidget]) -> QFrame:
        """A white box holding rows with hairlines between them."""
        card = QFrame()
        card.setObjectName("settingsCard")
        card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        # The window sizes itself to its contents, so the cards set its width.
        card.setMinimumWidth(DIALOG_WIDTH - 24)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        for index, row in enumerate(rows):
            if index:
                rule = QFrame()
                rule.setObjectName("settingsRule")
                rule.setFixedHeight(1)
                layout.addWidget(rule)
            layout.addWidget(row)
        return card

    def _description(self, text: str, *, rich: bool = False, width: int) -> QLabel:
        label = QLabel(text)
        label.setObjectName("settingDescription")
        label.setWordWrap(True)
        if rich:
            label.setTextFormat(Qt.RichText)
            label.setOpenExternalLinks(True)
            label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self._wrapped.append((label, width))
        return label

    def _check_row(self, check: QCheckBox, description: str) -> QWidget:
        """A checkbox whose text is the title, the description under the text."""
        row = QWidget()
        layout = QVBoxLayout(row)
        layout.setContentsMargins(ROW_SIDE_PADDING, 10, ROW_SIDE_PADDING, 12)
        layout.setSpacing(2)
        layout.addWidget(check)
        indent = check.style().pixelMetric(QStyle.PM_IndicatorWidth) + 8
        text = self._description(description, width=TEXT_WIDTH - indent)
        text.setContentsMargins(indent, 0, 0, 0)
        layout.addWidget(text)
        return row

    def _control_row(self, control: QWidget, title: str, description: str) -> QWidget:
        """A control on the left, the title and description beside it."""
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(ROW_SIDE_PADDING, 10, ROW_SIDE_PADDING, 12)
        layout.setSpacing(CONTROL_GAP)
        layout.addWidget(control, 0, Qt.AlignTop)
        text = QWidget()
        text_layout = QVBoxLayout(text)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        title_label = QLabel(title)
        title_label.setObjectName("settingTitle")
        text_layout.addWidget(title_label)
        text_layout.addWidget(self._description(description, width=TEXT_WIDTH - 170))
        layout.addWidget(text, 1)
        return row

    def _toggle_help(self, open_: bool) -> None:
        self.help_toggle.setArrowType(Qt.DownArrow if open_ else Qt.RightArrow)
        # The layout's fixed-size constraint grows the window for the steps
        # and shrinks it back when they fold up.
        self.esri_help.setVisible(open_)

    # --- Values -----------------------------------------------------------------

    def keep_backups(self) -> bool:
        return self.keep_backups_check.isChecked()

    def esri_key(self) -> str:
        return self.esri_key_input.text().strip()

    def check_updates(self) -> bool:
        return self.check_updates_check.isChecked()

    def use_feet(self) -> bool:
        return self.feet_radio.isChecked()

    def _update_buttons(self) -> None:
        self.remove_key_button.setEnabled(bool(self.esri_key_input.text().strip()))
        if hasattr(self, "save_button"):
            changed = (self.keep_backups(), self.esri_key(), self.check_updates(), self.use_feet()) != self._initial
            self.save_button.setEnabled(changed)
            self.save_button.setToolTip(
                "Save these settings" if changed else "Nothing has changed yet"
            )

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # A clearer edge on Windows 11 (see gui/window_frame.py).
        apply_window_border(self)
