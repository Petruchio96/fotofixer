"""
The Geotag from GPS Track window (File menu).

Every photo in the Photo List is listed on the left, oldest first, and the
track is drawn in green on the map on the right with a dot for each photo:
orange where the track places a checked photo (a red ring when that
replaces the photo's own GPS), blue where an unchecked photo with GPS is
now, grey where the track would place a photo that is left out. The window
only shows what the apply button will write: nothing is written until it
is clicked.

Clicking a dot, or a photo's name in the list, zooms the map all the way
in on that photo and opens its preview beside the dot (the thumbnail, the
name and time, "‹ 1 of n ›" for several photos at one spot, and Leave Off
Track / Put On Track, or Suggested Track Location for a photo with GPS when
the track has a point within a minute of its time: its blue dot wears an
orange ring). One preview is open at a time: clicking another dot
or name moves it. The checkbox (and a little around it) is what checks a
photo; the master Check All box checks every photo on the track that has
no GPS yet, or unchecks everything.

Like the map window, it is modal and shown with show(), not a blocking
exec(). The main window (GeotaggerMixin) feeds it the plan and listens for
its signals; the window itself holds no workflow logic.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from core.map_tiles import ESRI_SATELLITE_MAP, SATELLITE_MAP, STREET_MAP, TileSource
from gui.widgets.map_view import (
    LEFT_OUT_PHOTO_COLOR,
    PHOTO_COLOR,
    REPLACE_RING_COLOR,
    SELECTED_PHOTO_COLOR,
    MapView,
    PhotoPin,
    TileFetcher,
)
from gui.widgets.map_window import FIT_PADDING, SINGLE_PHOTO_ZOOM, PhotoPreviewPopup
from gui.window_frame import apply_window_border
from services.geotag_service import GeotagPlan, GeotagRow, format_coordinates, nothing_matches_hint

# The row's GeotagRow (QListWidgetItem data role).
ROW_ROLE = Qt.UserRole + 1

ROW_HEIGHT = 46
# Clicks this far from a row's left edge hit its checkbox; the rest of the
# row opens the photo's preview on the map.
CHECKBOX_CLICK_WIDTH = 44
ROW_THUMB_WIDTH = 40
ROW_THUMB_HEIGHT = 30

# The preview's thumbnail: a fifth larger than the map window's.
PREVIEW_SIZE = 154
# How far the map zooms in on a clicked photo (street level, not the limit).
PHOTO_ZOOM = 17
# How far the preview sits from the dot it belongs to.
PREVIEW_OFFSET = 14
# Photos whose dots overlap on screen (this close, in pixels) share one
# preview: "‹ 1 of 3 ›".
SAME_DOT_PIXELS = 14

# Row colors: the checkbox says what is checked, so rows are plain, except
# the one whose preview is open (orange, the app's "selected"); grey text
# for photos the track has no position for.
ROW_ACTIVE_BG = QColor("#fff3e3")
ROW_ACTIVE_BORDER = QColor("#d97706")
ROW_PLAIN_BG = QColor("#ffffff")
ROW_PLAIN_BORDER = QColor("#e1e8ef")
NAME_COLOR = QColor("#162131")
NAME_MUTED = QColor("#6b7a8c")
TIME_COLOR = QColor("#556579")
TIME_MUTED = QColor("#8c9aa8")
CHIP_GREY = QColor("#8c9aa8")
CHIP_RED = QColor("#b42f2f")
CHECK_COLOR = QColor("#d97706")

READOUT_IDLE = "Hover a dot or a photo to see where it will be placed."

WARNING_TEXT = (
    "The map shows where each photo will be placed; nothing is written yet. If the locations "
    "look wrong, the camera's clock may be off: "
    '<a href="shift">Shift the date and time…</a> (then load the track again).'
)
SHIFT_LINK_HINT = (
    "Close this window and open Shift Date and Time with these photos selected "
    "(load the track again afterwards)"
)


class GeotagPreview(PhotoPreviewPopup):
    """
    The map's photo preview, inside the map (not a pop-up that closes on the
    next click): it stays until another photo is clicked. Leave Off Track /
    Put On Track toggles whether the photo is geotagged; the time taken is
    shown under the name.
    """

    def __init__(self, map_view: MapView, icon_for: Callable[[Path], QIcon], row_for: Callable[[str], GeotagRow | None]) -> None:
        super().__init__(map_view, icon_for)
        self.setWindowFlags(Qt.Widget)
        self._row_for = row_for
        self.thumbnail_button.setFixedSize(PREVIEW_SIZE + 8, PREVIEW_SIZE + 8)
        self.thumbnail_button.setIconSize(QSize(PREVIEW_SIZE, PREVIEW_SIZE))
        self.thumbnail_button.setToolTip("Zoom the map to this photo")
        self.time_label = QLabel()
        self.time_label.setObjectName("previewCount")
        self.time_label.setAlignment(Qt.AlignCenter)
        self.layout().insertWidget(2, self.time_label)
        self.hide()

    def _use_location(self) -> None:
        # The button toggles the photo; the preview stays open and re-reads.
        path = self.current_path
        if path is not None:
            self.use_location.emit(path)

    def show_photos(self, paths: list[str], point: QPoint) -> None:
        """Open on these photos beside point (map coordinates)."""
        self._paths = list(paths)
        self._index = 0
        self._show_current()
        self.adjustSize()
        self.place_beside(point)
        self.show()
        self.raise_()

    def place_beside(self, point: QPoint) -> None:
        """Beside the dot, kept inside the map."""
        area = self.parentWidget().rect()
        x = point.x() + PREVIEW_OFFSET
        y = point.y() - self.height() // 2
        if x + self.width() > area.right() - 8:
            x = point.x() - PREVIEW_OFFSET - self.width()
        x = max(8, min(x, area.right() - self.width() - 8))
        y = max(8, min(y, area.bottom() - self.height() - 8))
        self.move(x, y)

    def _show_current(self) -> None:
        super()._show_current()
        path = self.current_path
        row = self._row_for(path) if path is not None else None
        self.time_label.setText(row.time_text if row is not None else "")
        included = row is not None and row.included
        self.use_button.setEnabled(row is not None and row.on_track)
        suggested = row is not None and row.suggested and not included
        if included:
            self.use_button.setText("Leave Off Track")
        elif suggested:
            self.use_button.setText("Suggested Track Location")
        else:
            self.use_button.setText("Put On Track")
        # Orange = about to change (putting the photo on the track); a grey
        # outline for taking it off.
        self._style_button("outlineButton" if included else "accentButton")
        if row is not None and not row.on_track:
            self.use_button.setToolTip("The track has no position for this photo")
        elif included:
            self.use_button.setToolTip("Don't geotag this photo (the same as clearing its checkbox in the list)")
        elif suggested:
            self.use_button.setToolTip(
                "The track has a position within a minute of when this photo was taken: use it instead of "
                "the photo's own GPS (Apply will ask first)"
            )
        elif row is not None and row.has_gps:
            self.use_button.setToolTip("Replace this photo's own GPS with the track's position (Apply will ask first)")
        else:
            self.use_button.setToolTip("Geotag this photo after all (the same as checking its box in the list)")

    def _style_button(self, name: str) -> None:
        if self.use_button.objectName() != name:
            self.use_button.setObjectName(name)
            self.use_button.style().unpolish(self.use_button)
            self.use_button.style().polish(self.use_button)


class GeotagRowDelegate(QStyledItemDelegate):
    """
    Draws a row: checkbox (rows on the track), thumbnail, name, time, and
    the chip saying why a photo has no position. The row whose preview is
    open is orange.
    """

    def __init__(self, parent: GeotagList) -> None:
        super().__init__(parent)
        self._list = parent

    def sizeHint(self, option, index) -> QSize:
        # Width 0: the row is as wide as the list, never wider (no sideways scrolling).
        return QSize(0, ROW_HEIGHT)

    @staticmethod
    def row_border(row: GeotagRow, active: bool) -> QColor:
        """Orange around the open preview's row, and always around a suggested one."""
        return ROW_ACTIVE_BORDER if active or row.suggested else ROW_PLAIN_BORDER

    def paint(self, painter: QPainter, option, index) -> None:
        row: GeotagRow = index.data(ROW_ROLE)
        if row is None:
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        rect = option.rect.adjusted(3, 2, -3, -2)
        active = self._list.active_path == row.path
        painter.setPen(QPen(self.row_border(row, active), 2))
        painter.setBrush(ROW_ACTIVE_BG if active else ROW_PLAIN_BG)
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 10, 10)
        if not row.on_track:
            painter.setOpacity(0.6)

        x = rect.left() + 10
        if row.on_track:
            box = QRect(x, rect.center().y() - 9, 18, 18)
            painter.setPen(QPen(CHECK_COLOR if row.included else CHIP_GREY, 1.5))
            painter.setBrush(CHECK_COLOR if row.included else QColor("#ffffff"))
            painter.drawRoundedRect(box, 4, 4)
            if row.included:
                painter.setPen(QPen(QColor("#ffffff"), 2.2))
                painter.drawPolyline([QPoint(box.left() + 4, box.center().y()), QPoint(box.left() + 8, box.bottom() - 4), QPoint(box.right() - 3, box.top() + 4)])
        x += 18 + 8

        thumb = QRect(x, rect.center().y() - ROW_THUMB_HEIGHT // 2, ROW_THUMB_WIDTH, ROW_THUMB_HEIGHT)
        painter.setPen(QPen(QColor(0, 0, 0, 20), 1))
        painter.setBrush(QColor("#e1e8ef"))
        painter.drawRoundedRect(thumb, 4, 4)
        pixmap = self._list.row_pixmap(row.path)
        if pixmap is not None and not pixmap.isNull():
            scaled = pixmap.scaled(thumb.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            painter.drawPixmap(
                thumb.x() + (thumb.width() - scaled.width()) // 2,
                thumb.y() + (thumb.height() - scaled.height()) // 2,
                scaled,
            )
        x += ROW_THUMB_WIDTH + 8

        chip = row.chip
        right = rect.right() - 10
        font = painter.font()
        if chip:
            chip_font = painter.font()
            chip_font.setPointSizeF(max(7.0, font.pointSizeF() - 2))
            chip_font.setBold(True)
            painter.setFont(chip_font)
            width = painter.fontMetrics().horizontalAdvance(chip) + 14
            chip_rect = QRect(right - width, rect.center().y() - 9, width, 18)
            painter.setPen(Qt.NoPen)
            painter.setBrush(CHIP_RED if row.has_gps and row.on_track else CHIP_GREY)
            painter.drawRoundedRect(chip_rect, 9, 9)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(chip_rect, Qt.AlignCenter, chip)
            painter.setFont(font)
            right = chip_rect.left() - 8

        text_rect = QRect(x, rect.top() + 5, max(10, right - x), rect.height() - 10)
        name_font = painter.font()
        name_font.setBold(True)
        painter.setFont(name_font)
        painter.setPen(NAME_COLOR if row.on_track else NAME_MUTED)
        name = painter.fontMetrics().elidedText(row.name, Qt.ElideMiddle, text_rect.width())
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignTop, name)
        time_font = painter.font()
        time_font.setBold(False)
        time_font.setPointSizeF(max(7.0, font.pointSizeF() - 1))
        painter.setFont(time_font)
        painter.setPen(TIME_COLOR if row.on_track else TIME_MUTED)
        time_text = painter.fontMetrics().elidedText(row.time_text, Qt.ElideRight, text_rect.width())
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignBottom, time_text)
        painter.restore()


