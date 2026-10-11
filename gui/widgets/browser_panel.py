"""
Browser panel UI builder.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QItemSelectionModel, QPoint, QSignalBlocker, QSize, Qt
from PySide6.QtGui import QColor, QFont, QKeySequence, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gui.widgets.icons import plus_icon
from gui.widgets.loading_indicator import LoadingIndicator
from gui.widgets.thumbnail_delegate import PICK_DISABLED_ROLE, ThumbnailDelegate
from gui.window_mixins.photo_list import THUMBNAIL_PATH_ROLE

if TYPE_CHECKING:
    from gui.main_window import MainWindow


class ThumbnailGrid(QListWidget):
    """
    The photo grid, with click-to-add selection.

    Selection rules (the photos selected are the photos to change):
        - Click (or Ctrl+click) a photo: add it, or remove it if selected.
        - Shift+click: add every photo shown between the last clicked photo
          and this one (photos hidden by the Show filter are skipped).
        - Click empty space: nothing. Ctrl+A: select every photo shown.
        - Delete (or Backspace): remove the selected photos from the list.
        - Arrow keys move the focus without changing the selection; Space
          adds or removes the focused photo.
    Pick mode and right-click are handled separately and never change the
    selection.

    It also keeps full-width section rows sized correctly after resizing.
    """

    def __init__(self, window: "MainWindow") -> None:
        super().__init__()
        self._window = window
        # Shown in the middle of the grid when no photos are visible.
        self.empty_message = ""
        # Shift+click ranges start here: the path of the last photo clicked.
        self._anchor_path: str | None = None

    # --- Mouse --------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        # Pick mode: a click chooses the location source and never changes
        # which photos are selected for updating.
        if self._window.is_picking_location and event.button() == Qt.LeftButton:
            self._window.pick_location_from_item(self.itemAt(event.position().toPoint()))
            event.accept()
            return
        # Right-click opens the context menu for the photo under the cursor
        # without changing the selection (Qt would normally select it).
        if event.button() == Qt.RightButton:
            event.accept()
            return
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return

        position = event.position().toPoint()
        item = self._photo_item_at(position)
        self.setFocus(Qt.MouseFocusReason)
        if item is None:
            # Empty space (or a heading): keep the selection.
            pass
        elif event.modifiers() & Qt.ShiftModifier and not self._window.is_only_selected:
            self._add_range_to(item)
        else:
            self._toggle(item)
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        position = event.position().toPoint()
        # While picking, show a "not allowed" cursor over dimmed photos.
        if self._window.is_picking_location:
            item = self.itemAt(position)
            unpickable = item is not None and item.data(PICK_DISABLED_ROLE)
            self.viewport().setCursor(Qt.ForbiddenCursor if unpickable else Qt.CrossCursor)
            event.accept()
            return
        if event.buttons() & Qt.LeftButton:
            # No drag selection: dragging over the grid changes nothing.
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            # Our press handling already decided the selection; Qt's release
            # logic would otherwise collapse it to a single photo.
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if self._window.is_picking_location or event.button() != Qt.LeftButton:
            event.accept()
            return
        # A double-click is two clicks: treat the second one like a click.
        self.mousePressEvent(event)

    # --- Keyboard -----------------------------------------------------------

    def keyPressEvent(self, event) -> None:
        # Esc leaves pick mode when the grid has focus (the window-wide Esc
        # shortcut covers the rest of the window).
        if self._window.is_picking_location and event.key() == Qt.Key_Escape:
            self._window.stop_picking_location()
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Delete) or event.key() == Qt.Key_Backspace:
            # Delete (Backspace on a Mac keyboard) removes the selected
            # photos from the list, like Remove from List. Files are untouched.
            if not self._window.is_picking_location:
                self._window.remove_selected_from_list()
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.SelectAll):
            if self._window.select_all_button.isEnabled():
                # Only photos currently shown, like the Select All button.
                self._window.select_all_photos()
            event.accept()
            return
        if event.key() == Qt.Key_Space and not self._window.is_picking_location:
            item = self.currentItem()
            if item is not None and item.data(THUMBNAIL_PATH_ROLE) is not None and not item.isHidden():
                self._toggle(item)
            event.accept()
            return
        if event.key() in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down,
                           Qt.Key_Home, Qt.Key_End, Qt.Key_PageUp, Qt.Key_PageDown):
            # Move the focus only; never replace the selection.
            index = self.moveCursor(self._cursor_action_for(event.key()), event.modifiers())
            if index.isValid():
                self.selectionModel().setCurrentIndex(index, QItemSelectionModel.NoUpdate)
                self.scrollTo(index)
            event.accept()
            return
        super().keyPressEvent(event)

    @staticmethod
    def _cursor_action_for(key):
        return {
            Qt.Key_Left: QAbstractItemView.MoveLeft,
            Qt.Key_Right: QAbstractItemView.MoveRight,
            Qt.Key_Up: QAbstractItemView.MoveUp,
            Qt.Key_Down: QAbstractItemView.MoveDown,
            Qt.Key_Home: QAbstractItemView.MoveHome,
            Qt.Key_End: QAbstractItemView.MoveEnd,
            Qt.Key_PageUp: QAbstractItemView.MovePageUp,
            Qt.Key_PageDown: QAbstractItemView.MovePageDown,
        }[key]

    # --- Selection helpers ---------------------------------------------------

    def _photo_item_at(self, position: QPoint) -> QListWidgetItem | None:
        item = self.itemAt(position)
        if item is None or item.isHidden() or item.data(THUMBNAIL_PATH_ROLE) is None:
            return None
        return item

    def _visible_photo_items(self) -> list[QListWidgetItem]:
        # Rows are in on-screen order (no-GPS group first, then GPS group).
        return [
            self.item(row)
            for row in range(self.count())
            if self.item(row).data(THUMBNAIL_PATH_ROLE) is not None and not self.item(row).isHidden()
        ]

    def _toggle(self, item: QListWidgetItem) -> None:
        self._anchor_path = item.data(THUMBNAIL_PATH_ROLE)
        self.setCurrentItem(item, QItemSelectionModel.NoUpdate)
        self._set_selected([item], not item.isSelected())

    def _add_range_to(self, item: QListWidgetItem) -> None:
        items = self._visible_photo_items()
        anchor = next(
            (candidate for candidate in items if candidate.data(THUMBNAIL_PATH_ROLE) == self._anchor_path),
            None,
        )
        self.setCurrentItem(item, QItemSelectionModel.NoUpdate)
        if anchor is None:
            # No starting photo (or it is hidden): just add this photo.
            self._anchor_path = item.data(THUMBNAIL_PATH_ROLE)
            self._set_selected([item], True)
            return
        first, last = sorted((items.index(anchor), items.index(item)))
        self._set_selected(items[first:last + 1], True)

    def _set_selected(self, items: list[QListWidgetItem], selected: bool) -> None:
        """
        Change several items at once, then update the window once.
        """
        changed = False
        with QSignalBlocker(self):
            for item in items:
                if item.isSelected() != selected:
                    item.setSelected(selected)
                    changed = True
        if changed:
            self.viewport().update()
            self._window.update_details_panel()

    def set_empty_message(self, message: str) -> None:
        if message != self.empty_message:
            self.empty_message = message
            self.viewport().update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._window._refresh_thumbnail_group_header_sizes()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self.empty_message:
            return
        painter = QPainter(self.viewport())
        painter.setPen(QColor("#7a8899"))
        font = QFont(painter.font())
        font.setPointSize(font.pointSize() + 2)
        painter.setFont(font)
        painter.drawText(self.viewport().rect(), Qt.AlignCenter | Qt.TextWordWrap, self.empty_message)
        painter.end()


# Show filter values, in button order, with their hover hints.
GRID_FILTERS = (
    ("all", "All", "Show every photo in the list"),
    ("needs", "Needs GPS", "Show only the photos without GPS coordinates"),
    ("has", "Has GPS", "Show only the photos that have GPS coordinates"),
)

# Height of the colored header bars at the top of both panes.
PANE_HEADER_HEIGHT = 60


def build_pane_header(title: str, tone: str) -> tuple[QFrame, QHBoxLayout]:
    """
    A colored bar across the top of a pane, with its title on the left.

    Returns the bar and its layout, so buttons can be added on the right.

    Args:
        tone:
            "list" (navy, the Photo List) or "change" (brown, Photos to Change).
    """
    header = QFrame()
    header.setObjectName("paneHeader")
    header.setProperty("tone", tone)
    header.setFixedHeight(PANE_HEADER_HEIGHT)
    layout = QHBoxLayout(header)
    layout.setContentsMargins(22, 0, 12, 0)
    layout.setSpacing(10)
    label = QLabel(title)
    label.setObjectName("paneHeaderTitle")
    layout.addWidget(label)
    layout.addStretch(1)
    return header, layout


def _selection_bar_separator() -> QLabel:
    separator = QLabel("|")
    separator.setObjectName("selectionBarSeparator")
    return separator


def _build_selection_bar(window: "MainWindow") -> QFrame:
    """
    The strip along the top of the grid: how many photos are selected, and
    what can be done with the selection. It turns orange (the selection
    color) once at least one photo is selected.
    """
    bar = QFrame()
    bar.setObjectName("selectionBar")
    bar.setProperty("active", False)
    layout = QHBoxLayout(bar)
    layout.setContentsMargins(18, 4, 10, 4)
    layout.setSpacing(4)

    window.selection_dot = QLabel("●")
    window.selection_dot.setObjectName("selectionDot")
    window.selection_count_label = QLabel("0 selected")
    window.selection_count_label.setObjectName("selectionCount")

    window.select_all_button = QPushButton("Select All")
    window.select_all_button.setToolTip("Select every photo shown (Ctrl+A)")
    window.select_all_button.clicked.connect(window.select_all_photos)

    window.deselect_all_button = QPushButton("Deselect All")
    window.deselect_all_button.setToolTip("Deselect all photos")
    window.deselect_all_button.clicked.connect(window.clear_photo_selection)

    window.remove_from_list_button = QPushButton("✕  Remove from List")
    window.remove_from_list_button.setToolTip(
        "Remove the selected photos from this list (Delete key). "
        "Files are not changed or deleted."
    )
    window.remove_from_list_button.clicked.connect(window.remove_selected_from_list)

    layout.addWidget(window.selection_dot)
    layout.addSpacing(4)
    layout.addWidget(window.selection_count_label)
    layout.addSpacing(8)
    for button in (
        window.select_all_button,
        window.deselect_all_button,
        window.remove_from_list_button,
    ):
        button.setObjectName("selectionBarButton")
        button.setCursor(Qt.PointingHandCursor)
        layout.addWidget(_selection_bar_separator())
        layout.addWidget(button)
    layout.addStretch(1)
    return bar


def build_browser_panel(window: "MainWindow") -> QWidget:
    """
    Create the Photo List pane shown on the left side.
    """
    panel = QFrame()
    panel.setObjectName("panel")
    panel_layout = QVBoxLayout(panel)
    panel_layout.setContentsMargins(0, 0, 0, 0)
    panel_layout.setSpacing(0)

    # Header bar: the title, and the buttons that change what is in the list.
    header, header_layout = build_pane_header("PHOTO LIST", "list")
    window.add_photos_button = QPushButton("Add Photos")
    window.add_photos_button.setObjectName("headerButton")
    window.add_photos_button.setIcon(plus_icon("#17304a"))
    window.add_photos_button.setToolTip(
        "Add photos to the list. Photos already in the list are skipped."
    )
    window.add_photos_button.clicked.connect(window.add_photos)
    window.clear_list_button = QPushButton("Clear List")
    window.clear_list_button.setObjectName("headerOutlineButton")
    window.clear_list_button.setEnabled(False)
    window.clear_list_button.setToolTip(
        "Remove every photo from this list. Files are not changed or deleted."
    )
    window.clear_list_button.clicked.connect(window.clear_photo_list)
    header_layout.addWidget(window.add_photos_button)
    header_layout.addWidget(window.clear_list_button)

    body = QWidget()
    layout = QVBoxLayout(body)
    layout.setContentsMargins(20, 16, 20, 20)
    layout.setSpacing(12)

    # Show filter (All / Needs GPS / Has GPS), a segmented control. On the
    # Date & Time tab a camera filter takes its place (see below).
    window.gps_filter_bar = QWidget()
    filter_row = QHBoxLayout(window.gps_filter_bar)
    filter_row.setContentsMargins(0, 0, 0, 0)
    filter_row.setSpacing(0)
    show_label = QLabel("Show")
    show_label.setObjectName("filterLabel")
    filter_row.addWidget(show_label)
    filter_row.addSpacing(10)
    window.grid_filter_group = QButtonGroup(panel)
    window.grid_filter_group.setExclusive(True)
    window.grid_filter_buttons = {}
    for position, (key, text, tooltip) in enumerate(GRID_FILTERS):
        button = QPushButton(text)
        button.setObjectName("filterButton")
        button.setProperty("filter", key)
        button.setCheckable(True)
        button.setToolTip(tooltip)
        button.setProperty(
            "segment",
            "first" if position == 0 else "last" if position == len(GRID_FILTERS) - 1 else "middle",
        )
        button.clicked.connect(lambda _checked=False, key=key: window.set_grid_filter(key))
        window.grid_filter_group.addButton(button)
        window.grid_filter_buttons[key] = button
        filter_row.addWidget(button)
    window.grid_filter_buttons["all"].setChecked(True)

    # A separate on/off switch, not a fourth view: it narrows the grid to the
    # selected photos whichever view was chosen.
    filter_row.addSpacing(16)
    window.only_selected_button = QPushButton("Only Show Selected Photos")
    window.only_selected_button.setObjectName("onlySelectedButton")
    window.only_selected_button.setCheckable(True)
    window.only_selected_button.setEnabled(False)
    window.only_selected_button.toggled.connect(window.set_only_selected)
    filter_row.addWidget(window.only_selected_button)
    filter_row.addStretch(1)

    # Date & Time mode: All, then one button per camera. Built when the
    # photos are shown (see PhotoListMixin._rebuild_camera_filter), and only
    # shown when the list has photos from more than one camera.
    window.camera_filter_bar = QWidget()
    window.camera_filter_layout = QHBoxLayout(window.camera_filter_bar)
    window.camera_filter_layout.setContentsMargins(0, 0, 0, 0)
    window.camera_filter_layout.setSpacing(0)
    camera_label = QLabel("Camera")
    camera_label.setObjectName("filterLabel")
    window.camera_filter_layout.addWidget(camera_label)
    window.camera_filter_layout.addSpacing(10)
    window.camera_filter_layout.addStretch(1)
    window.camera_filter_group = QButtonGroup(panel)
    window.camera_filter_group.setExclusive(True)
    window.camera_filter_buttons = {}
    window.camera_filter_bar.hide()

    # Banner shown while picking a location source from the grid.
    window.pick_banner = QFrame()
    window.pick_banner.setObjectName("pickBanner")
    banner_layout = QHBoxLayout(window.pick_banner)
    banner_layout.setContentsMargins(14, 8, 8, 8)
    window.pick_banner_label = QLabel()
    window.pick_banner_label.setObjectName("pickBannerText")
    window.pick_banner_label.setWordWrap(True)
    banner_layout.addWidget(window.pick_banner_label, 1)
    window.pick_banner.hide()

    window.list_widget = ThumbnailGrid(window)
    window.list_widget.setObjectName("thumbnailGrid")
    window.list_widget.setViewMode(QListWidget.IconMode)
    window.list_widget.setIconSize(QSize(128, 128))
    window.list_widget.setResizeMode(QListWidget.Adjust)
    window.list_widget.setSpacing(12)
    window.list_widget.setWordWrap(True)
    window.list_widget.setVerticalScrollMode(QListWidget.ScrollPerPixel)
    window.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    window.list_widget.setSelectionMode(QListWidget.ExtendedSelection)
    # Mouse moves are needed (not just drags) for the pick-mode cursor.
    window.list_widget.setMouseTracking(True)
    # Tiles stay in place: no dragging them around the grid.
    window.list_widget.setMovement(QListWidget.Static)
    window.list_widget.setDragEnabled(False)
    window.list_widget.setDragDropMode(QListWidget.NoDragDrop)
    window.list_widget.itemSelectionChanged.connect(window.update_details_panel)
    window.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
    window.list_widget.customContextMenuRequested.connect(window.show_context_menu)
    window.list_widget.verticalScrollBar().setSingleStep(24)
    # Draws shimmering placeholders for thumbnails that are still loading.
    window.thumbnail_delegate = ThumbnailDelegate(window.list_widget)
    window.list_widget.setItemDelegate(window.thumbnail_delegate)

    # The grid and its selection bar share one rounded box.
    grid_box = QFrame()
    grid_box.setObjectName("gridBox")
    grid_box_layout = QVBoxLayout(grid_box)
    grid_box_layout.setContentsMargins(0, 0, 0, 0)
    grid_box_layout.setSpacing(0)
    window.selection_bar = _build_selection_bar(window)
    grid_box_layout.addWidget(window.selection_bar)
    grid_box_layout.addWidget(window.list_widget, 1)

    # Status row under the grid, hidden unless there is something to say:
    # action feedback (with Undo), or the loading progress row.
    window.browser_hint = QLabel()
    window.browser_hint.setObjectName("browserHint")
    window.browser_hint.setWordWrap(True)
    window.browser_hint.setTextFormat(Qt.RichText)
    window.browser_hint.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
    window.browser_hint.linkActivated.connect(window._handle_status_link)

    window.loading_indicator = LoadingIndicator(window.browser_hint)
    window.loading_indicator.cancel_requested.connect(window.cancel_loading)
    window.loading_indicator.showing_changed.connect(window._update_status_row)
    window.loading_indicator.hide()

    layout.addWidget(window.gps_filter_bar)
    layout.addWidget(window.camera_filter_bar)
    layout.addWidget(window.pick_banner)
    layout.addWidget(grid_box, 1)
    layout.addWidget(window.loading_indicator)

    panel_layout.addWidget(header)
    panel_layout.addWidget(body, 1)
    return panel
