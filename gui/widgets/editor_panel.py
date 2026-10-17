"""
Inspector panel UI builder (the right side of the window).

The photos selected in the Photo List are the photos being edited. This pane
shows what is selected, then two tabs: Location (the new location and the two
actions, Apply and Remove GPS, which is destructive so styled to stand apart)
and Date & Time (shift the selected photos' dates, or set one date on them).
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QToolTip,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
)

from gui.presenters.date_time_state import MODE_SET, MODE_SHIFT, MODE_ZONE
from gui.widgets.browser_panel import build_pane_header
from gui.widgets.date_time_picker import ChevronComboBox, DateTimePicker
from gui.widgets.icons import ICON_SIZE, calendar_icon, clock_icon, clock_shift_icon, globe_icon, map_icon, pin_icon

if TYPE_CHECKING:
    from gui.main_window import MainWindow

# The pick button's label; it reads "Cancel" while picking.
PICK_BUTTON_TEXT = "From a Photo in the Photo List"
PICK_BUTTON_TIP = (
    "Click this, then click a photo with GPS in the Photo List to copy "
    "its location. A selected photo becomes the source and is deselected."
)

# The Date & Time pick button's label; it reads "Cancel" while picking.
PICK_TIME_BUTTON_TEXT = "From a Photo in the Photo List"
PICK_TIME_BUTTON_TIP = (
    "Click this, then click a photo in the Photo List whose time is right "
    "(e.g. from your phone), taken at the same moment as the reference photo."
)

# Tab positions in editor_tabs.
LOCATION_TAB = 0
DATE_TIME_TAB = 1


def _build_selection_summary(window: "MainWindow") -> QWidget:
    """
    Under the header: how many photos are selected, and how many of them
    have GPS.
    """
    summary = QWidget()
    layout = QHBoxLayout(summary)
    layout.setContentsMargins(22, 16, 20, 12)
    layout.setSpacing(14)

    window.selection_title_label = QLabel("No Photos Selected")
    window.selection_title_label.setObjectName("sectionTitle")
    window.selection_title_label.setWordWrap(True)

    window.selection_gps_label = QLabel()
    window.selection_gps_label.setObjectName("selectionGps")
    window.selection_gps_label.setWordWrap(True)
    window.selection_gps_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

    text = QVBoxLayout()
    text.setSpacing(2)
    text.addWidget(window.selection_title_label)
    text.addWidget(window.selection_gps_label)

    # Shown only when one photo with GPS is selected.
    window.copy_location_button = QPushButton("Copy")
    window.copy_location_button.setProperty("tone", "neutral")
    window.copy_location_button.setToolTip("Copy this photo's GPS coordinates")
    window.copy_location_button.clicked.connect(window.copy_selected_photo_gps_coordinates)

    layout.addLayout(text, 1)
    layout.addWidget(window.copy_location_button, 0, Qt.AlignVCenter)
    return summary


def _build_location_group(window: "MainWindow") -> QGroupBox:
    """
    The New Location box: where the new coordinates come from.
    Blue throughout means "where the location comes from".
    """
    location_group = QGroupBox("New Location")
    location_group.setObjectName("locationGroup")
    location_layout = QVBoxLayout(location_group)
    location_layout.setSpacing(10)

    copy_label = QLabel("Copy location")
    copy_label.setObjectName("fieldLabel")

    # Pick a photo in the grid to take its location from ("eyedropper").
    window.pick_location_button = QPushButton(PICK_BUTTON_TEXT)
    window.pick_location_button.setObjectName("pickButton")
    window.pick_location_button.setCheckable(True)
    window.pick_location_button.setToolTip(PICK_BUTTON_TIP)
    window.pick_location_button.clicked.connect(window.toggle_picking_location)

    window.location_from_photo_button = QPushButton("From a Photo on Your Computer")
    window.location_from_photo_button.setObjectName("pickButton")
    window.location_from_photo_button.setToolTip(
        "Choose any photo file on your computer and use its GPS coordinates"
    )
    window.location_from_photo_button.clicked.connect(window.choose_location_from_photo)

    copy_buttons = QHBoxLayout()
    copy_buttons.setSpacing(8)
    copy_buttons.addWidget(window.pick_location_button, 1)
    copy_buttons.addWidget(window.location_from_photo_button, 1)

    # Opens the pop-out map: click it or drag the pin to fill the fields.
    window.show_map_button = QPushButton("Pick from a Map")
    window.show_map_button.setObjectName("pickButton")
    # On Windows the icon lands flush against the text, so it gets clear
    # space on its right there (the icon size grows to match).
    map_icon_gap = 4 if sys.platform == "win32" else 0
    window.show_map_button.setIcon(map_icon("#1f5fc4", text_gap=map_icon_gap))
    window.show_map_button.setIconSize(QSize(ICON_SIZE + map_icon_gap, ICON_SIZE))
    window.show_map_button.setToolTip(
        "Open a map: click it, or drag the pin, to set the New Location. "
        "Photos in the Photo List with GPS show as dots."
    )
    window.show_map_button.clicked.connect(window.show_map)

    # Shows which photo the location came from, when it came from one.
    window.source_card = QFrame()
    window.source_card.setObjectName("sourceCard")
    source_card_layout = QHBoxLayout(window.source_card)
    source_card_layout.setContentsMargins(10, 8, 6, 8)
    source_card_layout.setSpacing(10)
    window.source_card_thumbnail = QLabel()
    window.source_card_thumbnail.setFixedSize(52, 52)
    window.source_card_thumbnail.setAlignment(Qt.AlignCenter)
    source_text = QVBoxLayout()
    source_text.setSpacing(2)
    window.source_card_title = QLabel()
    window.source_card_title.setObjectName("sourceCardTitle")
    window.source_card_detail = QLabel()
    window.source_card_detail.setObjectName("sourceCardDetail")
    source_text.addWidget(window.source_card_title)
    source_text.addWidget(window.source_card_detail)
    window.source_card_clear = QPushButton("✕")
    window.source_card_clear.setObjectName("sourceCardClear")
    window.source_card_clear.setToolTip("Clear the location")
    window.source_card_clear.setFixedSize(30, 30)
    window.source_card_clear.clicked.connect(window.clear_location_fields)
    source_card_layout.addWidget(window.source_card_thumbnail)
    source_card_layout.addLayout(source_text, 1)
    source_card_layout.addWidget(window.source_card_clear, 0, Qt.AlignTop)
    window.source_card.hide()

    fields = QFormLayout()
    fields.setSpacing(10)
    window.latitude_input = QLineEdit()
    window.longitude_input = QLineEdit()
    window.latitude_input.setPlaceholderText("e.g. 40.5865 or 40° 35' 11\" N")
    window.longitude_input.setPlaceholderText("e.g. -111.6558 or 111° 39' 21\" W")
    for field in (window.latitude_input, window.longitude_input):
        field.setToolTip(
            "Type or paste coordinates.\nA pair copied from Google Maps can be pasted into either field as is."
        )
    window.latitude_input.editingFinished.connect(window.validate_latitude_field)
    window.longitude_input.editingFinished.connect(window.validate_longitude_field)
    window.latitude_input.textChanged.connect(window._handle_location_input_change)
    window.longitude_input.textChanged.connect(window._handle_location_input_change)
    fields.addRow("Latitude:", window.latitude_input)
    fields.addRow("Longitude:", window.longitude_input)

    window.paste_coordinates_button = QPushButton("Paste")
    window.paste_coordinates_button.setProperty("tone", "neutral")
    window.paste_coordinates_button.setToolTip("Paste coordinates copied from a map or another photo")
    window.paste_coordinates_button.clicked.connect(window.paste_coordinates_from_clipboard)

    window.clear_location_button = QPushButton("Clear")
    window.clear_location_button.setProperty("tone", "neutral")
    window.clear_location_button.setToolTip("Empty the latitude and longitude fields")
    window.clear_location_button.clicked.connect(window.clear_location_fields)

    location_buttons = QHBoxLayout()
    location_buttons.setSpacing(8)
    location_buttons.addWidget(window.paste_coordinates_button, 1)
    location_buttons.addWidget(window.clear_location_button, 1)

    location_layout.addWidget(copy_label)
    location_layout.addLayout(copy_buttons)
    location_layout.addWidget(window.show_map_button)
    location_layout.addWidget(window.source_card)
    location_layout.addLayout(fields)
    location_layout.addLayout(location_buttons)
    return location_group


def _build_location_tab(window: "MainWindow") -> QWidget:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(20, 16, 20, 20)
    layout.setSpacing(10)

    window.apply_hint_label = QLabel()
    window.apply_hint_label.setObjectName("applyHint")
    window.apply_hint_label.setWordWrap(True)

    window.apply_button = QPushButton("Apply Location to Selected Photos")
    window.apply_button.setObjectName("accentButton")
    window.apply_button.setEnabled(False)
    window.apply_button.setMinimumHeight(44)
    window.apply_button.setToolTip("Write the New Location into the selected photos")
    window.apply_button.clicked.connect(window.apply_coordinates_to_selected)

    window.remove_gps_button = QPushButton("Remove GPS from Selected Photos")
    window.remove_gps_button.setObjectName("removeGpsButton")
    window.remove_gps_button.setEnabled(False)
    window.remove_gps_button.setToolTip(
        "Delete the GPS coordinates stored in the selected photos that have them. "
        "You can undo this afterwards."
    )
    window.remove_gps_button.clicked.connect(window.remove_gps_from_selected)

    layout.addWidget(_build_location_group(window))
    layout.addStretch(1)
    layout.addWidget(window.apply_hint_label)
    layout.addWidget(window.apply_button)
    layout.addWidget(window.remove_gps_button)
    return page


def _build_reference_card(window: "MainWindow") -> QFrame:
    """
    Shift: the reference photo (blue: what exists) with its current date,
    and arrows to choose another selected photo as the reference.
    """
    card = QFrame()
    card.setObjectName("sourceCard")
    layout = QHBoxLayout(card)
    layout.setContentsMargins(10, 8, 8, 8)
    layout.setSpacing(10)
    window.date_reference_thumbnail = QLabel()
    window.date_reference_thumbnail.setFixedSize(52, 52)
    window.date_reference_thumbnail.setAlignment(Qt.AlignCenter)
    text = QVBoxLayout()
    text.setSpacing(1)
    window.date_reference_title = QLabel()
    window.date_reference_title.setObjectName("sourceCardTitle")
    window.date_reference_detail = QLabel()
    window.date_reference_detail.setObjectName("sourceCardDetail")
    window.date_reference_earliest = QLabel("The earliest selected")
    window.date_reference_earliest.setObjectName("sourceCardDetail")
    for label in (window.date_reference_title, window.date_reference_detail, window.date_reference_earliest):
        text.addWidget(label)
    window.date_reference_back = QPushButton("‹")
    window.date_reference_back.setObjectName("referenceArrow")
    window.date_reference_back.setToolTip("Use the previous selected photo (by date) as the reference")
    window.date_reference_back.clicked.connect(lambda: window.step_date_reference(-1))
    window.date_reference_position = QLabel()
    window.date_reference_position.setObjectName("sourceCardDetail")
    window.date_reference_forward = QPushButton("›")
    window.date_reference_forward.setObjectName("referenceArrow")
    window.date_reference_forward.setToolTip("Use the next selected photo (by date) as the reference")
    window.date_reference_forward.clicked.connect(lambda: window.step_date_reference(1))
    for button in (window.date_reference_back, window.date_reference_forward):
        button.setFixedSize(28, 28)
    layout.addWidget(window.date_reference_thumbnail)
    layout.addLayout(text, 1)
    layout.addWidget(window.date_reference_back)
    layout.addWidget(window.date_reference_position)
    layout.addWidget(window.date_reference_forward)
    return card


def _build_time_source_card(window: "MainWindow") -> QFrame:
    """
    The photo the correct time was copied from (blue, like the Location
    tab's source card), with ✕ to stop using it.
    """
    card = QFrame()
    card.setObjectName("sourceCard")
    layout = QHBoxLayout(card)
    layout.setContentsMargins(10, 8, 6, 8)
    layout.setSpacing(10)
    window.time_source_thumbnail = QLabel()
    window.time_source_thumbnail.setFixedSize(52, 52)
    window.time_source_thumbnail.setAlignment(Qt.AlignCenter)
    text = QVBoxLayout()
    text.setSpacing(2)
    window.time_source_title = QLabel()
    window.time_source_title.setObjectName("sourceCardTitle")
    window.time_source_detail = QLabel()
    window.time_source_detail.setObjectName("sourceCardDetail")
    text.addWidget(window.time_source_title)
    text.addWidget(window.time_source_detail)
    window.time_source_clear = QPushButton("✕")
    window.time_source_clear.setObjectName("sourceCardClear")
    window.time_source_clear.setToolTip("Stop using this photo's time")
    window.time_source_clear.setFixedSize(30, 30)
    window.time_source_clear.clicked.connect(window.clear_time_source)
    layout.addWidget(window.time_source_thumbnail)
    layout.addLayout(text, 1)
    layout.addWidget(window.time_source_clear, 0, Qt.AlignTop)
    card.hide()
    return card


class StepBox(QFrame):
    """
    One numbered step of the Date & Time tab: a header (number, title, and
    on the right a summary or "After step N") and a body that shows once the
    step is reachable. set_state() switches between "active" (orange: do
    this now), "done" (navy ✓), and "locked" (grey, body hidden).
    """

    def __init__(self, number: int, title: str) -> None:
        super().__init__()
        self.number = number
        self.setObjectName("stepBox")
        self.setProperty("state", "locked")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(10)
        self.circle = QLabel(str(number))
        self.circle.setObjectName("stepCircle")
        self.circle.setAlignment(Qt.AlignCenter)
        self.circle.setFixedSize(28, 28)
        self.title = QLabel(title)
        self.title.setObjectName("stepTitle")
        self.summary = QLabel()
        self.summary.setObjectName("stepSummary")
        header.addWidget(self.circle)
        header.addWidget(self.title)
        header.addStretch(1)
        header.addWidget(self.summary)
        self.header = header
        layout.addLayout(header)

        # The step's contents, indented under the title.
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(38, 0, 0, 0)
        self.body_layout.setSpacing(10)
        layout.addWidget(self.body)

    def set_state(self, state: str, summary: str = "") -> None:
        """state: "active", "done", or "locked"."""
        self.circle.setText("✓" if state == "done" else str(self.number))
        self.body.setVisible(state != "locked")
        self.summary.setText(f"After step {self.number - 1}" if state == "locked" else summary)
        if self.property("state") != state:
            self.setProperty("state", state)
            for widget in (self, self.circle, self.title, self.summary):
                widget.style().unpolish(widget)
                widget.style().polish(widget)


# The hover hint of Change Time Zone's "Keep the clock time" checkbox.
KEEP_CLOCK_TIP = (
    "Off: the photos keep the moment they were taken; their clock times change to "
    "show that moment in the new zone (11:16 am MDT → 12:16 pm CDT).\n"
    "On: the clock times stay as they are and only the zone changes (11:16 am MDT → "
    "11:16 am CDT), which moves the moment. Use it when the times were right for "
    "where the photos were taken but the zone was set wrong."
)

# Step 2's card icons: orange, like the step to do now.
CHOICE_ICON_COLOR = "#d97706"
CHOICE_ICON_SIZE = 18


class ChoiceCard(QPushButton):
    """
    One of step 2's choices: a checkable button with an icon, a bold
    one-line title, and an explanation that wraps (labels inside pass clicks
    through to the button). A plain QPushButton ignores the layout inside it
    when sizing itself, so this one takes its size from that layout: only as
    tall as its text needs at the width it gets, and never narrower than its
    title. "Change ▾" on the right shows while step 2 is folded up to the
    chosen card (see set_folded).
    """

    def __init__(self, title: str, detail: str, tooltip: str, icon) -> None:
        super().__init__()
        self.setObjectName("choiceCard")
        self.setCheckable(True)
        self.choose_tooltip = tooltip
        self.setToolTip(tooltip)
        self.setCursor(Qt.PointingHandCursor)
        policy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

        layout = QHBoxLayout(self)
        # 12px (10px tall) inside the 2px border.
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        text = QVBoxLayout()
        text.setSpacing(3)
        title_row = QHBoxLayout()
        title_row.setSpacing(7)
        icon_label = QLabel()
        icon_label.setPixmap(icon.pixmap(CHOICE_ICON_SIZE, CHOICE_ICON_SIZE))
        icon_label.setFixedSize(CHOICE_ICON_SIZE, CHOICE_ICON_SIZE)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("choiceTitle")
        title_row.addWidget(icon_label)
        title_row.addWidget(self.title_label, 1)
        text.addLayout(title_row)
        self.detail_label = QLabel(detail)
        self.detail_label.setObjectName("choiceDetail")
        self.detail_label.setWordWrap(True)
        text.addWidget(self.detail_label)
        text.addStretch(1)
        layout.addLayout(text, 1)

        self.change_label = QLabel("Change ▾")
        self.change_label.setObjectName("choiceChange")
        self.change_label.hide()
        layout.addWidget(self.change_label, 0, Qt.AlignVCenter)
        for label in (icon_label, self.title_label, self.detail_label, self.change_label):
            label.setAttribute(Qt.WA_TransparentForMouseEvents)

    def set_folded(self, folded: bool) -> None:
        """
        Step 2 folded up to this (the chosen) card: "Change ▾" shows, and a
        click opens all the choices again.
        """
        self.change_label.setVisible(folded)
        self.setToolTip("Show all three choices, to pick another" if folded else self.choose_tooltip)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self.layout().totalHeightForWidth(width)

    def sizeHint(self) -> QSize:
        hint = self.layout().totalSizeHint()
        return QSize(hint.width(), self.heightForWidth(hint.width()))

    def minimumSizeHint(self) -> QSize:
        # The title never wraps, so it sets the narrowest the card can be.
        width = self.layout().totalMinimumSize().width()
        return QSize(width, self.heightForWidth(width))


def _build_select_step(window: "MainWindow") -> StepBox:
    """1. Select the photos to change (with Add Photos when the list is empty)."""
    step = StepBox(1, "Select the photos to change")
    window.step_add_photos_button = QPushButton("+ Add Photos")
    window.step_add_photos_button.setObjectName("stepAddButton")
    window.step_add_photos_button.setToolTip("Choose photos to add to the Photo List")
    window.step_add_photos_button.clicked.connect(window.add_photos)
    step.header.addWidget(window.step_add_photos_button)
    window.step_select_hint = QLabel()
    window.step_select_hint.setObjectName("stepHint")
    window.step_select_hint.setWordWrap(True)
    step.body_layout.addWidget(window.step_select_hint)
    return step


def _build_mode_step(window: "MainWindow") -> StepBox:
    """
    2. Choose how to change Date & Time: Shift, Set, or Change Time Zone
    (nothing chosen at first). Three stacked cards; once one is chosen the
    step folds up to it (see DateTimeEditorMixin._apply_date_steps).
    """
    step = StepBox(2, "Choose how to change Date & Time")
    window.date_shift_choice = ChoiceCard(
        "Shift Date and Time",
        "The time was off. Correct one photo; the rest move by the same amount.",
        "Move every selected photo by the same amount, keeping the time between them",
        clock_shift_icon(CHOICE_ICON_COLOR),
    )
    window.date_set_choice = ChoiceCard(
        "Set One Date and Time",
        "Every selected photo gets the same date and time.",
        "Give every selected photo one date and time",
        calendar_icon(CHOICE_ICON_COLOR),
    )
    window.date_zone_choice = ChoiceCard(
        "Change Time Zone",
        "Correct photos with the wrong time zone.",
        "Give the selected photos another time zone (the same moment, or the same clock time)",
        globe_icon(CHOICE_ICON_COLOR),
    )
    window.date_shift_choice.clicked.connect(lambda: window.choose_date_change_mode(MODE_SHIFT))
    window.date_set_choice.clicked.connect(lambda: window.choose_date_change_mode(MODE_SET))
    window.date_zone_choice.clicked.connect(lambda: window.choose_date_change_mode(MODE_ZONE))
    window.date_choice_cards = {
        MODE_SHIFT: window.date_shift_choice,
        MODE_SET: window.date_set_choice,
        MODE_ZONE: window.date_zone_choice,
    }
    # The cards use the step's full width (not indented under the title),
    # leaving room for the larger titles.
    step.body_layout.setContentsMargins(0, 0, 0, 0)
    step.body_layout.setSpacing(8)
    for card in window.date_choice_cards.values():
        step.body_layout.addWidget(card)
    return step


def _build_correct_step(window: "MainWindow") -> StepBox:
    """
    3. Correct the date and time (Shift: the reference photo, its correct
    date, time and zone, or copy the time from a photo), enter it (Set), or
    choose the new time zone (Change Time Zone).
    """
    step = StepBox(3, "Correct the date and time")

    # Shift: reference photo, its correct date and time, copy from a photo.
    window.date_shift_box = QWidget()
    shift_layout = QVBoxLayout(window.date_shift_box)
    shift_layout.setContentsMargins(0, 0, 0, 0)
    shift_layout.setSpacing(8)
    corrected_label = QLabel("Correct date and time for this photo")
    corrected_label.setObjectName("fieldLabel")
    window.date_reference_picker = DateTimePicker(what="correct date and time for the reference photo")
    window.date_reference_picker.changed.connect(window.date_reference_edited)
    window.date_reference_picker.zone_chosen.connect(window.date_zone_chosen)
    copy_label = QLabel("Or copy the time from a photo taken at the same moment")
    copy_label.setObjectName("fieldLabel")
    window.pick_time_button = QPushButton(PICK_TIME_BUTTON_TEXT)
    window.pick_time_button.setObjectName("pickButton")
    window.pick_time_button.setCheckable(True)
    window.pick_time_button.setToolTip(PICK_TIME_BUTTON_TIP)
    window.pick_time_button.clicked.connect(window.toggle_picking_time)
    window.time_from_photo_button = QPushButton("From a Photo on Your Computer")
    window.time_from_photo_button.setObjectName("pickButton")
    window.time_from_photo_button.setToolTip(
        "Choose a photo on your computer whose time is right, taken at the same "
        "moment as the reference photo"
    )
    window.time_from_photo_button.clicked.connect(window.choose_time_from_photo)
    copy_buttons = QHBoxLayout()
    copy_buttons.setSpacing(8)
    copy_buttons.addWidget(window.pick_time_button, 1)
    copy_buttons.addWidget(window.time_from_photo_button, 1)
    shift_layout.addWidget(_build_reference_card(window))
    shift_layout.addWidget(corrected_label)
    shift_layout.addWidget(window.date_reference_picker)
    shift_layout.addWidget(copy_label)
    shift_layout.addLayout(copy_buttons)
    window.time_source_card = _build_time_source_card(window)
    shift_layout.addWidget(window.time_source_card)

    # Set: one date and time for every selected photo.
    window.date_set_box = QWidget()
    set_layout = QVBoxLayout(window.date_set_box)
    set_layout.setContentsMargins(0, 0, 0, 0)
    set_layout.setSpacing(8)
    window.date_set_picker = DateTimePicker(what="date and time to give every selected photo")
    window.date_set_picker.changed.connect(window.date_set_value_edited)
    window.date_set_picker.zone_chosen.connect(window.date_zone_chosen)
    set_layout.addWidget(window.date_set_picker)
    window.date_set_box.hide()

    # Change Time Zone: the new zone, and whether the clock times stay.
    window.date_zone_box = QWidget()
    zone_layout = QVBoxLayout(window.date_zone_box)
    zone_layout.setContentsMargins(0, 0, 0, 0)
    zone_layout.setSpacing(8)
    zone_label = QLabel("New time zone")
    zone_label.setObjectName("fieldLabel")
    window.date_zone_combo = ChevronComboBox()
    window.date_zone_combo.setObjectName("timeZoneCombo")
    window.date_zone_combo.setMaxVisibleItems(16)
    window.date_zone_combo.setProperty("mixed", False)
    window.date_zone_combo.activated.connect(
        lambda index: window.date_zone_chosen(window.date_zone_combo.itemData(index))
    )
    window.date_keep_clock_check = QCheckBox("Keep the clock time (change only the time zone)")
    window.date_keep_clock_check.setObjectName("keepClockCheck")
    window.date_keep_clock_check.setToolTip(KEEP_CLOCK_TIP)
    window.date_keep_clock_check.clicked.connect(window.keep_clock_clicked)
    keep_clock_note = QLabel("Apply the current time to the selected time zone.")
    keep_clock_note.setObjectName("keepClockNote")
    keep_clock_note.setToolTip(KEEP_CLOCK_TIP)
    zone_layout.addWidget(zone_label)
    zone_layout.addWidget(window.date_zone_combo)
    zone_layout.addWidget(window.date_keep_clock_check)
    zone_layout.addWidget(keep_clock_note)
    window.date_zone_box.hide()

    step.body_layout.addWidget(window.date_shift_box)
    step.body_layout.addWidget(window.date_set_box)
    step.body_layout.addWidget(window.date_zone_box)
    return step


# Item data role on the changes list's rows: (name, original date, new date).
CHANGE_ROW_ROLE = Qt.UserRole + 1


class DateChangesList(QTreeWidget):
    """
    Step 4's list of changes (name, original date, → new date). The window
    is often too narrow for a whole row, so a column may end in "…"; then
    hovering the row shows it in full: the name, the original date and
    time, and the new one. Rows that fit show no hover hint.
    """

    # Narrowest the name and current-date columns get when room is short.
    MIN_NAME_WIDTH = 80
    MIN_CURRENT_WIDTH = 60

    def fit_columns(self) -> None:
        """
        Size the columns to fit the list's width: the new date in full when
        it fits, the name in full, and the current date the room left. When
        the list is too narrow the current date gives way first, then the
        name, then the new date, so all three always stay in view (each cut
        short with "…"; the row's hover hint shows it in full). Header
        ResizeToContents can't do this: it let a long new date such as
        "… MDT (time kept, time zone added)" push its column past the
        right edge, where it was hidden.
        """
        header = self.header()
        for column in range(self.columnCount()):
            header.setSectionResizeMode(column, QHeaderView.Fixed)
        available = self.viewport().width()
        name = max(self._content_widths(0), default=0)
        current = max(self._content_widths(1), default=0)
        new_widths = sorted(self._content_widths(2))
        new = new_widths[-1] if new_widths else 0
        if name + current + new > available and new_widths:
            # Short of room: size the new date for most rows (9 in 10), so a
            # few long ones, such as "(time kept, time zone added)", are cut
            # short rather than squeezing every row's current date.
            typical = new_widths[(len(new_widths) - 1) * 9 // 10]
            new = max(typical, min(new, available - name - current))
        room = max(available - new - self.MIN_CURRENT_WIDTH, 0)
        name = max(min(name, room), min(self.MIN_NAME_WIDTH, name))
        new = max(min(new, available - name - self.MIN_CURRENT_WIDTH), 0)
        header.resizeSection(0, name)
        header.resizeSection(2, new)
        header.resizeSection(1, max(available - name - new, 0))

    def _content_widths(self, column: int) -> list[int]:
        """
        The width each row's text needs in a column, over every row (not
        just the ones in view), with room for the padding _is_cut_short
        allows for. Empty cells are left out.
        """
        widths = []
        for row in range(self.topLevelItemCount()):
            item = self.topLevelItem(row)
            if not item.text(column):
                continue
            font = QFont(self.font())
            font.setBold(item.font(column).bold())
            widths.append(QFontMetrics(font).horizontalAdvance(item.text(column)) + 12)
        return widths

    def viewportEvent(self, event) -> bool:
        if event.type() == QEvent.Resize:
            # Also when the vertical scroll bar comes or goes.
            result = super().viewportEvent(event)
            self.fit_columns()
            return result
        if event.type() != QEvent.ToolTip:
            return super().viewportEvent(event)
        item = self.itemAt(event.pos())
        text = self.row_tooltip(item) if item is not None else ""
        if text:
            QToolTip.showText(event.globalPos(), text, self.viewport())
        else:
            QToolTip.hideText()
            event.ignore()
        return True

    def row_tooltip(self, item) -> str:
        """The row in full, or "" when nothing in it is cut short."""
        data = item.data(0, CHANGE_ROW_ROLE)
        if not data or not any(self._is_cut_short(item, column) for column in range(self.columnCount())):
            return ""
        name, original, new = data
        return f"{name}\nOriginal: {original}\nNew: {new}"

    def _is_cut_short(self, item, column: int) -> bool:
        """Whether a cell's text is wider than its column (so it ends in "…")."""
        text = item.text(column)
        if not text:
            return False
        font = QFont(self.font())
        font.setBold(item.font(column).bold())
        # 2px of padding each side (dateChangesList::item in styles.py), plus
        # a little room Qt keeps around the text.
        return QFontMetrics(font).horizontalAdvance(text) > self.columnWidth(column) - 10


def _build_apply_step(window: "MainWindow") -> StepBox:
    """4. Check the changes (every selected photo, new dates in orange) and apply."""
    step = StepBox(4, "Check the changes and apply")
    window.date_hint_label = QLabel()
    window.date_hint_label.setObjectName("applyHint")
    window.date_hint_label.setWordWrap(True)

    window.date_changes_list = DateChangesList()
    window.date_changes_list.setObjectName("dateChangesList")
    window.date_changes_list.setColumnCount(3)
    window.date_changes_list.setHeaderHidden(True)
    window.date_changes_list.setRootIsDecorated(False)
    window.date_changes_list.setUniformRowHeights(True)
    window.date_changes_list.setSelectionMode(QAbstractItemView.NoSelection)
    window.date_changes_list.setFocusPolicy(Qt.NoFocus)
    window.date_changes_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    window.date_changes_list.setMinimumHeight(90)
    window.date_changes_list.setMaximumHeight(220)

    window.date_apply_button = QPushButton("Shift Selected Photos")
    window.date_apply_button.setObjectName("accentButton")
    window.date_apply_button.setEnabled(False)
    window.date_apply_button.setMinimumHeight(44)
    window.date_apply_button.setToolTip("Write the new dates into the selected photos")
    window.date_apply_button.clicked.connect(window.apply_date_change)

    step.body_layout.addWidget(window.date_hint_label)
    step.body_layout.addWidget(window.date_changes_list)
    step.body_layout.addWidget(window.date_apply_button)
    return step


def _build_date_time_tab(window: "MainWindow") -> QWidget:
    """
    The Date & Time tab as four steps, one after another: select photos,
    choose Shift or Set, correct the date and time, check and apply. Later
    steps stay grey until the earlier ones are done, and the pane scrolls to
    each step as it opens (see DateTimeEditorMixin._apply_date_time_state).
    """
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)

    window.date_scroll = QScrollArea()
    window.date_scroll.setObjectName("dateScroll")
    window.date_scroll.setWidgetResizable(True)
    window.date_scroll.setFrameShape(QFrame.NoFrame)
    window.date_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    window.date_scroll.viewport().setAutoFillBackground(False)
    content = QWidget()
    content.setObjectName("dateScrollContent")
    content_layout = QVBoxLayout(content)
    content_layout.setContentsMargins(20, 14, 20, 20)
    content_layout.setSpacing(10)
    window.date_steps = [
        _build_select_step(window),
        _build_mode_step(window),
        _build_correct_step(window),
        _build_apply_step(window),
    ]
    for step in window.date_steps:
        content_layout.addWidget(step)
    content_layout.addStretch(1)
    window.date_scroll.setWidget(content)

    layout.addWidget(window.date_scroll, 1)
    return page