class GeotagList(QListWidget):
    """
    The photo list: one row per photo (GeotagRowDelegate draws it).

    hovered(path or ""): the mouse moved onto a row or off the list.
    toggled(path): a row's checkbox was clicked (or Space pressed on it).
    activated(path): the row was clicked outside its checkbox.
    """

    hovered = Signal(str)
    toggled = Signal(str)
    activated = Signal(str)

    def __init__(self, parent: QWidget, pixmap_for: Callable[[str], QPixmap | None]) -> None:
        super().__init__(parent)
        self.setObjectName("geotagList")
        self.setMouseTracking(True)
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setUniformItemSizes(True)
        self.setItemDelegate(GeotagRowDelegate(self))
        # The photo whose preview is open on the map.
        self.active_path: Path | None = None
        self._pixmap_for = pixmap_for
        self._items_by_path: dict[str, QListWidgetItem] = {}

    def row_pixmap(self, path: Path) -> QPixmap | None:
        return self._pixmap_for(str(path))

    def set_rows(self, rows: list[GeotagRow]) -> None:
        self.clear()
        self._items_by_path = {}
        for row in rows:
            item = QListWidgetItem()
            item.setData(ROW_ROLE, row)
            item.setToolTip(row.hint)
            item.setSizeHint(QSize(0, ROW_HEIGHT))
            self.addItem(item)
            self._items_by_path[str(row.path)] = item

    def update_row(self, row: GeotagRow) -> None:
        item = self._items_by_path.get(str(row.path))
        if item is not None:
            item.setData(ROW_ROLE, row)
            item.setToolTip(row.hint)

    def set_active(self, path: Path | None) -> None:
        if path == self.active_path:
            return
        self.active_path = path
        if path is not None:
            item = self._items_by_path.get(str(path))
            if item is not None:
                self.scrollToItem(item, QAbstractItemView.EnsureVisible)
        self.viewport().update()

    def _row_at(self, position) -> GeotagRow | None:
        item = self.itemAt(position)
        return item.data(ROW_ROLE) if item is not None else None

    def mouseMoveEvent(self, event) -> None:
        row = self._row_at(event.position().toPoint())
        self.hovered.emit(str(row.path) if row is not None else "")
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self.hovered.emit("")
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        position = event.position().toPoint()
        row = self._row_at(position)
        if event.button() == Qt.LeftButton and row is not None:
            item = self.itemAt(position)
            if row.on_track and position.x() - self.visualItemRect(item).left() <= CHECKBOX_CLICK_WIDTH:
                self.toggled.emit(str(row.path))
            else:
                self.activated.emit(str(row.path))
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Space and self.currentItem() is not None:
            row = self.currentItem().data(ROW_ROLE)
            if row is not None and row.on_track:
                self.toggled.emit(str(row.path))
                return
        super().keyPressEvent(event)


