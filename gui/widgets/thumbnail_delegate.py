"""
Draws placeholder tiles with a moving shimmer for thumbnails still loading.

Why a delegate:
    Animating by swapping icons would mean updating every waiting item many
    times a second. Instead, waiting items are flagged with SHIMMER_ROLE and
    this delegate paints a gray tile with a light band over them. One timer
    moves the band (advance()) and repaints the grid once per frame.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)

# Item data role: True while an item's thumbnail is still loading and its
# placeholder should be drawn.
SHIMMER_ROLE = Qt.UserRole + 3

# Item data role: True in the Add Photos picker on photos already in the
# Photo List. They are drawn washed out with "In Photo List".
IN_LIST_ROLE = Qt.UserRole + 8

# Item data role: on group heading items, "no_gps" or "gps".
GROUP_HEADER_ROLE = Qt.UserRole + 4

# Item data role: True on the photo the New Location was taken from.
SOURCE_ROLE = Qt.UserRole + 5

# Item data role: while picking, on photos that cannot be picked. They are
# drawn dimmed with this label ("No GPS"; for a time "No Date" or "Being
# Changed"); True means "No GPS".
PICK_DISABLED_ROLE = Qt.UserRole + 6

# Item data role: True in "Only Show Selected Photos" on a photo that was
# deselected there. It stays in place, faded, so it can be clicked again.
FADED_ROLE = Qt.UserRole + 7

SOURCE_COLOR = QColor("#1f6feb")

# One sweep of the light band across a tile takes this long.
SHIMMER_PERIOD_MS = 1200

TILE_COLOR = QColor("#e3e9f0")
BAND_COLOR = QColor(255, 255, 255, 190)


class ThumbnailDelegate(QStyledItemDelegate):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # 0.0-1.0: where the light band is in its sweep.
        self.phase = 0.0

    def advance(self, elapsed_ms: int) -> None:
        """Move the light band forward by elapsed_ms of animation time."""
        self.phase = (self.phase + elapsed_ms / SHIMMER_PERIOD_MS) % 1.0

    def updateEditorGeometry(self, editor, option, index) -> None:
        # Group headings get their whole row. Qt would otherwise shrink them
        # by the photo tiles' padding, leaving a tall empty band around them.
        if index.data(GROUP_HEADER_ROLE) is not None:
            editor.setGeometry(option.rect)
            return
        super().updateEditorGeometry(editor, option, index)

    def paint(self, painter: QPainter, option, index) -> None:
        # Qt still asks to paint items hidden by the Show filter, with an empty
        # rectangle at the top-left corner; drawing markers there leaves a
        # stray chip in the corner of the grid.
        if option.rect.isEmpty():
            return
        super().paint(painter, option, index)
        pick_disabled = index.data(PICK_DISABLED_ROLE)
        if pick_disabled:
            _paint_washed_out(painter, option, pick_disabled if isinstance(pick_disabled, str) else "No GPS")
        elif index.data(IN_LIST_ROLE):
            # True: "In Photo List"; or the picker's own label ("Being Changed").
            in_list = index.data(IN_LIST_ROLE)
            _paint_washed_out(painter, option, in_list if isinstance(in_list, str) else "In Photo List")
        elif index.data(FADED_ROLE):
            painter.fillRect(option.rect, QColor(255, 255, 255, 170))
        if index.data(SOURCE_ROLE):
            _paint_source_marker(painter, option)
        if not index.data(SHIMMER_ROLE):
            return

        style_option = QStyleOptionViewItem(option)
        self.initStyleOption(style_option, index)
        widget = style_option.widget
        style = widget.style() if widget is not None else QApplication.style()
        icon_rect = QRectF(
            style.subElementRect(QStyle.SE_ItemViewItemDecoration, style_option, widget)
        )
        if icon_rect.isEmpty():
            return

        tile = _placeholder_tile(icon_rect)
        tile_path = QPainterPath()
        tile_path.addRoundedRect(tile, 6, 6)

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillPath(tile_path, TILE_COLOR)

        # A soft light band sweeping left to right, clipped to the tile.
        band_width = tile.width() * 0.6
        band_left = tile.left() - band_width + (tile.width() + band_width) * self.phase
        gradient = QLinearGradient(band_left, 0, band_left + band_width, 0)
        transparent = QColor(BAND_COLOR)
        transparent.setAlpha(0)
        gradient.setColorAt(0.0, transparent)
        gradient.setColorAt(0.5, BAND_COLOR)
        gradient.setColorAt(1.0, transparent)
        painter.setClipPath(tile_path)
        painter.fillRect(tile, gradient)
        painter.restore()


def _placeholder_tile(icon_rect: QRectF) -> QRectF:
    """
    A 3:2 tile centered in the icon area, the shape of most photos.
    """
    width = icon_rect.width()
    height = min(icon_rect.height(), width * 2 / 3)
    top = icon_rect.top() + (icon_rect.height() - height) / 2
    return QRectF(icon_rect.left(), top, width, height)


def _paint_source_marker(painter: QPainter, option) -> None:
    """
    Blue outline and a "SOURCE" label: this photo's location is the one in
    New Location. Blue always means "where the location comes from".
    """
    rect = QRectF(option.rect).adjusted(3, 3, -3, -3)
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    pen = painter.pen()
    pen.setColor(SOURCE_COLOR)
    pen.setWidthF(2.5)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawRoundedRect(rect, 10, 10)

    label = "SOURCE"
    font = painter.font()
    font.setPointSizeF(max(7.0, font.pointSizeF() - 2))
    font.setBold(True)
    painter.setFont(font)
    metrics = painter.fontMetrics()
    chip = QRectF(rect.left() + 6, rect.top() + 6, metrics.horizontalAdvance(label) + 12, metrics.height() + 4)
    chip_path = QPainterPath()
    chip_path.addRoundedRect(chip, 6, 6)
    painter.fillPath(chip_path, SOURCE_COLOR)
    painter.setPen(QColor("white"))
    painter.drawText(chip, Qt.AlignCenter, label)
    painter.restore()


def _paint_washed_out(painter: QPainter, option, label: str) -> None:
    """
    Wash out a photo that cannot be picked and label it, for example
    "No GPS" while picking a location.
    """
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    rect = QRectF(option.rect)
    painter.fillRect(rect, QColor(244, 246, 249, 205))

    font = painter.font()
    font.setBold(True)
    painter.setFont(font)
    metrics = painter.fontMetrics()
    chip = QRectF(0, 0, metrics.horizontalAdvance(label) + 16, metrics.height() + 6)
    chip.moveCenter(rect.center() - QPointF(0, rect.height() * 0.12))
    chip_path = QPainterPath()
    chip_path.addRoundedRect(chip, 8, 8)
    painter.fillPath(chip_path, QColor("#8c9aa8"))
    painter.setPen(QColor("white"))
    painter.drawText(chip, Qt.AlignCenter, label)
    painter.restore()

