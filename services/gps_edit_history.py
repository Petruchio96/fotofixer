"""
Session-only undo/redo memory for GPS and date edits.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# GPS state of one file: (latitude, longitude), or (None, None) for no GPS.
type GpsState = tuple[float | None, float | None]
# Date state of one file: its date tags (tag -> ExifTool text, or None).
type DateState = dict[str, str | None]

# What an edit changed, so undo knows how to write the states back.
EDIT_GPS = "gps"
EDIT_DATE = "date"


@dataclass(frozen=True)
class PhotoListSnapshot:
    """
    The photo list at the time of an edit: which photos were in it, in
    order, and which of them were selected.
    """

    paths: tuple[Path, ...] = ()
    selected: tuple[Path, ...] = ()


class GpsEditHistory:
    """
    Remember the most recent edit (a GPS apply or clear, or a date change)
    so it can be undone and redone. One history covers both kinds, so Undo
    always undoes the last change, whichever tab it was made on; kind says
    which it was.

    Along with the GPS states it keeps the photo list as it was at the time,
    so undo and redo can put the list back too (photos added or removed
    since then are undone with it), and the backup files the edit created,
    which undo deletes (redo makes them again).

    This is single-step: recording a new edit replaces the previous one. The
    history lives in memory only and is never written to disk.
    """

    def __init__(self) -> None:
        self._before: dict[Path, object] = {}
        self._after: dict[Path, object] = {}
        self._kind = EDIT_GPS
        self._photo_list: PhotoListSnapshot | None = None
        self._backups: tuple[Path, ...] = ()
        self._undone = False

    def record(
        self,
        *,
        before: dict[Path, GpsState] | dict[Path, DateState],
        after: dict[Path, GpsState] | dict[Path, DateState],
        photo_list: PhotoListSnapshot | None = None,
        backups: tuple[Path, ...] = (),
        kind: str = EDIT_GPS,
    ) -> None:
        """
        Remember an edit. Only files present in both mappings are kept, so
        files that failed to update are never "restored" by undo.

        Args:
            photo_list:
                The photo list when the edit was made (an edit doesn't change
                the list, so this is the list both before and after it).
            backups:
                Backup files ("<name>_original.<ext>") the edit created.
            kind:
                EDIT_GPS (states are GpsState) or EDIT_DATE (DateState).
        """
        paths = [path for path in after if path in before]
        self._before = {path: before[path] for path in paths}
        self._after = {path: after[path] for path in paths}
        self._photo_list = photo_list if paths else None
        self._backups = tuple(backups) if paths else ()
        self._kind = kind
        self._undone = False

    @property
    def kind(self) -> str:
        """EDIT_GPS or EDIT_DATE: what the remembered edit changed."""
        return self._kind

    def clear(self) -> None:
        self._before = {}
        self._after = {}
        self._photo_list = None
        self._backups = ()
        self._undone = False

    @property
    def backups(self) -> tuple[Path, ...]:
        """
        The backup files the edit created (delete them on undo).
        """
        return self._backups

    def set_backups(self, backups: tuple[Path, ...]) -> None:
        """
        After redo: the backups it made again, for the next undo.
        """
        self._backups = tuple(backups)

    @property
    def photo_list(self) -> PhotoListSnapshot | None:
        """
        The photo list to put back on undo or redo, if one was recorded.
        """
        return self._photo_list

    @property
    def can_undo(self) -> bool:
        return bool(self._before) and not self._undone

    @property
    def can_redo(self) -> bool:
        return bool(self._after) and self._undone

    def undo_states(self) -> dict:
        """
        States to write to undo the edit (see kind). Empty if there is
        nothing to undo.
        """
        return dict(self._before) if self.can_undo else {}

    def redo_states(self) -> dict:
        """
        States to write to redo the edit (see kind). Empty if there is
        nothing to redo.
        """
        return dict(self._after) if self.can_redo else {}

    def mark_undone(self) -> None:
        self._undone = True

    def mark_redone(self) -> None:
        self._undone = False