def refresh_tab_icons(window: "MainWindow") -> None:
    """
    White icon on the orange tab shown (the current mode), dark on the other.
    """
    current = window.editor_tabs.currentIndex()
    for index, icon in ((LOCATION_TAB, pin_icon), (DATE_TIME_TAB, clock_icon)):
        window.editor_tabs.setTabIcon(index, icon("#ffffff" if index == current else "#31445a"))


def build_editor_panel(window: "MainWindow") -> QWidget:
    """
    Create the right side pane: what is selected, then the Location and
    Date & Time tabs.
    """
    panel = QFrame()
    panel.setObjectName("panel")
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    # Brown: "your selection, the photos to change".
    header, _header_layout = build_pane_header("PHOTOS TO CHANGE", "change")

    window.editor_tabs = QTabWidget()
    window.editor_tabs.setObjectName("editorTabs")
    window.editor_tabs.tabBar().setDrawBase(False)
    window.editor_tabs.addTab(_build_location_tab(window), "Location")
    # "&&" shows a plain "&" (a single "&" marks a keyboard shortcut letter).
    window.editor_tabs.addTab(_build_date_time_tab(window), "Date && Time")
    refresh_tab_icons(window)
    window.editor_tabs.setTabToolTip(LOCATION_TAB, "Change where the selected photos were taken")
    window.editor_tabs.setTabToolTip(DATE_TIME_TAB, "Change when the selected photos were taken")
    # The Photo List switches between GPS groups and camera groups with it.
    window.editor_tabs.currentChanged.connect(window.editor_tab_changed)

    layout.addWidget(header)
    layout.addWidget(_build_selection_summary(window))
    layout.addWidget(window.editor_tabs, 1)
    return panel
