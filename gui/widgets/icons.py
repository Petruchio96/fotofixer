"""
Small line icons for buttons and tabs, drawn in code.

Drawing them with QPainter (instead of loading SVG files) keeps the packaged
app free of Qt's SVG plugin and keeps the icons sharp at any screen scale.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

ICON_SIZE = 16
# Drawn at 2x so they stay crisp on high-DPI screens.
_SCALE = 2


def _icon(color: str, draw, *, text_gap: int = 0) -> QIcon:
    """
    Draw a 16 px line icon. text_gap adds that many clear pixels on the
    right, for buttons whose style sets the icon too close to its text (the
    button's iconSize must grow by the same amount, or the icon shrinks).
    """
    pixmap = QPixmap((ICON_SIZE + text_gap) * _SCALE, ICON_SIZE * _SCALE)
    pixmap.setDevicePixelRatio(_SCALE)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color), 1.6)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    draw(painter)
    painter.end()
    return QIcon(pixmap)


def plus_icon(color: str) -> QIcon:
    def draw(painter: QPainter) -> None:
        painter.drawLine(QPointF(8, 3), QPointF(8, 13))
        painter.drawLine(QPointF(3, 8), QPointF(13, 8))

    return _icon(color, draw)


def pin_icon(color: str) -> QIcon:
    """Map pin, for the Location tab."""

    def draw(painter: QPainter) -> None:
        path = QPainterPath(QPointF(8, 14.5))
        path.cubicTo(QPointF(8, 14.5), QPointF(3, 10), QPointF(3, 6.5))
        path.arcTo(QRectF(3, 1.5, 10, 10), 180, -180)
        path.cubicTo(QPointF(13, 10), QPointF(8, 14.5), QPointF(8, 14.5))
        painter.drawPath(path)
        painter.drawEllipse(QPointF(8, 6.5), 1.8, 1.8)

    return _icon(color, draw)


def map_icon(color: str, *, text_gap: int = 0) -> QIcon:
    """Folded map, for Pick from a Map. text_gap: see _icon."""

    def draw(painter: QPainter) -> None:
        path = QPainterPath(QPointF(2, 4))
        path.lineTo(QPointF(6, 2.5))
        path.lineTo(QPointF(10, 4))
        path.lineTo(QPointF(14, 2.5))
        path.lineTo(QPointF(14, 12))
        path.lineTo(QPointF(10, 13.5))
        path.lineTo(QPointF(6, 12))
        path.lineTo(QPointF(2, 13.5))
        path.closeSubpath()
        painter.drawPath(path)
        painter.drawLine(QPointF(6, 2.5), QPointF(6, 12))
        painter.drawLine(QPointF(10, 4), QPointF(10, 13.5))

    return _icon(color, draw, text_gap=text_gap)


def location_pin_path(tip: QPointF, width: float, height: float) -> QPainterPath:
    """
    An upside-down teardrop pin whose point is at tip: the map's New
    Location pin and the GPS badge on thumbnails.
    """
    radius = width / 2
    head_center = QPointF(tip.x(), tip.y() - height + radius)
    path = QPainterPath(tip)
    path.cubicTo(
        QPointF(tip.x() - radius * 0.3, tip.y() - radius * 0.9),
        QPointF(tip.x() - radius, head_center.y() + radius * 0.6),
        QPointF(tip.x() - radius, head_center.y()),
    )
    path.arcTo(QRectF(head_center.x() - radius, head_center.y() - radius, width, width), 180, -180)
    path.cubicTo(
        QPointF(tip.x() + radius, head_center.y() + radius * 0.6),
        QPointF(tip.x() + radius * 0.3, tip.y() - radius * 0.9),
        tip,
    )
    return path


def draw_location_pin(
    painter: QPainter,
    tip: QPointF,
    *,
    width: float,
    height: float,
    fill: QColor,
    outline: float = 2.0,
    dot_radius: float = 4.5,
    shadow: bool = False,
) -> None:
    """
    Draw the teardrop pin: fill color, a white border, and a white dot in
    its head. With shadow, a soft shadow helps it stand out on a photo.
    """
    path = location_pin_path(tip, width, height)
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    if shadow:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 70))
        painter.drawPath(path.translated(1.0, 1.5))
    painter.setPen(QPen(QColor("#ffffff"), outline))
    painter.setBrush(fill)
    painter.drawPath(path)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#ffffff"))
    painter.drawEllipse(QPointF(tip.x(), tip.y() - height + width / 2), dot_radius, dot_radius)
    painter.restore()


def clock_icon(color: str) -> QIcon:
    """Clock face, for the Date & Time tab."""

    def draw(painter: QPainter) -> None:
        painter.drawEllipse(QPointF(8, 8), 6, 6)
        painter.drawLine(QPointF(8, 4.8), QPointF(8, 8))
        painter.drawLine(QPointF(8, 8), QPointF(10.2, 9.4))

    return _icon(color, draw)


def clock_shift_icon(color: str) -> QIcon:
    """Clock with a turn arrow, for Shift Date and Time."""

    def draw(painter: QPainter) -> None:
        painter.drawEllipse(QPointF(7.2, 8.8), 5.2, 5.2)
        painter.drawLine(QPointF(7.2, 6), QPointF(7.2, 8.8))
        painter.drawLine(QPointF(7.2, 8.8), QPointF(9.2, 10))
        # The arrow at the top right: the time moves.
        painter.drawLine(QPointF(13.2, 2.4), QPointF(13.2, 5.2))
        painter.drawLine(QPointF(13.2, 5.2), QPointF(10.8, 5.2))

    return _icon(color, draw)


def calendar_icon(color: str) -> QIcon:
    """Calendar page with a check mark, for Set One Date and Time."""

    def draw(painter: QPainter) -> None:
        painter.drawRoundedRect(QRectF(2.5, 3.2, 11, 10.4), 1.6, 1.6)
        painter.drawLine(QPointF(2.5, 6.4), QPointF(13.5, 6.4))
        painter.drawLine(QPointF(5.6, 2), QPointF(5.6, 4.2))
        painter.drawLine(QPointF(10.4, 2), QPointF(10.4, 4.2))
        path = QPainterPath(QPointF(6, 10))
        path.lineTo(QPointF(7.4, 11.4))
        path.lineTo(QPointF(10.2, 8.5))
        painter.drawPath(path)

    return _icon(color, draw)


def globe_icon(color: str) -> QIcon:
    """Globe, for Change Time Zone."""

    def draw(painter: QPainter) -> None:
        painter.drawEllipse(QPointF(8, 8), 6, 6)
        painter.drawLine(QPointF(2, 8), QPointF(14, 8))
        painter.drawEllipse(QPointF(8, 8), 2.6, 6)

    return _icon(color, draw)
