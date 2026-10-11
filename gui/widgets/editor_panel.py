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
    QSizePolicy,
    QTabWidget,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
)

from gui.presenters.date_time_state import MODE_SET, MODE_SHIFT
from gui.widgets.browser_panel import build_pane_header
from gui.widgets.date_time_picker import ChevronComboBox, DateTimePicker
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


def _build_date_group(window: "MainWindow") -> QGroupBox:
    """
    The Change Date and Time box (orange: what is about to change): the
    mode, the reference photo or the new date, and the list of changes.
    """
    group = QGroupBox("Change Date and Time")
    group.setObjectName("dateGroup")
    layout = QVBoxLayout(group)
    layout.setSpacing(10)

    mode_row = QHBoxLayout()
    mode_row.setSpacing(12)
    mode_label = QLabel("Change")
    mode_label.setObjectName("fieldLabel")
    window.date_mode_combo = ChevronComboBox()
    window.date_mode_combo.setObjectName("dateModeCombo")
    window.date_mode_combo.addItem("Shift Date and Time", MODE_SHIFT)
    window.date_mode_combo.addItem("Set a Single Date and Time", MODE_SET)
    window.date_mode_combo.setToolTip(
        "Shift every photo by the same amount, or give them all one date and time"
    )
    window.date_mode_combo.currentIndexChanged.connect(window.set_date_change_mode)
    mode_row.addWidget(mode_label)
    mode_row.addWidget(window.date_mode_combo, 1)
    window.date_mode_help = QLabel()
    window.date_mode_help.setObjectName("dateModeHelp")
    window.date_mode_help.setWordWrap(True)

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
    set_label = QLabel("New date and time")
    set_label.setObjectName("fieldLabel")
    window.date_set_picker = DateTimePicker(what="date and time to give every selected photo")
    window.date_set_picker.changed.connect(window.date_set_value_edited)
    window.date_set_picker.zone_chosen.connect(window.date_zone_chosen)
    set_layout.addWidget(set_label)
    set_layout.addWidget(window.date_set_picker)
    window.date_set_box.hide()
    # Only the changes list grows and shrinks with the window; these always
    # keep their full size (squeezing them would overlap their rows).
    for box in (window.date_shift_box, window.date_set_box):
        box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    # Every selected photo with its current date, and the new one if it changes.
    changes_label = QLabel("Changing date to:")
    changes_label.setObjectName("dateChangesTitle")
    window.date_changes_list = QTreeWidget()
    window.date_changes_list.setObjectName("dateChangesList")
    window.date_changes_list.setColumnCount(3)
    window.date_changes_list.setHeaderHidden(True)
    window.date_changes_list.setRootIsDecorated(False)
    window.date_changes_list.setUniformRowHeights(True)
    window.date_changes_list.setSelectionMode(QAbstractItemView.NoSelection)
    window.date_changes_list.setFocusPolicy(Qt.NoFocus)
    window.date_changes_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    window.date_changes_list.setMinimumHeight(56)

    layout.addLayout(mode_row)
    layout.addWidget(window.date_mode_help)
    layout.addWidget(window.date_shift_box)
    layout.addWidget(window.date_set_box)
    layout.addWidget(changes_label)
    # The list takes the room left, and scrolls past that.
    layout.addWidget(window.date_changes_list, 1)
    return group


class _ShrinkFirstContent(QWidget):
    """
    The Date & Time box inside its scroll area. With wrapping text inside,
    Qt's scroll area sizes it to its preferred height (heightForWidth), so it
    scrolled before the changes list had shrunk. Answering with the minimum
    height lets the list shrink first; it scrolls only when that's not enough.
    """

    def heightForWidth(self, width: int) -> int:
        return self.layout().minimumHeightForWidth(width)


def _build_date_time_tab(window: "MainWindow") -> QWidget:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(20, 16, 20, 20)
    layout.setSpacing(10)

    window.date_hint_label = QLabel()
    window.date_hint_label.setObjectName("applyHint")
    window.date_hint_label.setWordWrap(True)

    window.date_apply_button = QPushButton("Shift Selected Photos")
    window.date_apply_button.setObjectName("accentButton")
    window.date_apply_button.setEnabled(False)
    window.date_apply_button.setMinimumHeight(44)
    window.date_apply_button.setToolTip("Write the new dates into the selected photos")
    window.date_apply_button.clicked.connect(window.apply_date_change)

    # On a short window the box scrolls instead of squeezing its rows
    # together; otherwise the changes list fills the room left.
    scroll = QScrollArea()
    scroll.setObjectName("dateScroll")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.viewport().setAutoFillBackground(False)
    content = _ShrinkFirstContent()
    content.setObjectName("dateScrollContent")
    content_layout = QVBoxLayout(content)
    content_layout.setContentsMargins(0, 0, 0, 0)
    content_layout.addWidget(_build_date_group(window))
    scroll.setWidget(content)

    layout.addWidget(scroll, 1)
    layout.addWidget(window.date_hint_label)
    layout.addWidget(window.date_apply_button)
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
