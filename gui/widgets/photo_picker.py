"""
The Add Photos picker: a folder tree on the left; the folder's subfolders
and photos on the right.

Why this file exists:
    The system file pickers mix folders and photos in one list, and on Linux
    choosing both at once silently does nothing. Here folders and photos can
    be chosen together: a chosen folder adds the photos in it (and, with
    "Add Photos in Subfolders", in every folder inside it). The selection
    stays while moving between folders. It also shows thumbnails (upright,
    with GPS badges) while choosing, and marks photos that are already in
    the Photo List.

Places in the tree:
    My Computer (Home and the user folders), Bookmarks (the Linux file
    manager's list), Devices (mounted drives), and Network (mounted shares).
    Any other folder can be typed or pasted into the path box.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import (
    QElapsedTimer,
    QItemSelectionModel,
    QPointF,
    QRect,
    QSignalBlocker,
    QSize,
    QStandardPaths,
    QStorageInfo,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QIcon, QKeySequence, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.places import (
    GVFS_FILE_SYSTEM,
    Place,
    folder_contents_summary,
    gvfs_share_name,
    has_subfolders,
    is_network_file_system,
    is_system_mount,
    list_photos,
    list_subfolders,
    network_share_name,
    parse_gtk_bookmarks,
)
from gui.background import CancelToken
from gui.widgets.thumbnail_delegate import IN_LIST_ROLE, SHIMMER_ROLE, ThumbnailDelegate
from gui.window_frame import apply_window_border
from services.models import WorkflowSession

# Item data roles.
PATH_ROLE = Qt.UserRole
HAS_GPS_ROLE = Qt.UserRole + 1
# On tree items: True once the folder's subfolders have been listed.
LOADED_ROLE = Qt.UserRole + 2
# On grid items: True for a folder tile (the rest are photos). Past the
# thumbnail delegate's roles (up to Qt.UserRole + 8).
IS_FOLDER_ROLE = Qt.UserRole + 9

THUMBNAILS_PER_BATCH = 24
GPS_PER_BATCH = 50
FOLDER_SUMMARIES_PER_BATCH = 20
# Room for the thumbnail and two lines of text (a folder's name and contents).
TILE_SIZE = QSize(170, 206)
# Placeholder animation frame interval (milliseconds), as in the Photo List.
SHIMMER_FRAME_MS = 40

# Matches QTreeWidget#pickerTree in styles.py.
TREE_BACKGROUND = QColor("#fbfdff")
# The selection color (orange = what is about to change): the dot on tree
# folders with something selected inside.
SELECTED_MARK_COLOR = QColor("#d97706")

# The tree's sections, in order: (title, places).
type PlaceSections = list[tuple[str, list[Place]]]


def _user_folder_places() -> list[Place]:
    """Home and the standard user folders that exist, in file-manager order."""
    locations = (
        ("Home", QStandardPaths.HomeLocation),
        ("Desktop", QStandardPaths.DesktopLocation),
        ("Documents", QStandardPaths.DocumentsLocation),
        ("Pictures", QStandardPaths.PicturesLocation),
        ("Music", QStandardPaths.MusicLocation),
        ("Videos", QStandardPaths.MoviesLocation),
        ("Downloads", QStandardPaths.DownloadLocation),
    )
    places: list[Place] = []
    seen: set[Path] = set()
    for name, location in locations:
        folder = QStandardPaths.writableLocation(location)
        if not folder or not Path(folder).is_dir():
            continue
        path = Path(folder)
        if path in seen:
            continue
        seen.add(path)
        # Use the folder's real name (it may be translated or renamed).
        places.append(Place(name if location == QStandardPaths.HomeLocation else path.name, path))
    return places


def _bookmark_places() -> list[Place]:
    """The Linux file manager's bookmarks that are reachable folders."""
    if not sys.platform.startswith("linux"):
        return []
    bookmarks_file = Path.home() / ".config" / "gtk-3.0" / "bookmarks"
    try:
        text = bookmarks_file.read_text(encoding="utf-8")
    except OSError:
        return []
    return [place for place in parse_gtk_bookmarks(text) if place.path.is_dir()]


def _drive_and_network_places() -> tuple[list[Place], list[Place]]:
    """Mounted drives and mounted network shares."""
    devices: list[Place] = []
    network: list[Place] = []
    for volume in QStorageInfo.mountedVolumes():
        if not volume.isValid() or not volume.isReady():
            continue
        root = volume.rootPath()
        file_system = bytes(volume.fileSystemType()).decode(errors="replace")
        path = Path(root)

        if file_system == GVFS_FILE_SYSTEM:
            # One folder per share opened in the file manager.
            for share in list_subfolders(path):
                network.append(Place(gvfs_share_name(share.name), share))
            continue
        if is_network_file_system(file_system):
            device = bytes(volume.device()).decode(errors="replace")
            network.append(Place(network_share_name(device, path), path))
            continue
        if is_system_mount(root, file_system):
            continue

        if sys.platform == "win32":
            # "Local Disk (C:)" style names.
            letter = root.rstrip("/\\")
            label = volume.displayName() if volume.displayName() != root else "Local Disk"
            name = f"{label} ({letter})"
        elif root == "/" and sys.platform != "darwin":
            # macOS names its startup disk ("Macintosh HD"); Linux doesn't.
            name = "File System"
        else:
            name = volume.displayName() or path.name
        devices.append(Place(name, path))
    return devices, network


