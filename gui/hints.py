"""
Hover hints wrapped onto short, balanced lines.

Why this file exists:
    Qt shows a plain-text tooltip on one line however long it is, so the
    app's longer hints ran across the screen. Instead of editing every
    hint, one event filter on the application wraps each hint as it is
    shown: at most about HINT_WIDTH characters (8 to 10 words) per line,
    the lines about the same length, breaking at the end of a sentence
    when that keeps them balanced, otherwise at the nearest word. Hints
    written with their own line breaks keep them (each paragraph is
    wrapped on its own), so a hint can still lay itself out by hand.
"""

from __future__ import annotations

import math
import re

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QAbstractItemView, QApplication, QMenu, QToolTip, QWidget

# The longest line a hint gets, in characters: about 8 to 10 words.
HINT_WIDTH = 55
# A sentence end this close to the balanced break point wins over the
# nearest word, so lines end on a full stop when they can.
SENTENCE_SLACK = 15
# A last line shorter than this reads as an orphan: use another layout.
MIN_LAST_LINE = 12
# A line may run this much past HINT_WIDTH when that saves a line or lets
# it end on a sentence.
LINE_SLACK = 8

_SENTENCE_END = re.compile(r"[.!?;:)]\s")
# A number and its unit ("5 min", "2,897 ft", "11:16 am") stay together.
_UNIT = re.compile(r"^(min|h|s|ft|m|am|pm)[.,;:)]*$")


def wrap_hint(text: str, width: int = HINT_WIDTH) -> str:
    """
    text with line breaks so no line is much longer than width, the lines
    balanced. Paragraphs (existing line breaks) are wrapped one by one.
    """
    return "\n".join(_wrap_paragraph(paragraph, width) for paragraph in text.split("\n"))


def _wrap_paragraph(text: str, width: int) -> str:
    text = text.strip()
    if len(text) <= width:
        return text
    words = _words(text)
    for line_count in range(max(2, math.ceil(len(text) / (width + LINE_SLACK))), len(words)):
        # Sentence ends first; if that makes a line too long, plain balance.
        for prefer_sentences in (True, False):
            lines = _balanced_lines(words, line_count, prefer_sentences)
            if lines is not None and max(len(line) for line in lines) <= width + LINE_SLACK:
                return "\n".join(lines)
    return text


def _words(text: str) -> list[str]:
    """The words, with a unit glued to the number before it."""
    words: list[str] = []
    for word in text.split():
        if words and _UNIT.match(word) and words[-1][-1:].isdigit():
            words[-1] += " " + word
        else:
            words.append(word)
    return words


def _balanced_lines(words: list[str], line_count: int, prefer_sentences: bool = True) -> list[str] | None:
    """
    words on line_count lines, each break near its share of the text: at
    a sentence end within SENTENCE_SLACK of the ideal point, else at the
    word nearest it. None when the last line would be an orphan.
    """
    text = " ".join(words)
    total = len(text)
    # Where each word starts in text.
    starts = []
    position = 0
    for word in words:
        starts.append(position)
        position += len(word) + 1
    breaks: list[int] = []  # the index of the first word of each line after the first
    previous = 0
    for line in range(1, line_count):
        target = round(total * line / line_count)
        candidates = range(previous + 1, len(words) - (line_count - line) + 1)
        if not candidates:
            return None
        sentence_ends = [
            index for index in candidates
            if prefer_sentences
            and _SENTENCE_END.fullmatch(text[starts[index] - 2:starts[index]])
            and abs(starts[index] - target) <= SENTENCE_SLACK
        ]
        if sentence_ends:
            chosen = min(sentence_ends, key=lambda index: abs(starts[index] - target))
        else:
            chosen = min(candidates, key=lambda index: abs(starts[index] - target))
        breaks.append(chosen)
        previous = chosen
    bounds = [0, *breaks, len(words)]
    lines = [" ".join(words[bounds[i]:bounds[i + 1]]) for i in range(line_count)]
    if len(lines) > 1 and len(lines[-1]) < MIN_LAST_LINE:
        return None
    return lines


class HintWrapper(QObject):
    """
    Shows every tooltip wrapped. Installed once on the application; a
    widget whose hint already fits is left to Qt.
    """

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() != QEvent.ToolTip or not isinstance(watched, QWidget):
            return False
        text = self._hint_at(watched, event)
        if not text:
            return False
        wrapped = wrap_hint(text)
        if wrapped == text:
            return False
        QToolTip.showText(event.globalPos(), wrapped, watched)
        return True

    @staticmethod
    def _hint_at(widget: QWidget, event) -> str:
        if isinstance(widget, QMenu):
            action = widget.actionAt(event.pos())
            return action.toolTip() if action is not None else ""
        parent = widget.parent()
        if isinstance(parent, QAbstractItemView) and widget is parent.viewport():
            index = parent.indexAt(event.pos())
            text = index.data(Qt.ToolTipRole) if index.isValid() else None
            return str(text) if text else ""
        return widget.toolTip()


_installed: HintWrapper | None = None


def install_hint_wrapping() -> None:
    """Wrap every hint the application shows (once)."""
    global _installed
    app = QApplication.instance()
    if app is None or _installed is not None:
        return
    _installed = HintWrapper(app)
    app.installEventFilter(_installed)