class GeotagWindow(QWidget):
    """
    The window. The main window gives it the plan (set_plan) and listens for:

    toggle_requested(path): a checkbox, or the preview's button.
    check_all_requested() / uncheck_all_requested(): the master checkbox.
    add_photos_requested(): + Add More Photos.
    shift_requested(): the "Shift the date and time…" link.
    apply_requested(): the apply button.
    closed(): closed without applying (Cancel, Esc, the title bar).
    """

    toggle_requested = Signal(str)
    check_all_requested = Signal()
    uncheck_all_requested = Signal()
    add_photos_requested = Signal()
    shift_requested = Signal()
    apply_requested = Signal()
    closed = Signal()

    def __init__(
        self,
        parent: QWidget,
        *,
        fetcher: TileFetcher,
        icon_for: Callable[[Path], QIcon],
    ) -> None:
        super().__init__(parent, Qt.Window)
        self.setWindowModality(Qt.ApplicationModal)
        self.setObjectName("geotagWindow")
        self.setWindowTitle("Geotag from GPS Track - FotoFixer")
        self.resize(1200, 760)
        self.setMinimumSize(900, 600)
        self._icon_for = icon_for
        self._plan: GeotagPlan | None = None
        self._rows_by_path: dict[str, GeotagRow] = {}
        self._pixmaps: dict[str, QPixmap | None] = {}
        self._esri_key = ""
        self._use_us_satellite = False
        self._hovered: str | None = None
        # The photo whose preview is open, and where its dot was when it
        # opened (the map re-zooms when the dot moves).
        self._active: str | None = None
        self._active_location: tuple[float, float] | None = None
        self._applied = False

        self.map_view = MapView(fetcher, self)
        self.map_view.pick_enabled = False
        self.map_view.setCursor(Qt.ArrowCursor)
        self.map_view.photo_pins_clicked.connect(self._dot_clicked)
        self.map_view.background_clicked.connect(self._close_preview)
        self.map_view.photos_hovered.connect(self._map_hovered)
        self.map_view.pointer_left.connect(lambda: self._set_hovered(None))
        self.map_view.view_changed.connect(self._view_changed)

        self.preview = GeotagPreview(self.map_view, icon_for, self._row_for)
        self.preview.use_location.connect(self.toggle_requested)
        self.preview.zoom_to.connect(self._zoom_to_active)

        self.photo_list = GeotagList(self, self._pixmap_for)
        self.photo_list.hovered.connect(lambda path: self._set_hovered(path or None))
        self.photo_list.toggled.connect(self.toggle_requested)
        self.photo_list.activated.connect(self.show_photo)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addLayout(self._build_toolbar())
        self.summary_label = QLabel()
        self.summary_label.setObjectName("geotagSummary")
        self.summary_label.setTextFormat(Qt.RichText)
        layout.addWidget(self.summary_label)

        splitter = QSplitter(Qt.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)
        self.list_heading = QLabel("Photos · ☑ will be geotagged")
        self.list_heading.setObjectName("geotagListHeading")
        left_layout.addWidget(self.list_heading)
        self.check_all_box = QCheckBox("Check All")
        self.check_all_box.setObjectName("geotagCheckAll")
        self.check_all_box.setToolTip(
            "Check every photo on the track without GPS and every suggested one (orange border), "
            "or uncheck every photo. Other photos with GPS are checked one by one."
        )
        self.check_all_box.clicked.connect(self._check_all_clicked)
        left_layout.addWidget(self.check_all_box)
        left_layout.addWidget(self.photo_list, 1)
        splitter.addWidget(left)
        splitter.addWidget(self.map_view)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 880])
        layout.addWidget(splitter, 1)

        self.readout_label = QLabel(READOUT_IDLE)
        self.readout_label.setObjectName("mapReadout")
        self.readout_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.readout_label)

        layout.addLayout(self._build_bottom_bar())
        apply_window_border(self)
        self._show_source_checked()

    # --- Building -------------------------------------------------------------

    def _build_toolbar(self) -> QHBoxLayout:
        toolbar = QHBoxLayout()
        toolbar.setSpacing(0)
        self.street_button = QPushButton(STREET_MAP.name)
        self.street_button.setProperty("segment", "first")
        self.street_button.setToolTip("Show the OpenStreetMap street map")
        self.street_button.clicked.connect(self.show_street_map)
        self.satellite_button = QPushButton()
        self.satellite_button.setProperty("segment", "last")
        self.satellite_button.clicked.connect(self.show_satellite_map)
        for button in (self.street_button, self.satellite_button):
            button.setObjectName("filterButton")
            button.setCheckable(True)
            toolbar.addWidget(button)
        toolbar.addStretch(1)

        self.show_track_button = QPushButton("Show Whole Track")
        self.show_track_button.setProperty("tone", "neutral")
        self.show_track_button.setToolTip("Zoom the map to fit the whole GPS track")
        self.show_track_button.clicked.connect(self.show_whole_track)
        self.show_matched_button = QPushButton("Show All Photos")
        self.show_matched_button.setProperty("tone", "neutral")
        self.show_matched_button.clicked.connect(self.show_all_photos)
        self.zoom_out_button = QPushButton("−")
        self.zoom_out_button.setProperty("tone", "neutral")
        self.zoom_out_button.setToolTip("Zoom out (or scroll the mouse wheel)")
        self.zoom_out_button.setFixedWidth(40)
        self.zoom_out_button.clicked.connect(lambda: self.map_view.zoom_by(-1))
        self.zoom_in_button = QPushButton("+")
        self.zoom_in_button.setProperty("tone", "neutral")
        self.zoom_in_button.setToolTip("Zoom in (or scroll the mouse wheel)")
        self.zoom_in_button.setFixedWidth(40)
        self.zoom_in_button.clicked.connect(lambda: self.map_view.zoom_by(1))
        for button in (self.show_track_button, self.show_matched_button):
            toolbar.addWidget(button)
            toolbar.addSpacing(8)
        toolbar.addSpacing(8)
        toolbar.addWidget(self.zoom_out_button)
        toolbar.addSpacing(4)
        toolbar.addWidget(self.zoom_in_button)
        return toolbar

    def _build_bottom_bar(self) -> QHBoxLayout:
        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        self.warning_label = QLabel()
        self.warning_label.setObjectName("geotagWarning")
        self.warning_label.setTextFormat(Qt.RichText)
        self.warning_label.setWordWrap(True)
        self.warning_label.setToolTip(SHIFT_LINK_HINT)
        self.warning_label.linkActivated.connect(lambda _link: self.shift_requested.emit())
        bottom.addWidget(self.warning_label, 1)
        self.add_photos_button = QPushButton("+ Add More Photos")
        self.add_photos_button.setObjectName("stepAddButton")
        self.add_photos_button.setToolTip(
            "Add more photos from your computer; they join the Photo List and the ones on the track are matched too"
        )
        self.add_photos_button.clicked.connect(self.add_photos_requested)
        bottom.addWidget(self.add_photos_button)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setProperty("tone", "neutral")
        self.cancel_button.setToolTip("Close without changing any photo")
        self.cancel_button.clicked.connect(self.close)
        bottom.addWidget(self.cancel_button)
        self.apply_button = QPushButton()
        self.apply_button.setObjectName("accentButton")
        self.apply_button.setMinimumHeight(44)
        self.apply_button.clicked.connect(self._apply)
        bottom.addWidget(self.apply_button)
        return bottom

    # --- The plan -------------------------------------------------------------

    def set_plan(self, plan: GeotagPlan, track: list[tuple[float, float]], files_text: str, points: int) -> None:
        """
        Show a plan (the first time, or again after more photos were added
        or a setting changed). files_text names the track files.
        """
        first = self._plan is None
        self._plan = plan
        self._rows_by_path = {str(row.path): row for row in plan.rows}
        self._pixmaps = {}
        self.map_view.set_track(track)
        self.photo_list.set_rows(plan.rows)
        self._refresh_dots()
        matched = len(plan.matched)
        color = "#b45f06" if matched else "#9b2c2c"
        self.summary_label.setText(
            f"<span style='color:#15803d; font-weight:600'>▬ {files_text}</span>"
            f" &nbsp;·&nbsp; {plan.track_span_text()} &nbsp;·&nbsp; {points:,} point{'' if points == 1 else 's'}"
            f" &nbsp;·&nbsp; <span style='color:{color}; font-weight:600'>{plan.summary()}</span>"
        )
        self.summary_label.setToolTip("The GPS track files, when the track was recorded (in this computer's time zone), and how many photos it has a position for")
        self._update_buttons()
        if self._active is not None and self._active not in self._rows_by_path:
            self._close_preview()
        elif self._active is not None:
            self._refresh_preview()
        if first:
            self.show_whole_track()
            if any(row.has_gps for row in plan.rows):
                # The blue dots of photos with GPS may lie off the track.
                self.show_all_photos()

    def refresh_row(self, row: GeotagRow) -> None:
        """A row was toggled (its included flag and hint changed)."""
        self.refresh_rows([row])

    def refresh_rows(self, rows: list[GeotagRow]) -> None:
        for row in rows:
            self._rows_by_path[str(row.path)] = row
            self.photo_list.update_row(row)
        self._refresh_dots()
        self._update_buttons()
        self._refresh_preview()

    def refresh_thumbnails(self) -> None:
        """Thumbnails arrived in the main window: draw them."""
        self._pixmaps = {}
        self.photo_list.viewport().update()
        if self.preview.isVisible():
            self.preview._show_current()

    def _row_for(self, path: str) -> GeotagRow | None:
        return self._rows_by_path.get(path)

    def _marker_location(self, row: GeotagRow | None) -> tuple[float, float] | None:
        """
        Where the row's dot is: a photo with GPS that is unchecked sits
        where it is now; any other photo on the track sits where the track
        puts it; the rest have no dot.
        """
        if row is None:
            return None
        if row.has_gps and not row.included:
            return row.current
        if row.on_track:
            return (row.latitude, row.longitude)
        return None

    def _refresh_dots(self) -> None:
        if self._plan is None:
            return
        pins = []
        for row in self._plan.rows:
            location = self._marker_location(row)
            if location is None:
                continue
            if row.has_gps and not row.included:
                # Blue where it is now; an orange ring when the track has a
                # position within a minute of the photo's time to suggest.
                color, ring = PHOTO_COLOR, (SELECTED_PHOTO_COLOR if row.suggested else None)
            elif row.included:
                color, ring = SELECTED_PHOTO_COLOR, (REPLACE_RING_COLOR if row.has_gps else None)
            else:
                color, ring = LEFT_OUT_PHOTO_COLOR, None
            pins.append(PhotoPin(
                path=str(row.path), latitude=location[0], longitude=location[1],
                color=color, ring=ring, hovered=str(row.path) == self._hovered, hint=row.hint,
            ))
        self.map_view.set_photo_pins(pins)

    def _pixmap_for(self, path: str) -> QPixmap | None:
        if path not in self._pixmaps:
            icon = self._icon_for(Path(path))
            pixmap = icon.pixmap(QSize(128, 128)) if icon is not None else QPixmap()
            self._pixmaps[path] = None if pixmap.isNull() else pixmap
        return self._pixmaps[path]

    def _update_buttons(self) -> None:
        if self._plan is None:
            return
        included = len(self._plan.included)
        matched = len(self._plan.matched)
        if included:
            self.apply_button.setText(f"Geotag {included} Photo{'' if included == 1 else 's'}")
            self.apply_button.setToolTip(
                "Write the track's position (and altitude) into every checked photo. You can undo this afterwards."
            )
        else:
            self.apply_button.setText("No Photos on the Track")
            self.apply_button.setToolTip(
                "No photo is checked to geotag" if matched else "No photo in the list was taken while the track was recorded"
            )
        self.apply_button.setEnabled(included > 0)
        # The master box: full when every photo without GPS on the track is
        # checked, part when some are, empty when none.
        checkable = [row for row in self._plan.matched if row.checkable]
        checked = [row for row in checkable if row.included]
        self.check_all_box.blockSignals(True)
        if checkable and len(checked) == len(checkable):
            self.check_all_box.setCheckState(Qt.Checked)
        elif checked or (included and not checkable):
            self.check_all_box.setCheckState(Qt.PartiallyChecked)
        else:
            self.check_all_box.setCheckState(Qt.Unchecked)
        self.check_all_box.blockSignals(False)
        self.check_all_box.setEnabled(matched > 0)
        has_any = matched > 0 or any(row.has_gps for row in self._plan.rows)
        self.show_matched_button.setEnabled(has_any)
        self.show_matched_button.setToolTip(
            "Zoom the map to fit every photo: where the track places them, and the blue dots where photos with GPS are now"
            if has_any else "No photo is on the track or has GPS"
        )
        if matched:
            self.warning_label.setProperty("tone", "warning")
            self.warning_label.setText(WARNING_TEXT)
        else:
            self.warning_label.setProperty("tone", "error")
            self.warning_label.setText(nothing_matches_hint(self._plan))
        self.warning_label.style().unpolish(self.warning_label)
        self.warning_label.style().polish(self.warning_label)

    def _check_all_clicked(self) -> None:
        """Clicked: check everything checkable, unless it all is already, then uncheck all."""
        if self._plan is None:
            return
        checkable = [row for row in self._plan.matched if row.checkable]
        if checkable and all(row.included for row in checkable):
            self.uncheck_all_requested.emit()
        elif not checkable and self._plan.included:
            self.uncheck_all_requested.emit()
        else:
            self.check_all_requested.emit()

    # --- Hover ----------------------------------------------------------------

    def _map_hovered(self, paths: list) -> None:
        self._set_hovered(paths[0] if paths else None)

    def _set_hovered(self, path: str | None) -> None:
        if path == self._hovered:
            return
        self._hovered = path
        self._refresh_dots()
        self.readout_label.setText(self._readout_for(self._rows_by_path.get(path) if path else None))

    def _readout_for(self, row: GeotagRow | None) -> str:
        feet = self._plan.feet if self._plan is not None else True
        if row is not None and row.has_gps and not row.included and row.current is not None:
            return f"{format_coordinates(*row.current)} — {row.name}, taken {row.time_text}: where it is now (unchecked)"
        if row is not None and row.on_track:
            return f"{format_coordinates(row.latitude, row.longitude, row.altitude, feet)} — {row.name}, taken {row.time_text}"
        return READOUT_IDLE

    # --- The preview ------------------------------------------------------------

    def show_photo(self, path: str) -> None:
        """
        A click on a dot or a row: zoom in on the photo and open its preview
        beside its dot (with the other photos at that spot). A photo with no
        dot can't be shown; clicking the shown photo's row again closes it.
        """
        row = self._rows_by_path.get(path)
        location = self._marker_location(row)
        if location is None:
            return
        if path == self._active and self.preview.isVisible() and location == self._active_location:
            self._close_preview()
            return
        self._active = path
        self._active_location = location
        self.photo_list.set_active(Path(path))
        self.map_view.set_view(location[0], location[1], max(self.map_view.zoom, PHOTO_ZOOM))
        point = self.map_view.screen_point_for(*location)
        same_spot = []
        for other in self._plan.rows if self._plan else []:
            other_location = self._marker_location(other)
            if str(other.path) == path or other_location is None:
                continue
            other_point = self.map_view.screen_point_for(*other_location)
            if abs(other_point.x() - point.x()) <= SAME_DOT_PIXELS and abs(other_point.y() - point.y()) <= SAME_DOT_PIXELS:
                same_spot.append(str(other.path))
        self.preview.show_photos([path, *same_spot], point.toPoint())

    def _dot_clicked(self, paths: list, _x: int, _y: int) -> None:
        if paths:
            self.show_photo(paths[0])

    def _refresh_preview(self) -> None:
        """After a change: the active photo's dot may have moved (checked or unchecked)."""
        if self._active is None:
            return
        row = self._rows_by_path.get(self._active)
        location = self._marker_location(row)
        if location is None:
            self._close_preview()
        elif location != self._active_location:
            self.show_photo(self._active)
        elif self.preview.isVisible():
            self.preview._show_current()

    def _zoom_to_active(self, path: str) -> None:
        """The preview's thumbnail: back to the photo (after panning away)."""
        location = self._marker_location(self._rows_by_path.get(path))
        if location is not None:
            self.map_view.set_view(location[0], location[1], max(self.map_view.zoom, PHOTO_ZOOM))

    def _view_changed(self) -> None:
        self._show_source_checked()
        if self.preview.isVisible() and self._active_location is not None:
            self.preview.place_beside(self.map_view.screen_point_for(*self._active_location).toPoint())

    def _close_preview(self) -> None:
        self.preview.hide()
        self._active = None
        self._active_location = None
        self.photo_list.set_active(None)

    # --- Map ------------------------------------------------------------------

    def set_esri_key(self, api_key: str) -> None:
        self._esri_key = api_key
        self.map_view.set_api_key(ESRI_SATELLITE_MAP.key, api_key)
        self._show_source_checked()

    def satellite_source(self) -> TileSource:
        if self._esri_key and not self._use_us_satellite:
            return ESRI_SATELLITE_MAP
        return SATELLITE_MAP

    def show_street_map(self) -> None:
        self.map_view.set_source(STREET_MAP)
        self._show_source_checked()

    def show_satellite_map(self) -> None:
        self.map_view.set_source(self.satellite_source())
        self._show_source_checked()

    def _show_source_checked(self) -> None:
        satellite = self.satellite_source()
        self.satellite_button.setText(satellite.name)
        self.satellite_button.setToolTip(
            "Show Esri's satellite imagery of the whole world"
            if satellite == ESRI_SATELLITE_MAP
            else "Show aerial photos of the United States from USGS. For worldwide "
            "imagery, add a free Esri key in Edit > Settings"
        )
        on_street = self.map_view.source == STREET_MAP
        self.street_button.setChecked(on_street)
        self.satellite_button.setChecked(not on_street)

    def show_whole_track(self) -> None:
        self.map_view.fit_points(self.map_view.track_points, padding=FIT_PADDING, max_zoom=SINGLE_PHOTO_ZOOM)

    def show_all_photos(self) -> None:
        """Fit every dot: the track's positions, and where photos with GPS are now."""
        if self._plan is None:
            return
        points = [location for row in self._plan.rows if (location := self._marker_location(row)) is not None]
        self.map_view.fit_points(points, padding=FIT_PADDING, max_zoom=SINGLE_PHOTO_ZOOM)

    # --- Closing --------------------------------------------------------------

    def _apply(self) -> None:
        self._applied = True
        self.apply_requested.emit()

    def closeEvent(self, event) -> None:
        self.preview.hide()
        super().closeEvent(event)
        if not self._applied:
            self.closed.emit()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            # Esc closes the preview first, then the window.
            if self.preview.isVisible():
                self._close_preview()
            else:
                self.close()
            return
        super().keyPressEvent(event)