def default_place_sections() -> PlaceSections:
    devices, network = _drive_and_network_places()
    user_folders = _user_folder_places()
    # Like the file manager, leave out bookmarks that repeat a user folder.
    user_paths = {place.path for place in user_folders}
    bookmarks = [place for place in _bookmark_places() if place.path not in user_paths]
    sections: PlaceSections = [
        ("My Computer", user_folders),
        ("Bookmarks", bookmarks),
        ("Drives" if sys.platform == "win32" else "Devices", devices),
        ("Network", network),
    ]
    return [(title, places) for title, places in sections if places]


def painted_folder_icon(size: QSize) -> QIcon:
    """
    A yellow folder drawn in code at any size: the picker's tree and its
    folder tiles. Qt's own folder icon differs per system and is too small
    to scale up to a tile on most of them. Drawn at twice the size too, for
    sharp edges on high-resolution screens.
    """
    icon = QIcon()
    for scale in (1, 2):
        pixmap = QPixmap(size * scale)
        pixmap.setDevicePixelRatio(scale)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        width = size.width() * (0.78 if size.width() > 32 else 0.92)
        height = width * 0.76
        left = (size.width() - width) / 2
        top = (size.height() - height) / 2
        unit = height / 16
        outline = max(1.0, unit * 0.35)
        back = QPainterPath()
        back.moveTo(left, top + unit)
        back.lineTo(left + width * 0.38, top + unit)
        back.lineTo(left + width * 0.38 + unit * 1.6, top + unit * 2.6)
        back.lineTo(left + width, top + unit * 2.6)
        back.lineTo(left + width, top + height)
        back.lineTo(left, top + height)
        back.closeSubpath()
        painter.setPen(QPen(QColor("#b7862a"), outline))
        painter.setBrush(QColor("#e9b949"))
        painter.drawPath(back)
        front = QPainterPath()
        front.addRoundedRect(left, top + unit * 4.6, width, height - unit * 4.6, unit * 0.7, unit * 0.7)
        painter.setPen(QPen(QColor("#c99a3a"), outline * 0.8))
        painter.setBrush(QColor("#f3cd6b"))
        painter.drawPath(front)
        painter.end()
        icon.addPixmap(pixmap)
        # The same in a selected tree row (Qt would otherwise dim it).
        icon.addPixmap(pixmap, QIcon.Selected)
    return icon


