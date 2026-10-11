"""
Inspector panel UI builder (the right side of the window).

The photos selected in the Photo List are the photos being edited. This pane
shows what is selected, then two tabs: Location (the new location and the two
actions, Apply and Remove GPS, which is destructive so styled to stand apart)
and Date & Time (shift the selected photos' dates, or set one date on them).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
)

from gui.presenters.date_time_state import MODE_SET, MODE_SHIFT
from gui.widgets.browser_panel import build_pane_header
from gui.widgets.date_time_picker import DateTimePicker
from gui.widgets.icons import clock_icon, map_icon, pin_icon

if TYPE_CHECKING:
    from gui.main_window import MainWindow

# The pick button's label; it reads "Cancel" while picking.
PICK_BUTTON_TEXT = "From a Photo in the Photo List"
PICK_BUTTON_TIP = (
    "Click this, then click a photo with GPS in the Photo List to copy "
    "its location. The photos selected to change stay selected."
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
    window.show_map_button.setIcon(map_icon("#1f5fc4"))
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


def _choice_card(title: str, detail: str, tooltip: str) -> QPushButton:
    """
    Step 2's two big choices: a checkable button with a bold title and a
    line of explanation (labels inside pass clicks through to the button).
    """
    button = QPushButton()
    button.setObjectName("choiceCard")
    button.setCheckable(True)
    button.setToolTip(tooltip)
    button.setCursor(Qt.PointingHandCursor)
    layout = QVBoxLayout(button)
    layout.setContentsMargins(12, 10, 12, 10)
    layout.setSpacing(4)
    for text, name in ((title, "choiceTitle"), (detail, "choiceDetail")):
        label = QLabel(text)
        label.setObjectName(name)
        label.setWordWrap(True)
        label.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(label)
    # Room for a two-line title and three lines of explanation at the
    # narrowest pane width.
    button.setMinimumHeight(112)
    return button


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
    """2. Choose the kind of change: Shift or Set (nothing chosen at first)."""
    step = StepBox(2, "Choose the kind of change")
    window.date_shift_choice = _choice_card(
        "Shift Date and Time",
        "The time was off. Correct one photo; the rest move by the same amount.",
        "Move every selected photo by the same amount, keeping the time between them",
    )
    window.date_set_choice = _choice_card(
        "Set a Single Date and Time",
        "Every selected photo gets the same date and time (for example scans).",
        "Give every selected photo one date and time",
    )
    window.date_shift_choice.clicked.connect(lambda: window.choose_date_change_mode(MODE_SHIFT))
    window.date_set_choice.clicked.connect(lambda: window.choose_date_change_mode(MODE_SET))
    row = QHBoxLayout()
    row.setSpacing(10)
    row.addWidget(window.date_shift_choice, 1)
    row.addWidget(window.date_set_choice, 1)
    step.body_layout.addLayout(row)
    return step


def _build_correct_step(window: "MainWindow") -> StepBox:
    """
    3. Correct the date and time (Shift: the reference photo, its correct
    date, time and zone, or copy the time from a photo) or enter it (Set).
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

    step.body_layout.addWidget(window.date_shift_box)
    step.body_layout.addWidget(window.date_set_box)
    return step


def _build_apply_step(window: "MainWindow") -> StepBox:
    """4. Check the changes (every selected photo, new dates in orange) and apply."""
    step = StepBox(4, "Check the changes and apply")
    window.date_hint_label = QLabel()
    window.date_hint_label.setObjectName("applyHint")
    window.date_hint_label.setWordWrap(True)

    window.date_changes_list = QTreeWidget()
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
