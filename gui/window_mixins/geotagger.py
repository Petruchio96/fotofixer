"""
File > Geotag from GPS Track: match every photo in the Photo List to a GPS
track and write each one the position recorded when it was taken.

The flow: an empty list opens the Add Photos picker first; then a file
dialog for one or more GPX files (a day each, say); the files are read and
a plan built (services/geotag_service.py); the plan opens in the
GeotagWindow (gui/widgets/geotag_window.py), which shows what the apply
button will write. Apply asks the usual Replace / Skip question for photos
that already have GPS, then writes like Apply Location does: in the
background with a progress bar, one undo step, backups, and a status
message with Undo. The track is not kept after the window closes.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFileDialog, QMessageBox

from core.gpx_track import GpxError, TrackPoint, read_gpx_files
from core.models import GpsCoordinates
from core.time_zones import computer_utc_offset
from gui.widgets.editor_panel import DATE_TIME_TAB
from gui.widgets.geotag_window import GeotagWindow
from gui.window_mixins.map_picker import ESRI_KEY_SETTING
from gui.presenters.date_time_state import MODE_SHIFT
from services.geotag_service import GeotagPlan, build_geotag_plan, geotag_values
from services.models import OverwriteEntry

# QSettings keys: the folder tracks were last chosen from, and the window's
# size and position.
LAST_TRACK_FOLDER_SETTING = "geotag/last_track_folder"
GEOTAG_GEOMETRY_SETTING = "geotag/geometry"

GPX_FILTER = "GPS tracks (*.gpx *.GPX)"


def _photos(count: int) -> str:
    return f"{count} photo" if count == 1 else f"{count} photos"


class GeotaggerMixin:
    _geotag_window: GeotagWindow | None = None
    _geotag_plan: GeotagPlan | None = None
    _geotag_track: list[TrackPoint] = []
    _geotag_files: list[Path] = []

    # --- Opening --------------------------------------------------------------

    def geotag_from_track(self) -> None:
        """The menu item (enabled only with photos in the list): choose the track files."""
        if self.session.selected_paths:
            self._choose_track_files()

    def _choose_track_files(self) -> None:
        self._pick_track_files(self._open_geotag_window)

    def _pick_track_files(self, on_chosen) -> None:
        """
        The system file dialog for GPX files, shown without blocking (as the
        photo picker is). Tests replace this. on_chosen(paths) runs with
        the chosen files.
        """
        start = self.settings.value(LAST_TRACK_FOLDER_SETTING, "", type=str)
        if not start or not Path(start).is_dir():
            start = str(self._photo_picker_start_folder())
        dialog = QFileDialog(self, "Choose GPS Track Files", start, GPX_FILTER)
        dialog.setFileMode(QFileDialog.ExistingFiles)
        dialog.setAcceptMode(QFileDialog.AcceptOpen)
        self._track_dialog = dialog

        def chosen(files: list[str]) -> None:
            paths = [Path(file) for file in files]
            if paths:
                self.settings.setValue(LAST_TRACK_FOLDER_SETTING, str(paths[0].parent))
                on_chosen(paths)

        dialog.filesSelected.connect(chosen)
        dialog.setWindowModality(Qt.ApplicationModal)
        dialog.show()

    def _open_geotag_window(self, files: list[Path]) -> None:
        try:
            track = read_gpx_files(files)
        except GpxError as error:
            dialog = QMessageBox(self)
            dialog.setIcon(QMessageBox.Warning)
            dialog.setWindowTitle("Could Not Read the GPS Track")
            dialog.setText(str(error))
            dialog.setStandardButtons(QMessageBox.Ok)
            self.show_message(dialog)
            return
        self._geotag_track = track
        self._geotag_files = list(files)
        self._geotag_plan = None
        if self._geotag_window is None:
            self._geotag_window = self._build_geotag_window()
            geometry = self.settings.value(GEOTAG_GEOMETRY_SETTING)
            if geometry is not None:
                self._geotag_window.restoreGeometry(geometry)
        self._refresh_geotag_plan()
        self._geotag_window.show()
        self._geotag_window.raise_()
        self._geotag_window.activateWindow()

    def _build_geotag_window(self) -> GeotagWindow:
        window = GeotagWindow(self, fetcher=self._create_tile_fetcher(), icon_for=self._geotag_photo_icon)
        window.set_esri_key(self.settings.value(ESRI_KEY_SETTING, "", type=str))
        window.toggle_requested.connect(self._toggle_geotag_row)
        window.check_all_requested.connect(lambda: self._check_geotag_rows(True))
        window.uncheck_all_requested.connect(lambda: self._check_geotag_rows(False))
        window.add_photos_requested.connect(self._geotag_add_photos)
        window.shift_requested.connect(self._geotag_go_to_shift)
        window.apply_requested.connect(self._apply_geotag)
        window.closed.connect(self._geotag_cancelled)
        return window

    def _geotag_photo_icon(self, path: Path) -> QIcon:
        item = self._grid_items_by_path.get(str(path))
        if item is not None:
            return item.icon()
        return self.thumbnail_loader.load_icon(path, has_gps=False)

    def _refresh_geotag_plan(self) -> None:
        """Build (or rebuild, keeping the checks) the plan and show it."""
        if self._geotag_window is None or not self._geotag_track:
            return
        self._geotag_plan = build_geotag_plan(
            list(self.session.selected_paths),
            self.session.loaded_photo_infos,
            self._geotag_track,
            computer_utc_offset(datetime.now()),
            previous=self._geotag_plan,
            feet=self.use_feet,
        )
        names = [path.name for path in self._geotag_files]
        files_text = names[0] + (f" + {len(names) - 1} more" if len(names) > 1 else "") if names else ""
        self._geotag_window.set_plan(
            self._geotag_plan,
            [(point.latitude, point.longitude) for point in self._geotag_track],
            files_text,
            len(self._geotag_track),
        )

    # --- Hooks from the Photo List (photos read, thumbnails arrived) ----------

    def _geotag_photos_changed(self) -> None:
        if self._geotag_window is not None and self._geotag_window.isVisible():
            self._refresh_geotag_plan()

    def _geotag_thumbnails_changed(self) -> None:
        if self._geotag_window is not None and self._geotag_window.isVisible():
            self._geotag_window.refresh_thumbnails()

    # --- The window's requests ------------------------------------------------

    def _toggle_geotag_row(self, path_text: str) -> None:
        if self._geotag_plan is None or self._geotag_window is None:
            return
        path = Path(path_text)
        row = next((row for row in self._geotag_plan.rows if row.path == path), None)
        if row is None or not row.on_track:
            return
        self._geotag_plan.set_included(path, not row.included)
        self._geotag_window.refresh_row(row)

    def _check_geotag_rows(self, checked: bool) -> None:
        """
        Check All (the photos on the track without GPS, and those with GPS
        the track has a better position for; other photos with GPS are
        checked one by one on purpose) or Uncheck All (every photo).
        """
        if self._geotag_plan is None or self._geotag_window is None:
            return
        changed = []
        for row in self._geotag_plan.rows:
            if not row.on_track or row.included == checked or (checked and not row.checkable):
                continue
            self._geotag_plan.set_included(row.path, checked)
            changed.append(row)
        self._geotag_window.refresh_rows(changed)

    def _geotag_add_photos(self) -> None:
        """+ Add More Photos: the picker over the window; the plan refreshes as the photos are read."""
        self._pick_photo_files("Add Photos", self._add_chosen_photos)

    def _geotag_go_to_shift(self) -> None:
        """
        The warning's link: to Shift Date and Time with the window's dated
        photos selected. The track is dropped; the user loads it again after
        the shift.
        """
        plan = self._geotag_plan
        self._close_geotag_window()
        dated = [row.path for row in plan.rows if row.instant is not None] if plan else []
        self.select_browser_paths(dated)
        self.editor_tabs.setCurrentIndex(DATE_TIME_TAB)
        self.choose_date_change_mode(MODE_SHIFT)
        self._set_status_message(
            "Shift the dates, then open File > Geotag from GPS Track again and load the track.", "info"
        )

    def _geotag_cancelled(self) -> None:
        """Closed without applying: back to the main window, nothing selected."""
        self._forget_geotag()
        self.clear_photo_selection()

    def _close_geotag_window(self) -> None:
        if self._geotag_window is not None:
            self.settings.setValue(GEOTAG_GEOMETRY_SETTING, self._geotag_window.saveGeometry())
            window = self._geotag_window
            self._forget_geotag()
            window.closed.disconnect(self._geotag_cancelled)
            window.close()
            window.deleteLater()

    def _forget_geotag(self) -> None:
        self._geotag_window = None
        self._geotag_plan = None
        self._geotag_track = []
        self._geotag_files = []

    # --- Apply ----------------------------------------------------------------

    def _apply_geotag(self) -> None:
        plan = self._geotag_plan
        if plan is None or not plan.included:
            return
        with_gps = [
            OverwriteEntry(path=row.path, coordinates=GpsCoordinates(*row.current))
            for row in plan.included if row.has_gps and row.current is not None
        ]
        if not with_gps:
            self._write_geotag("replace")
            return
        self._ask_overwrite_choice(
            with_gps,
            other_count=len(plan.included) - len(with_gps),
            on_choice=self._write_geotag,
        )

    def _write_geotag(self, choice: str) -> None:
        plan = self._geotag_plan
        if plan is None:
            return
        if choice == "cancel":
            # Back to the window; nothing changed.
            if self._geotag_window is not None:
                self._geotag_window._applied = False
            return
        values = geotag_values(plan)
        skipped = 0
        if choice == "skip":
            keep = {row.path for row in plan.included if row.has_gps}
            values = {path: value for path, value in values.items() if path not in keep}
            skipped = len(keep)
        if not values:
            self._close_geotag_window()
            self._set_status_message("Nothing was changed: every photo on the track already had GPS.", "info")
            return
        targets = list(values)
        before_states = self._gps_states_for_paths(targets)
        self._close_geotag_window()

        def done(apply_result) -> None:
            self.session = apply_result.session
            backups = self._take_new_backups()
            result = apply_result.execution_result
            if result.successful_paths:
                self._remember_gps_edit(
                    before_states={path: before_states[path] for path in result.successful_paths},
                    # With the altitude, so Redo writes it back too.
                    after_states={path: values[path] for path in result.successful_paths},
                    backups=backups,
                )
            else:
                self._clear_gps_edit_history()
            # Like Apply Location: the changed photos are deselected, the
            # ones that failed stay selected to retry.
            self._rerender_selecting([path for path in targets if path not in set(result.successful_paths)])
            if result.successful_paths:
                message = f"Geotagged {_photos(len(result.successful_paths))} from the GPS track."
                if skipped:
                    message += f" Skipped {skipped} that already {'has' if skipped == 1 else 'had'} GPS."
                if backups:
                    copies = "a backup of the original" if len(backups) == 1 else f"{len(backups)} backups of the originals"
                    message += f" Saved {copies} next to {'it' if len(backups) == 1 else 'them'}."
                self._set_status_message(message, "success", undo=True)
            self._report_write_failures("geotag", list(result.failed_paths))

        self._run_writes(
            "Geotagging",
            len(values),
            lambda progress: self.workflow.write_gps_values_workflow(
                session=self.session,
                values_by_path=values,
                on_progress=progress,
            ),
            done,
        )

    def _update_geotag_action(self, loaded_count: int) -> None:
        """File > Geotag from GPS Track: only with photos in the list."""
        self.geotag_action.setEnabled(loaded_count > 0)
        self.geotag_action.setToolTip(
            "Load a GPS track (GPX) and give every photo taken while it was recorded the position recorded then"
            if loaded_count
            else "Add photos to the Photo List first, then load a GPS track to geotag them"
        )