class PickerTree(QTreeWidget):
    """
    The folder tree. Draws its own expand arrows so the selected folder's
    highlight covers only its name, not the arrow beside it.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self._hovered_index = None
        # Set by the picker: True for folders to mark with an orange dot
        # (something inside them is selected).
        self.mark_test = None
        # A new selection repaints everything too (see mouseMoveEvent).
        self.currentItemChanged.connect(lambda *_: self.viewport().update())

    def drawBranches(self, painter: QPainter, rect, index) -> None:
        # Drawn in drawRow instead, after Qt has painted the row.
        pass

    def mouseMoveEvent(self, event) -> None:
        # Qt repaints only the row under the mouse when the hover moves, which
        # left a stale 1-pixel edge of a highlight in the arrow column beside
        # a neighboring row. Repaint the whole (small) tree instead.
        index = self.indexAt(event.position().toPoint())
        if index != self._hovered_index:
            self._hovered_index = index
            self.viewport().update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered_index = None
        self.viewport().update()
        super().leaveEvent(event)

    def drawRow(self, painter: QPainter, option, index) -> None:
        super().drawRow(painter, option, index)
        # The arrow column: everything left of the item itself.
        rect = QRect(0, option.rect.top(), self.visualRect(index).left(), option.rect.height())
        self._paint_arrow(painter, rect, index)
        item = self.itemFromIndex(index)
        if item is not None and self.mark_test is not None and self.mark_test(item):
            self._paint_mark(painter, option.rect)

    def _paint_mark(self, painter: QPainter, row: QRect) -> None:
        """An orange dot at the right end of the row."""
        radius = 4
        center = QPointF(self.viewport().width() - 14, row.center().y() + 0.5)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(SELECTED_MARK_COLOR)
        painter.drawEllipse(center, radius, radius)
        painter.restore()

    def _paint_arrow(self, painter: QPainter, rect: QRect, index) -> None:
        # Cover any selection or hover color Qt painted in the arrow column,
        # including a pixel above and below (antialiased highlight edges).
        painter.fillRect(rect.adjusted(0, -1, 0, 1), TREE_BACKGROUND)
        item = self.itemFromIndex(index)
        if item is None:
            return
        shows_arrow = item.childCount() > 0 or (
            item.childIndicatorPolicy() == QTreeWidgetItem.ShowIndicator
        )
        if not shows_arrow:
            return
        # The arrow sits in the last indentation step, left of the item.
        size = 8
        center = QPointF(rect.right() - self.indentation() / 2, rect.center().y())
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor("#7a8899"), 1.6)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        half = size / 2
        if item.isExpanded():
            points = [center + QPointF(-half, -half / 2), center + QPointF(0, half / 2), center + QPointF(half, -half / 2)]
        else:
            points = [center + QPointF(-half / 2, -half), center + QPointF(half / 2, 0), center + QPointF(-half / 2, half)]
        painter.drawPolyline(points)
        painter.restore()


class PickerGrid(QListWidget):
    """
    The picker's grid of folders and photos, with the same click rules as
    the Photo List: click adds or removes a folder or photo, Shift+click
    adds a range, Ctrl+A selects everything shown. Double-click opens a
    folder. Photos already in the Photo List can't be selected.
    """

    # Double-click on a photo (used to choose it in one-photo mode).
    photo_double_clicked = Signal()
    # Double-click on a folder: open it. Carries the folder's path (str).
    folder_double_clicked = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._anchor_row: int | None = None
        # One-photo mode: a click selects just that photo.
        self.single = False

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            event.accept()
            return
        item = self.itemAt(event.position().toPoint())
        self.setFocus(Qt.MouseFocusReason)
        if item is not None and item.flags() & Qt.ItemIsSelectable:
            row = self.row(item)
            if self.single:
                self._set_selected([other for other in self.selectedItems() if other is not item], False)
                self._set_selected([item], True)
            elif event.modifiers() & Qt.ShiftModifier and self._anchor_row is not None:
                first, last = sorted((self._anchor_row, row))
                self._set_selected([self.item(index) for index in range(first, last + 1)], True)
            else:
                self._anchor_row = row
                self._set_selected([item], not item.isSelected())
            self.setCurrentItem(item, QItemSelectionModel.NoUpdate)
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        # No drag selection.
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        item = self.itemAt(event.position().toPoint())
        if event.button() == Qt.LeftButton and item is not None and item.data(IS_FOLDER_ROLE):
            if not self.single:
                # The first click of the double-click selected (or
                # deselected) the folder; this undoes it, so opening a
                # folder leaves the selection as it was.
                self.mousePressEvent(event)
            self.folder_double_clicked.emit(item.data(PATH_ROLE))
            event.accept()
            return
        if self.single:
            if item is not None and item.flags() & Qt.ItemIsSelectable:
                self._set_selected([other for other in self.selectedItems() if other is not item], False)
                self._set_selected([item], True)
                self.photo_double_clicked.emit()
            event.accept()
            return
        self.mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.matches(QKeySequence.StandardKey.SelectAll):
            if not self.single:
                self.select_all()
            event.accept()
            return
        super().keyPressEvent(event)

    def selectable_items(self) -> list[QListWidgetItem]:
        return [
            self.item(row)
            for row in range(self.count())
            if self.item(row).flags() & Qt.ItemIsSelectable
        ]

    def select_all(self) -> None:
        """
        Select every photo shown (Select All, Ctrl+A). Folders are left as
        they are: they are chosen one by one with a click.
        """
        self._set_selected(
            [item for item in self.selectable_items() if not item.data(IS_FOLDER_ROLE)],
            True,
        )

    def _set_selected(self, items: list[QListWidgetItem], selected: bool) -> None:
        changed = False
        with QSignalBlocker(self):
            for item in items:
                if item.flags() & Qt.ItemIsSelectable and item.isSelected() != selected:
                    item.setSelected(selected)
                    changed = True
        if changed:
            self.viewport().update()
            self.itemSelectionChanged.emit()


class PhotoPickerDialog(QDialog):
    """
    Choose photos to add to the Photo List.

    Args:
        start_folder:
            The folder shown first.
        in_list:
            Photos already in the Photo List; they are marked and can't be
            selected again.
        workflow:
            Reads GPS data, to badge photos that have it.
        thumbnail_loader / background:
            Build thumbnails on the app's background thread.
        place_sections:
            The tree's places; read from the system when not given.
        single:
            Choose one photo (to use its location) instead of photos to add.
            Folders can then be opened but not selected.
        include_subfolders:
            Whether "Add Photos in Subfolders" starts checked.
    """

    def __init__(
        self,
        parent: QWidget | None,
        *,
        title: str,
        start_folder: Path,
        in_list: set[Path],
        workflow,
        thumbnail_loader,
        background,
        place_sections: PlaceSections | None = None,
        single: bool = False,
        include_subfolders: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("photoPicker")
        self.setWindowTitle(title)
        self.resize(1200, 780)
        self.setMinimumSize(820, 520)

        self._single = single
        self._start_include_subfolders = include_subfolders
        self._in_list = set() if single else {Path(path) for path in in_list}
        self._workflow = workflow
        self._thumbnail_loader = thumbnail_loader
        self._background = background
        # Drawn in code, like the grid's folder tiles, so the tree and the
        # grid match on every system. (QFileIconProvider asks the system
        # shell for icons, which on Windows has caused crashes elsewhere in
        # the app.)
        self._folder_icon = painted_folder_icon(QSize(18, 18))

        self.current_folder: Path | None = None
        self._back: list[Path] = []
        self._forward: list[Path] = []
        # Bumped on every folder change and on close, so late background
        # results for another folder (or a closed window) are ignored.
        self._generation = 0
        self._token: CancelToken | None = None
        self._items_by_path: dict[str, QListWidgetItem] = {}
        self._images: dict[str, object] = {}
        self._photo_count = 0
        self._blank_icon: QIcon | None = None
        self._folder_tile_icon: QIcon | None = None
        # Everything selected, in every folder visited: path -> True for a
        # folder, False for a photo, in the order selected. Kept here, not
        # in the grid, so the selection stays while moving between folders.
        self._chosen: dict[str, bool] = {}
        # The folders that hold selected photos (see _tree_item_marked).
        self._chosen_containers: set[Path] = set()

        # Animates the placeholder tiles while thumbnails load.
        self._shimmer_timer = QTimer(self)
        self._shimmer_timer.timeout.connect(self._advance_shimmer)
        self._shimmer_clock = QElapsedTimer()

        self._build_ui()
        self._fill_tree(place_sections if place_sections is not None else default_place_sections())
        self.finished.connect(self._stop_loading)
        self.open_folder(start_folder)

    # --- Layout ---------------------------------------------------------------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # A clearer edge on Windows 11 (see gui/window_frame.py).
        apply_window_border(self)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Navigation row: back, forward, up, and the path box.
        nav = QFrame()
        nav.setObjectName("pickerNav")
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(16, 12, 16, 12)
        nav_layout.setSpacing(8)
        self.back_button = self._nav_button("‹", "Back", self.go_back)
        self.forward_button = self._nav_button("›", "Forward", self.go_forward)
        self.up_button = self._nav_button("↑", "Up one folder", self.go_up)
        self.path_box = QLineEdit()
        self.path_box.setObjectName("pickerPath")
        self.path_box.setToolTip("Type or paste a folder and press Enter")
        self.path_box.returnPressed.connect(self._open_typed_folder)
        for button in (self.back_button, self.forward_button, self.up_button):
            nav_layout.addWidget(button)
        nav_layout.addWidget(self.path_box, 1)

        # Left: places and folders.
        self.tree = PickerTree()
        self.tree.setObjectName("pickerTree")
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(18)
        self.tree.setIconSize(QSize(18, 18))
        self.tree.itemExpanded.connect(self._load_subfolders)
        # Expanding or collapsing moves the dots (see _tree_item_marked).
        self.tree.itemExpanded.connect(lambda _item: self.tree.viewport().update())
        self.tree.itemCollapsed.connect(lambda _item: self.tree.viewport().update())
        self.tree.itemClicked.connect(self._tree_item_clicked)
        self.tree.mark_test = self._tree_item_marked
        self.tree.setMinimumWidth(220)

        # Right: the photos in the folder.
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(18, 12, 18, 0)
        right_layout.setSpacing(10)

        grid_box = QFrame()
        grid_box.setObjectName("gridBox")
        grid_box_layout = QVBoxLayout(grid_box)
        grid_box_layout.setContentsMargins(0, 0, 0, 0)
        grid_box_layout.setSpacing(0)
        grid_box_layout.addWidget(self._build_selection_bar())

        self.grid = PickerGrid()
        self.grid.setObjectName("thumbnailGrid")
        self.grid.setViewMode(QListWidget.IconMode)
        self.grid.setIconSize(QSize(128, 128))
        self.grid.setResizeMode(QListWidget.Adjust)
        self.grid.setSpacing(12)
        self.grid.setWordWrap(True)
        self.grid.setMovement(QListWidget.Static)
        self.grid.setDragEnabled(False)
        self.grid.setSelectionMode(QAbstractItemView.MultiSelection)
        self.grid.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.grid.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.grid.verticalScrollBar().setSingleStep(24)
        self.grid.setItemDelegate(ThumbnailDelegate(self.grid))
        self.grid.single = self._single
        self.grid.itemSelectionChanged.connect(self._grid_selection_changed)
        self.grid.photo_double_clicked.connect(self.accept)
        self.grid.folder_double_clicked.connect(lambda path: self.open_folder(Path(path)))
        grid_box_layout.addWidget(self.grid, 1)

        self.empty_label = QLabel()
        self.empty_label.setObjectName("pickerEmpty")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setWordWrap(True)
        grid_box_layout.addWidget(self.empty_label, 1)
        self.empty_label.hide()

        # Bottom row: a note, Cancel, and Add.
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 2, 0, 16)
        bottom.setSpacing(10)
        note = QLabel(
            "Choose a photo with GPS; its location goes into New Location."
            if self._single
            else "Click to select photos or folders. Double-click a folder to open it. "
            "Photos already in the Photo List can't be selected again."
        )
        note.setObjectName("pickerNote")
        note.setWordWrap(True)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setProperty("tone", "neutral")
        self.cancel_button.setToolTip("Close without adding photos")
        self.cancel_button.clicked.connect(self.reject)
        self.add_button = QPushButton("Add Photos to Photo List")
        self.add_button.setObjectName("pickerAddButton")
        self.add_button.setToolTip(
            "Put this photo's GPS coordinates in New Location"
            if self._single
            else "Add the selected photos, and the photos in the selected folders, to the Photo List"
        )
        self.add_button.clicked.connect(self.accept)
        bottom.addWidget(note, 1)
        bottom.addWidget(self.cancel_button)
        bottom.addWidget(self.add_button)

        right_layout.addWidget(grid_box, 1)
        right_layout.addLayout(bottom)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self.tree)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([320, 880])

        layout.addWidget(nav)
        layout.addWidget(splitter, 1)

        # Enter belongs to the path box (open the typed folder). Dialog
        # buttons would otherwise also "click" on Enter and could add photos.
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)
            button.setDefault(False)

    def _nav_button(self, text: str, tooltip: str, slot) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("pickerNavButton")
        button.setToolTip(tooltip)
        button.setFixedSize(34, 34)
        button.clicked.connect(slot)
        return button

    def _build_selection_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("selectionBar")
        bar.setProperty("active", False)
        self.selection_bar = bar
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(18, 4, 16, 4)
        layout.setSpacing(4)

        dot = QLabel("●")
        dot.setObjectName("selectionDot")
        self.selection_count_label = QLabel("0 selected")
        self.selection_count_label.setObjectName("selectionCount")
        self.select_all_button = QPushButton("Select All Photos")
        self.select_all_button.setToolTip("Select every photo shown (Ctrl+A); click folders to choose them")
        self.select_all_button.clicked.connect(self.grid_select_all)
        self.deselect_all_button = QPushButton("Deselect All")
        self.deselect_all_button.setToolTip("Deselect everything, in every folder")
        self.deselect_all_button.clicked.connect(self.grid_deselect_all)
        # Shown only while a folder is selected (see _update_selection).
        self.subfolders_check = QCheckBox("Add Photos in Subfolders")
        self.subfolders_check.setObjectName("selectionBarCheck")
        self.subfolders_check.setToolTip(
            "Also add the photos in every folder inside the selected folders"
        )
        self.subfolders_check.setChecked(self._start_include_subfolders)
        self.subfolders_check.setCursor(Qt.PointingHandCursor)
        self.subfolders_check.toggled.connect(lambda _checked: self._update_selection())
        self.subfolders_check.hide()
        self.folder_summary_label = QLabel()
        self.folder_summary_label.setObjectName("pickerSummary")

        layout.addWidget(dot)
        layout.addSpacing(4)
        layout.addWidget(self.selection_count_label)
        layout.addSpacing(8)
        for button in (self.select_all_button, self.deselect_all_button):
            separator = QLabel("|")
            separator.setObjectName("selectionBarSeparator")
            button.setObjectName("selectionBarButton")
            button.setCursor(Qt.PointingHandCursor)
            layout.addWidget(separator)
            layout.addWidget(button)
        layout.addStretch(1)
        layout.addWidget(self.subfolders_check)
        layout.addSpacing(12)
        layout.addWidget(self.folder_summary_label)
        if self._single:
            # Only one photo is chosen: no count or Select All needed.
            for widget in bar.findChildren(QWidget):
                if widget is not self.folder_summary_label:
                    widget.hide()
        return bar

    # --- Tree -----------------------------------------------------------------

    def _fill_tree(self, sections: PlaceSections) -> None:
        bold = QFont(self.tree.font())
        bold.setBold(True)
        for title, places in sections:
            section = QTreeWidgetItem([title])
            section.setFlags(Qt.ItemIsEnabled)
            section.setFont(0, bold)
            self.tree.addTopLevelItem(section)
            for place in places:
                section.addChild(self._folder_item(place.name, place.path))
            section.setExpanded(True)

    def _folder_item(self, name: str, path: Path) -> QTreeWidgetItem:
        item = QTreeWidgetItem([name])
        item.setData(0, PATH_ROLE, str(path))
        item.setToolTip(0, str(path))
        item.setIcon(0, self._folder_icon)
        # An expand arrow only if it has subfolders. The subfolders themselves
        # are listed when it is expanded (listing every folder up front would
        # be slow on network shares).
        item.setChildIndicatorPolicy(
            QTreeWidgetItem.ShowIndicator
            if has_subfolders(path)
            else QTreeWidgetItem.DontShowIndicator
        )
        return item

    def _load_subfolders(self, item: QTreeWidgetItem) -> None:
        path_text = item.data(0, PATH_ROLE)
        if path_text is None or item.data(0, LOADED_ROLE):
            return
        item.setData(0, LOADED_ROLE, True)
        subfolders = list_subfolders(Path(path_text))
        for folder in subfolders:
            item.addChild(self._folder_item(folder.name, folder))
        if not subfolders:
            item.setChildIndicatorPolicy(QTreeWidgetItem.DontShowIndicatorWhenChildless)

    def _tree_item_clicked(self, item: QTreeWidgetItem) -> None:
        path_text = item.data(0, PATH_ROLE)
        if path_text is not None:
            self.open_folder(Path(path_text))

    def _select_folder_in_tree(self, folder: Path) -> None:
        """
        Highlight the folder in the tree, opening the branches above it,
        starting from the place that contains it most closely.
        """
        best: QTreeWidgetItem | None = None
        best_depth = -1
        for section_index in range(self.tree.topLevelItemCount()):
            section = self.tree.topLevelItem(section_index)
            for child_index in range(section.childCount()):
                item = section.child(child_index)
                place = Path(item.data(0, PATH_ROLE))
                if folder == place or place in folder.parents:
                    depth = len(place.parts)
                    if depth > best_depth:
                        best, best_depth = item, depth

        with QSignalBlocker(self.tree):
            self.tree.clearSelection()
            item = best
            if item is not None:
                place = Path(item.data(0, PATH_ROLE))
                for part in folder.relative_to(place).parts:
                    self._load_subfolders(item)
                    item.setExpanded(True)
                    match = next(
                        (
                            item.child(index)
                            for index in range(item.childCount())
                            if Path(item.child(index).data(0, PATH_ROLE)).name == part
                        ),
                        None,
                    )
                    if match is None:
                        break
                    item = match
                item.setSelected(True)
                self.tree.setCurrentItem(item)
                self.tree.scrollToItem(item)

    # --- Navigation -----------------------------------------------------------

    def open_folder(self, folder: Path, *, remember: bool = True) -> bool:
        """
        Show a folder's photos. Returns False if it isn't a readable folder.
        """
        folder = Path(folder)
        if not folder.is_dir():
            return False
        if remember and self.current_folder is not None and folder != self.current_folder:
            self._back.append(self.current_folder)
            self._forward.clear()
        if self._single:
            # One photo is chosen from the folder it is in.
            self._chosen.clear()
        self.current_folder = folder
        self.path_box.setText(str(folder))
        self._set_path_error(False)
        self._select_folder_in_tree(folder)
        self._update_nav_buttons()
        self._load_photos(folder)
        return True

    def go_back(self) -> None:
        if self._back:
            self._forward.append(self.current_folder)
            self.open_folder(self._back.pop(), remember=False)

    def go_forward(self) -> None:
        if self._forward:
            self._back.append(self.current_folder)
            self.open_folder(self._forward.pop(), remember=False)

    def go_up(self) -> None:
        if self.current_folder is not None and self.current_folder.parent != self.current_folder:
            self.open_folder(self.current_folder.parent)

    def _open_typed_folder(self) -> None:
        text = os.path.expanduser(self.path_box.text().strip())
        if not text or not self.open_folder(Path(text)):
            self._set_path_error(True)

    def _set_path_error(self, error: bool) -> None:
        if self.path_box.property("error") != error:
            self.path_box.setProperty("error", error)
            self.path_box.style().unpolish(self.path_box)
            self.path_box.style().polish(self.path_box)
        self.path_box.setToolTip(
            "That folder doesn't exist or can't be opened"
            if error
            else "Type or paste a folder and press Enter"
        )

    def _update_nav_buttons(self) -> None:
        self.back_button.setEnabled(bool(self._back))
        self.forward_button.setEnabled(bool(self._forward))
        folder = self.current_folder
        self.up_button.setEnabled(folder is not None and folder.parent != folder)

    # --- Photos ---------------------------------------------------------------

    def _stop_loading(self, *_args) -> None:
        if self._token is not None:
            self._token.cancel()
            self._token = None
        self._generation += 1
        self._shimmer_timer.stop()

    def _load_photos(self, folder: Path) -> None:
        """
        Show the folder's subfolders and photos right away (photos as
        placeholder tiles with their names), then fill in thumbnails, folder
        contents, and GPS badges batch by batch in the background (reading
        every photo first is slow on network shares).
        """
        self._stop_loading()
        generation = self._generation
        token = CancelToken()
        self._token = token
        # Quietly: clearing deselects the old folder's items first, which
        # would otherwise drop them from the selection (see _chosen).
        with QSignalBlocker(self.grid):
            self.grid.clear()
        self._items_by_path = {}
        self._images = {}
        self._photo_count = 0
        self._show_message("")
        self.folder_summary_label.setText("Reading folder…")
        self._update_selection()

        def work():
            if token.cancelled:
                return None
            return list_subfolders(folder), list_photos(folder)

        def done(listing) -> None:
            if generation != self._generation or listing is None:
                return
            folders, photos = listing
            self._show_items(folders, photos)
            self._start_thumbnails(generation, token, photos, folders)

        def failed(exc: BaseException) -> None:
            if generation != self._generation:
                return
            self.folder_summary_label.setText("")
            self._show_message(f"This folder's photos could not be read:\n{exc}")

        self._background.submit(work, done, failed)

    def _cached_icon(self, path: Path) -> tuple[QIcon | None, bool]:
        """A thumbnail built earlier (in this window or the Photo List), and whether it has GPS."""
        for has_gps in (True, False):
            icon = self._thumbnail_loader.cached_icon(path, has_gps=has_gps)
            if icon is not None:
                return icon, has_gps
        return None, False

    def _show_items(self, folders: list[Path], photos: list[Path]) -> None:
        """Folder tiles first, then the photos, selected as remembered."""
        self._photo_count = len(photos)
        self.grid.setUpdatesEnabled(False)
        try:
            for path in folders:
                item = QListWidgetItem(self._folder_icon_for_tile(), path.name)
                item.setData(PATH_ROLE, str(path))
                item.setData(IS_FOLDER_ROLE, True)
                item.setSizeHint(TILE_SIZE)
                item.setToolTip(f"{path.name}\nDouble-click to open")
                if self._single:
                    # Opened (double-click), never chosen, in one-photo mode.
                    item.setFlags(Qt.ItemIsEnabled)
                self.grid.addItem(item)
                self._items_by_path[str(path)] = item
            for path in photos:
                icon, has_gps = self._cached_icon(path)
                item = QListWidgetItem(icon if icon is not None else self._blank(), path.name)
                item.setData(PATH_ROLE, str(path))
                item.setSizeHint(TILE_SIZE)
                if icon is None:
                    # A placeholder tile until the thumbnail arrives.
                    item.setData(SHIMMER_ROLE, True)
                    item.setToolTip(path.name)
                else:
                    self._set_gps(item, has_gps)
                if path in self._in_list:
                    item.setFlags(Qt.ItemIsEnabled)
                    item.setData(IN_LIST_ROLE, True)
                    item.setToolTip(f"{path.name}\nAlready in the Photo List")
                self.grid.addItem(item)
                self._items_by_path[str(path)] = item
            # Selected earlier (before leaving this folder): select again.
            # Signals are blocked, so this doesn't count as a new selection.
            with QSignalBlocker(self.grid):
                for key in self._chosen:
                    item = self._items_by_path.get(key)
                    if item is not None and item.flags() & Qt.ItemIsSelectable:
                        item.setSelected(True)
        finally:
            self.grid.setUpdatesEnabled(True)

        # Only "Reading folder…" while loading; no counts afterwards (next
        # to the selection count they were confusing).
        self.folder_summary_label.setText("")
        self._show_message(
            "" if folders or photos else "No photos or folders in this folder. Choose a folder on the left."
        )
        self._update_selection()

    def _folder_icon_for_tile(self) -> QIcon:
        """A large folder, the size of a thumbnail."""
        if self._folder_tile_icon is None:
            self._folder_tile_icon = painted_folder_icon(self.grid.iconSize())
        return self._folder_tile_icon

    def _set_gps(self, item: QListWidgetItem, has_gps: bool) -> None:
        item.setData(HAS_GPS_ROLE, has_gps)
        if not item.data(IN_LIST_ROLE):
            name = Path(item.data(PATH_ROLE)).name
            item.setToolTip(f"{name}\n{'Has GPS coordinates' if has_gps else 'No GPS coordinates'}")

    def _start_thumbnails(self, generation, token, photos: list[Path], folders: list[Path] = ()) -> None:
        """
        In the background: thumbnails for the whole folder first (top of the
        folder first), then what is in each subfolder, then GPS badges.
        Thumbnails come from the system cache or the small preview inside
        each photo where possible, so this is quick even for large photos on
        a network share.
        """
        pending = [
            path for path in photos
            if self._items_by_path[str(path)].data(SHIMMER_ROLE)
        ]
        if pending:
            self._shimmer_clock.start()
            self._shimmer_timer.start(SHIMMER_FRAME_MS)
        loader = self._thumbnail_loader
        workflow = self._workflow
        background = self._background

        def work() -> None:
            for start in range(0, len(pending), THUMBNAILS_PER_BATCH):
                if token.cancelled:
                    return
                images = loader.load_images(pending[start:start + THUMBNAILS_PER_BATCH])
                background.post(self._apply_thumbnails, (generation, images))

            # "5 photos, 2 folders" under each folder tile.
            for start in range(0, len(folders), FOLDER_SUMMARIES_PER_BATCH):
                if token.cancelled:
                    return
                summaries = {
                    folder: folder_contents_summary(folder)
                    for folder in folders[start:start + FOLDER_SUMMARIES_PER_BATCH]
                }
                background.post(self._apply_folder_summaries, (generation, summaries))

            # GPS badges second, so they never hold up the thumbnails.
            for start in range(0, len(photos), GPS_PER_BATCH):
                if token.cancelled:
                    return
                batch = photos[start:start + GPS_PER_BATCH]
                try:
                    session = workflow.refresh_photo_workflow(WorkflowSession(selected_paths=batch))
                except Exception:
                    # Badges are a convenience; leave them off.
                    return
                has_gps = {
                    path: info.current_latitude is not None and info.current_longitude is not None
                    for path, info in session.loaded_photo_infos.items()
                }
                background.post(self._apply_gps, (generation, has_gps))

        def finished(_result=None) -> None:
            if generation == self._generation:
                self._shimmer_timer.stop()

        background.submit(work, finished, finished)

    def _apply_thumbnails(self, payload) -> None:
        generation, images = payload
        if generation != self._generation:
            return
        for path, image in images.items():
            item = self._items_by_path.get(str(path))
            if item is None:
                continue
            # Kept so the GPS badge can be added when GPS is known.
            self._images[str(path)] = image
            has_gps = bool(item.data(HAS_GPS_ROLE))
            item.setIcon(self._thumbnail_loader.icon_from_image(path, has_gps, image))
            item.setData(SHIMMER_ROLE, False)
        if not any(item.data(SHIMMER_ROLE) for item in self._items_by_path.values()):
            self._shimmer_timer.stop()

    def _apply_folder_summaries(self, payload) -> None:
        generation, summaries = payload
        if generation != self._generation:
            return
        for folder, (photos, subfolders) in summaries.items():
            item = self._items_by_path.get(str(folder))
            if item is None:
                continue
            parts = []
            if photos:
                parts.append(_count(photos, "photo"))
            if subfolders:
                parts.append(_count(subfolders, "folder"))
            item.setText(f"{folder.name}\n{', '.join(parts) or 'No photos'}")

    def _apply_gps(self, payload) -> None:
        generation, has_gps = payload
        if generation != self._generation:
            return
        for path, gps in has_gps.items():
            item = self._items_by_path.get(str(path))
            if item is None:
                continue
            had_gps = bool(item.data(HAS_GPS_ROLE))
            self._set_gps(item, gps)
            key = str(path)
            if gps != had_gps and key in self._images:
                item.setIcon(self._thumbnail_loader.icon_from_image(path, gps, self._images[key]))

    def _advance_shimmer(self) -> None:
        self.grid.itemDelegate().advance(self._shimmer_clock.restart())
        self.grid.viewport().update()

    def _blank(self) -> QIcon:
        if self._blank_icon is None:
            pixmap = QPixmap(self.grid.iconSize())
            pixmap.fill(Qt.transparent)
            self._blank_icon = QIcon(pixmap)
        return self._blank_icon

    def _show_message(self, message: str) -> None:
        self.empty_label.setText(message)
        self.empty_label.setVisible(bool(message))
        self.grid.setVisible(not message)

    # --- Selection ------------------------------------------------------------

    def grid_select_all(self) -> None:
        self.grid.select_all()

    def grid_deselect_all(self) -> None:
        """Deselect everything, also what was selected in other folders."""
        self._chosen.clear()
        with QSignalBlocker(self.grid):
            self.grid.clearSelection()
        self.grid.viewport().update()
        self._update_selection()

    def selected_paths(self) -> list[Path]:
        """The photos chosen (in any folder), in the order selected."""
        return [Path(path) for path, is_folder in self._chosen.items() if not is_folder]

    def selected_folders(self) -> list[Path]:
        """The folders chosen, in the order selected."""
        return [Path(path) for path, is_folder in self._chosen.items() if is_folder]

    def include_subfolders(self) -> bool:
        """Whether "Add Photos in Subfolders" is checked."""
        return self.subfolders_check.isChecked()

    def _grid_selection_changed(self) -> None:
        """
        Copy the grid's selection into _chosen. Only the items shown are
        touched, so what was selected in other folders stays selected.
        """
        for row in range(self.grid.count()):
            item = self.grid.item(row)
            key = item.data(PATH_ROLE)
            if item.isSelected():
                if key not in self._chosen:
                    self._chosen[key] = bool(item.data(IS_FOLDER_ROLE))
            else:
                self._chosen.pop(key, None)
        self._update_selection()

    def _tree_item_marked(self, item: QTreeWidgetItem) -> bool:
        """
        True for a tree folder that holds selected photos (selected folders
        don't count). The dot goes on the deepest folder showing in the tree
        for each photo: a folder is marked for photos directly inside it,
        and for photos deeper down only while the subfolder holding them is
        hidden (collapsed). Likewise a place (Home) is not marked for what is
        inside another place in the tree (Pictures): that place gets it.
        """
        path_text = item.data(0, PATH_ROLE)
        if path_text is None or not self._chosen_containers:
            return False
        ancestor = item.parent()
        while ancestor is not None:
            if not ancestor.isExpanded():
                # Hidden in a collapsed branch: a folder above shows the dot.
                return False
            ancestor = ancestor.parent()
        folder = Path(path_text)
        containers = [
            container for container in self._chosen_containers
            if container == folder or folder in container.parents
        ]
        parent = item.parent()
        is_place = parent is not None and parent.data(0, PATH_ROLE) is None
        if is_place and containers:
            inner_places = [
                place for place in self._place_paths()
                if place != folder and folder in place.parents
            ]
            containers = [
                container for container in containers
                if not any(container == place or place in container.parents for place in inner_places)
            ]
        if item.isExpanded():
            # Photos inside a subfolder showing below this one mark that
            # subfolder instead.
            shown = [Path(item.child(index).data(0, PATH_ROLE)) for index in range(item.childCount())]
            containers = [
                container for container in containers
                if container == folder
                or not any(container == child or child in container.parents for child in shown)
            ]
        return bool(containers)

    def _place_paths(self) -> list[Path]:
        """The folders listed directly under the tree's sections."""
        paths = []
        for section_index in range(self.tree.topLevelItemCount()):
            section = self.tree.topLevelItem(section_index)
            for child_index in range(section.childCount()):
                paths.append(Path(section.child(child_index).data(0, PATH_ROLE)))
        return paths

    def _update_selection(self) -> None:
        photo_count = len(self.selected_paths())
        folder_count = len(self.selected_folders())
        count = photo_count + folder_count
        has_selection = count > 0
        parts = []
        if photo_count:
            parts.append(_count(photo_count, "photo"))
        if folder_count:
            parts.append(_count(folder_count, "folder"))
        chosen_text = " and ".join(parts)
        self.selection_count_label.setText(f"{chosen_text} selected" if has_selection else "0 selected")
        if self.selection_bar.property("active") != has_selection:
            self.selection_bar.setProperty("active", has_selection)
            for widget in [self.selection_bar, *self.selection_bar.findChildren(QWidget)]:
                widget.style().unpolish(widget)
                widget.style().polish(widget)
        selectable = self.grid.selectable_items()
        self.select_all_button.setEnabled(
            any(not item.isSelected() and not item.data(IS_FOLDER_ROLE) for item in selectable)
        )
        self.deselect_all_button.setEnabled(has_selection)
        self.subfolders_check.setVisible(folder_count > 0 and not self._single)
        self.add_button.setEnabled(has_selection)
        if self._single:
            self.add_button.setText("Use This Photo's Location")
        else:
            self.add_button.setText(
                f"Add {_count(photo_count, 'Photo') if photo_count else ''}"
                f"{' and ' if photo_count and folder_count else ''}"
                f"{_count(folder_count, 'Folder') if folder_count else ''} to Photo List"
                if has_selection
                else "Add Photos to Photo List"
            )

        # The tree's dots: which folders hold selected photos.
        self._chosen_containers = {
            Path(path).parent for path, is_folder in self._chosen.items() if not is_folder
        }
        self.tree.viewport().update()


def _count(number: int, word: str) -> str:
    """ "1 photo", "3 photos". """
    return f"{number} {word}{'' if number == 1 else 's'}"
