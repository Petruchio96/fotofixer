"""
A compact date and time picker: date box, then hour : minute : second, am/pm,
and the time zone drop-down underneath.

Why a custom widget:
    Qt's QDateTimeEdit is one box where the arrows change whichever part has
    the cursor, which is fiddly. Separate drop-downs for the hour, minute,
    and second are quicker to set and harder to get wrong. The hour list
    reads "9 am", "2 pm", but the box shows just the hour, with am/pm as a
    label after the seconds.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QDate, QPointF, QSignalBlocker, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QStyle,
    QStyleOptionComboBox,
    QStylePainter,
    QWidget,
)

# The app's date format (see core/photo_dates.format_display_datetime).
DATE_DISPLAY_FORMAT = "MM/dd/yyyy"


ARROW_COLOR = QColor("#556579")


def paint_down_arrow(widget: QWidget) -> None:
    """
    A small chevron at the right edge, centered top to bottom. Styled combo
    and date boxes lose Qt's own arrow (styles.py hides it), so it is drawn
    here, close to the text.
    """
    painter = QPainter(widget)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(ARROW_COLOR if widget.isEnabled() else QColor("#a8b3bf"), 1.6)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    center = QPointF(widget.width() - 12, widget.height() / 2 + 0.5)
    painter.drawPolyline(
        [center + QPointF(-4, -2), center + QPointF(0, 2), center + QPointF(4, -2)]
    )
    painter.end()


class ChevronComboBox(QComboBox):
    """A drop-down with the app's own arrow (see paint_down_arrow)."""

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        paint_down_arrow(self)


class DateBox(QDateEdit):
    """The date with a calendar drop-down and the app's own arrow."""

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        paint_down_arrow(self)


class HourComboBox(ChevronComboBox):
    """
    Hours 0-23, listed as "12 am" … "11 pm". The closed box shows only the
    hour on the 12-hour clock; the am/pm label next to the seconds says which.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        for hour in range(24):
            self.addItem(f"{hour % 12 or 12} {'am' if hour < 12 else 'pm'}", hour)

    def paintEvent(self, event) -> None:
        painter = QStylePainter(self)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        option.currentText = str(self.currentIndex() % 12 or 12)
        painter.drawComplexControl(QStyle.CC_ComboBox, option)
        painter.drawControl(QStyle.CE_ComboBoxLabel, option)
        painter.end()
        paint_down_arrow(self)


class DateTimePicker(QWidget):
    """
    Pick a date and time to the second, and a time zone. changed fires when
    the user changes the date or time, zone_chosen (with the zone's key) when
    the user picks a time zone; neither fires for set_value()/set_zones().
    """

    changed = Signal()
    zone_chosen = Signal(str)

    def __init__(self, parent=None, *, what: str = "date and time") -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        outer.addLayout(layout)

        self.date_edit = DateBox()
        self.date_edit.setObjectName("dateField")
        self.date_edit.setDisplayFormat(DATE_DISPLAY_FORMAT)
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setToolTip(f"The {what}: the date (click the arrow for a calendar)")
        self.hour_box = HourComboBox()
        self.minute_box = ChevronComboBox()
        self.second_box = ChevronComboBox()
        for box in (self.minute_box, self.second_box):
            for value in range(60):
                box.addItem(f"{value:02d}", value)
        for box, tip in (
            (self.hour_box, "Hour"),
            (self.minute_box, "Minute"),
            (self.second_box, "Second"),
        ):
            box.setObjectName("timeField")
            box.setToolTip(f"The {what}: {tip.lower()}")
            box.setMaxVisibleItems(12)
            # Two digits and the arrow; the hour list is wider ("12 pm").
            box.setFixedWidth(64)
        self.hour_box.view().setMinimumWidth(76)
        self.date_edit.setFixedWidth(158)
        self.am_pm_label = QLabel("am")
        self.am_pm_label.setObjectName("amPmLabel")

        layout.addWidget(self.date_edit)
        layout.addSpacing(4)
        layout.addWidget(self.hour_box)
        layout.addWidget(_colon())
        layout.addWidget(self.minute_box)
        layout.addWidget(_colon())
        layout.addWidget(self.second_box)
        layout.addWidget(self.am_pm_label)
        layout.addStretch(1)

        self.date_edit.dateChanged.connect(self._user_changed)
        for box in (self.hour_box, self.minute_box, self.second_box):
            box.currentIndexChanged.connect(self._user_changed)

        # Time zones, east (top) to west; filled by set_zones().
        self.zone_box = ChevronComboBox()
        self.zone_box.setObjectName("timeZoneCombo")
        self.zone_box.setMaxVisibleItems(16)
        self.zone_box.setProperty("mixed", False)
        self.zone_box.activated.connect(lambda index: self.zone_chosen.emit(self.zone_box.itemData(index)))
        outer.addWidget(self.zone_box)

    def value(self) -> datetime:
        date = self.date_edit.date()
        return datetime(
            date.year(),
            date.month(),
            date.day(),
            self.hour_box.currentIndex(),
            self.minute_box.currentIndex(),
            self.second_box.currentIndex(),
        )

    def set_value(self, value: datetime) -> None:
        """Show a date and time, without firing changed."""
        blockers = [
            QSignalBlocker(widget)
            for widget in (self.date_edit, self.hour_box, self.minute_box, self.second_box)
        ]
        self.date_edit.setDate(QDate(value.year, value.month, value.day))
        self.hour_box.setCurrentIndex(value.hour)
        self.minute_box.setCurrentIndex(value.minute)
        self.second_box.setCurrentIndex(value.second)
        del blockers
        self._update_am_pm()

    def set_time_enabled(self, enabled: bool) -> None:
        """Turn the date and time parts on or off; the time zone box is separate."""
        for widget in (self.date_edit, self.hour_box, self.minute_box, self.second_box, self.am_pm_label):
            widget.setEnabled(enabled)

    def set_zones(self, items, key: str, *, mixed: bool, tooltip: str) -> None:
        """
        Fill the time zone list ((key, label) pairs) and show one, without
        firing zone_chosen. mixed shows it in red (the photos have more than
        one time zone).
        """
        fill_zone_box(self.zone_box, items, key, mixed=mixed, tooltip=tooltip)

    def _user_changed(self, *_args) -> None:
        self._update_am_pm()
        self.changed.emit()

    def _update_am_pm(self) -> None:
        self.am_pm_label.setText("am" if self.hour_box.currentIndex() < 12 else "pm")
        # The hour box draws itself (see HourComboBox.paintEvent).
        self.hour_box.update()


def fill_zone_box(box: QComboBox, items, key: str, *, mixed: bool, tooltip: str) -> None:
    """
    Fill a time zone drop-down ((key, label) pairs) and show one, without
    firing its signals. mixed shows it in red (the photos have more than one
    time zone). Shared by the date and time pickers and Change Time Zone.
    """
    with QSignalBlocker(box):
        if [box.itemData(i) for i in range(box.count())] == [k for k, _ in items]:
            for index, (_key, label) in enumerate(items):
                box.setItemText(index, label)
        else:
            box.clear()
            for item_key, label in items:
                box.addItem(label, item_key)
        index = box.findData(key)
        box.setCurrentIndex(max(index, 0))
    box.setToolTip(tooltip)
    if box.property("mixed") != mixed:
        box.setProperty("mixed", mixed)
        box.style().unpolish(box)
        box.style().polish(box)


def _colon() -> QLabel:
    label = QLabel(":")
    label.setObjectName("timeColon")
    label.setAlignment(Qt.AlignCenter)
    return label
