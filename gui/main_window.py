"""
Main application window.
"""

from __future__ import annotations

import html
from datetime import timedelta
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QSettings, QStandardPaths, Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core.places import photos_in_folders
from core.runtime_paths import resource_path
from gui.background import BackgroundRunner, InputBlocker
from gui.hints import install_hint_wrapping
from gui.styles import APP_STYLESHEET
from gui.thumbnail_loader import ThumbnailLoader
from gui.widgets.browser_panel import build_browser_panel
from gui.widgets.editor_panel import build_editor_panel
from gui.widgets.photo_picker import PhotoPickerDialog
from gui.widgets.settings_dialog import SettingsDialog
from gui.window_mixins.apply_workflow import ApplyWorkflowMixin
from gui.window_mixins.date_time_editor import DateTimeEditorMixin
from gui.window_mixins.geotagger import GeotaggerMixin
from gui.window_mixins.inspector import InspectorMixin
from gui.window_mixins.location_editor import LocationEditorMixin
from gui.window_mixins.map_picker import ESRI_KEY_SETTING, MapPickerMixin
from gui.window_mixins.photo_list import THUMBNAIL_BATCH_SIZE, PhotoListMixin
from gui.window_mixins.update_check import UpdateCheckMixin
from services.gps_edit_history import EDIT_DATE, EDIT_GPS, GpsEditHistory, PhotoListSnapshot
from services.models import OverwriteEntry, WorkflowSession
from services.workflow_facade import PhotoWorkflowFacade

APP_VERSION = "1.11.1"
# The app's name, and the subtitle shown with it where people first meet it
# (window title, About). Called Photo GPS Editor until 1.9.0.
APP_NAME = "FotoFixer"
APP_SUBTITLE = "When & Where"

# QSettings key for the "Keep Backup Copies of Originals" option.
KEEP_BACKUPS_SETTING = "keep_backup_copies"
# QSettings key: altitudes in feet (True, the default) or metres.
USE_FEET_SETTING = "units/feet"

# QSettings key: the folder photos were last chosen from, so the file
# pickers open there next time.
LAST_PHOTO_FOLDER_SETTING = "last_photo_folder"

# How long an action message (e.g. "Applied GPS to 3 photos. Undo") stays in
# the status row under the grid before the row hides again.
STATUS_MESSAGE_MS = 12000


class MainWindow(
    InspectorMixin,
    LocationEditorMixin,
    DateTimeEditorMixin,
    MapPickerMixin,
    GeotaggerMixin,
    UpdateCheckMixin,
    PhotoListMixin,
    ApplyWorkflowMixin,
    QMainWindow,
):
    """
    Main application window.

    This class focuses on window setup and shared Qt-level concerns while
    mixins handle the larger groups of UI actions.
    """

    # Sent with map tile downloads and update checks (the User-Agent), and
    # what the update check compares the latest release with.
    app_version = APP_VERSION

    def __init__(self, settings: QSettings | None = None) -> None:
        super().__init__()
        # Every hover hint in the app shows on short, balanced lines.
        install_hint_wrapping()

        # Saved preferences. Tests pass their own QSettings to stay isolated.
        self.settings = settings if settings is not None else QSettings()

        # The name, and the subtitle that says what it does.
        self.setWindowTitle(f"{APP_NAME} – {APP_SUBTITLE}")
        self.resize(1500, 920)
        self.setMinimumSize(1280, 820)

        self.workflow = PhotoWorkflowFacade()
        self.exiftool = self.workflow.writer
        self.loader = self.workflow.loader
        self.thumbnail_loader = ThumbnailLoader(
            thumbnail_size=128,
            preview_reader=self.workflow.read_embedded_previews,
            small_preview_reader=self.workflow.read_small_previews,
            use_system_cache=True,
        )

        self.session = WorkflowSession()
        self._is_splitting_manual_coordinates = False
        # Where the New Location came from (a photo), and pick-mode state.
        self._location_source = None
        # The source photo's altitude, copied to the targets by Apply (None: none).
        self._location_source_altitude = None
        self._picking_location = False
        # What pick mode picks: "location" (Location tab) or "time" (Date & Time).
        self._pick_kind = "location"
        self._filter_before_pick = None
        # Date & Time tab (see DateTimeEditorMixin): Shift or Set, the
        # reference photo chosen with the arrows (None: the earliest), the
        # shift entered, the photo the correct time came from, and Set's date.
        # None until Shift or Set is chosen (step 2).
        self._date_change_mode = None
        # The step the Date & Time tab last scrolled to.
        self._date_active_step = None
        self._date_reference = None
        self._date_shift = timedelta(0)
        self._time_source = None
        self._time_source_info = None
        self._date_set_value = None
        # The time zone chosen in the drop-down, or None (each photo keeps its own).
        self._date_zone = None
        # Change Time Zone's "Keep the clock time" (off: the moment stays).
        self._date_keep_clock = False
        # Step 2 opened again (all three choices showing) after one was chosen.
        self._date_choices_open = False
        # Date & Time mode's camera filter: "all" or one camera's name.
        self._camera_filter = "all"
        # The camera filter before picking a time (it shows every camera while
        # picking); put back when picking ends. None when not picking a time.
        self._camera_filter_before_pick = None
        # Set while _run_writes writes to the photos (input is blocked).
        self._input_blocker = None
        # Message boxes open right now (see show_message).
        self._open_messages: list[QMessageBox] = []
        self._last_status_message = ""
        self._last_status_tone = "info"
        self._status_undo_link = False
        self.gps_history = GpsEditHistory()

        # Photo grid state: Show filter ("all", "needs", "has") and the items.
        self._grid_filter = "all"
        # "Only Show Selected Photos": the paths shown while it is on, or None.
        self._only_selected_paths = None
        # Picking a location turns it off for a moment; turn it back on after.
        self._only_selected_before_pick = False
        self._grid_items_by_path = {}
        self._group_header_items = []
        # The Add Photos picker's "Add Photos in Subfolders": off at start,
        # then as last left until the app closes (not saved between sessions).
        self._picker_include_subfolders = False

        # Background loading state (see PhotoListMixin.load_photos and
        # _start_thumbnail_job). Generation numbers let late results from a
        # cancelled or replaced load be recognized and ignored.
        self.background = BackgroundRunner()
        self.thumbnail_batch_size = THUMBNAIL_BATCH_SIZE
        self._gps_load_generation = 0
        self._gps_load_token = None
        self._thumbnail_generation = 0
        self._thumbnail_token = None
        self._thumbnail_total = 0
        self._pending_thumbnail_items = {}
        self._blank_icon = None
        # The update check's state (see UpdateCheckMixin); it checks nothing yet.
        self._init_update_check()

        self._build_ui()
        self._build_menu_bar()
        self._build_loading_timers()

        # Esc leaves pick mode (From a Photo in the Photo List; only active while picking).
        self._pick_escape_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self._pick_escape_shortcut.setEnabled(False)
        self._pick_escape_shortcut.activated.connect(self.stop_picking_location)
        self._apply_window_style()
        # The Paste button follows the clipboard: read once now, then again
        # a moment after each change (see LocationEditorMixin).
        self._clipboard_has_coordinates = False
        self._clipboard_is_stale = True
        self._clipboard_check_retries = 0
        self._clipboard_check_timer = QTimer(self)
        self._clipboard_check_timer.setSingleShot(True)
        self._clipboard_check_timer.timeout.connect(self._refresh_clipboard_state)
        self._clipboard = self.clipboard()
        self._clipboard.dataChanged.connect(self._handle_clipboard_change)
        self._apply_backup_setting()
        self._apply_grid_filter()
        self.update_details_panel()
        self._refresh_clipboard_state()

    def _build_ui(self) -> None:
        central_widget = QWidget()
        central_widget.setObjectName("centralSurface")
        self.setCentralWidget(central_widget)

        outer_layout = QVBoxLayout(central_widget)
        outer_layout.setContentsMargins(10, 10, 10, 10)
        outer_layout.setSpacing(12)

        # "Version X is available": hidden until a newer release is found.
        outer_layout.addWidget(self._build_update_banner())

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(8)
        splitter.addWidget(build_browser_panel(self))
        splitter.addWidget(build_editor_panel(self))
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([900, 540])

        outer_layout.addWidget(splitter, 1)

    def _build_menu_bar(self) -> None:
        file_menu = self.menuBar().addMenu("&File")

        self.open_action = QAction("Add Photos...", self)
        self.open_action.setShortcuts(QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self.add_photos)
        file_menu.addAction(self.open_action)

        # Geotagging from a GPS track lives only here (see GeotaggerMixin).
        self.geotag_action = QAction("Geotag from GPS Track...", self)
        self.geotag_action.setShortcut(QKeySequence("Ctrl+G"))
        self.geotag_action.triggered.connect(self.geotag_from_track)
        file_menu.addAction(self.geotag_action)
        self._update_geotag_action(0)
        # Menu items show their hover hints (the greyed-out Geotag item says why).
        file_menu.setToolTipsVisible(True)

        self.clear_list_action = QAction("Clear List", self)
        self.clear_list_action.setEnabled(False)
        self.clear_list_action.triggered.connect(self.clear_photo_list)
        file_menu.addAction(self.clear_list_action)

        file_menu.addSeparator()

        self.exit_action = QAction("Exit", self)
        self.exit_action.setShortcuts(QKeySequence.StandardKey.Quit)
        self.exit_action.triggered.connect(self.close)
        file_menu.addAction(self.exit_action)

        edit_menu = self.menuBar().addMenu("&Edit")

        self.undo_action = QAction("Undo", self)
        self.undo_action.setShortcuts(QKeySequence.StandardKey.Undo)
        self.undo_action.setEnabled(False)
        self.undo_action.triggered.connect(self.undo_gps_edit)
        edit_menu.addAction(self.undo_action)

        self.redo_action = QAction("Redo", self)
        self.redo_action.setShortcuts(QKeySequence.StandardKey.Redo)
        self.redo_action.setEnabled(False)
        self.redo_action.triggered.connect(self.redo_gps_edit)
        edit_menu.addAction(self.redo_action)

        edit_menu.addSeparator()

        self.select_all_action = QAction("Select All Photos", self)
        self.select_all_action.setEnabled(False)
        self.select_all_action.triggered.connect(self.select_all_photos)
        edit_menu.addAction(self.select_all_action)

        edit_menu.addSeparator()

        self.copy_action = QAction("Copy GPS Coordinates", self)
        self.copy_action.setEnabled(False)
        self.copy_action.triggered.connect(self.copy_selected_photo_gps_coordinates)
        edit_menu.addAction(self.copy_action)

        self.paste_action = QAction("Paste Coordinates", self)
        self.paste_action.setEnabled(False)
        self.paste_action.triggered.connect(self.paste_coordinates_from_clipboard)
        edit_menu.addAction(self.paste_action)

        edit_menu.addSeparator()

        # Backups and the Esri key. On macOS Qt moves it to the app menu.
        self.settings_action = QAction("Settings...", self)
        self.settings_action.setMenuRole(QAction.MenuRole.PreferencesRole)
        # Ctrl+, (Cmd+, on macOS). Qt's standard Preferences key is the
        # "Settings" media key on Linux, which showed as "Settings Settings".
        self.settings_action.setShortcut(QKeySequence("Ctrl+,"))
        self.settings_action.triggered.connect(self.open_settings)
        edit_menu.addAction(self.settings_action)

        help_menu = self.menuBar().addMenu("&Help")

        self._build_update_menu(help_menu)

        self.about_action = QAction("About", self)
        self.about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(self.about_action)

    def _build_loading_timers(self) -> None:
        # Shows placeholder tiles if thumbnails are not ready quickly.
        self._placeholder_timer = QTimer(self)
        self._placeholder_timer.setSingleShot(True)
        self._placeholder_timer.timeout.connect(self._show_thumbnail_placeholders)

        # Drives the shimmer animation while placeholders are shown.
        self._shimmer_timer = QTimer(self)
        self._shimmer_timer.timeout.connect(self._advance_shimmer)
        self._shimmer_clock = QElapsedTimer()

    def closeEvent(self, event) -> None:
        if self._input_blocker is not None:
            # Writing to the photos: closing now could leave a change half done.
            event.ignore()
            return
        settings_dialog = getattr(self, "_settings_dialog", None)
        if settings_dialog is not None and settings_dialog.isVisible():
            settings_dialog.reject()
        self._cancel_update_download()
        self._close_map_window()
        self._close_geotag_window()
        self.stop_background_work()
        super().closeEvent(event)

    def stop_background_work(self) -> None:
        """
        Stop background loading and wait for the batch in progress, so no
        background work is still using Qt when the app shuts down.
        """
        self.cancel_loading(update_indicator=False)
        self.background.shutdown()

    def _apply_window_style(self) -> None:
        self.setStyleSheet(APP_STYLESHEET)

        # Clears an action message from the status row after a while.
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(self._clear_status_message)

    def _set_status_message(self, message: str, tone: str = "info", *, undo: bool = False) -> None:
        """
        Show a message in the status row under the grid.

        Args:
            message:
                What happened, for example "Applied GPS to 3 photos."
            tone:
                "success", "error", or "info"; sets the color.
            undo:
                True to add an Undo link after the message.
        """
        self._last_status_message = message
        self._last_status_tone = tone
        self._status_undo_link = undo
        self._status_timer.start(STATUS_MESSAGE_MS)
        self._update_status_row()

    def _clear_status_message(self) -> None:
        self._last_status_message = ""
        self._last_status_tone = "info"
        self._status_undo_link = False
        self._update_status_row()

    def _handle_status_link(self, link: str) -> None:
        if link == "undo":
            self.undo_gps_edit()

    def _update_status_row(self) -> None:
        """
        Show the latest action message under the grid. The row is hidden
        when there is no message and nothing is loading.
        """
        text = ""
        tone = "info"
        if self._last_status_message:
            text = html.escape(self._last_status_message, quote=False)
            if self._status_undo_link and self.gps_history.can_undo:
                text += '&nbsp;&nbsp;<a href="undo">Undo</a>'
            tone = self._last_status_tone

        self.browser_hint.setText(text)
        if self.browser_hint.property("tone") != tone:
            self.browser_hint.setProperty("tone", tone)
            self.browser_hint.style().unpolish(self.browser_hint)
            self.browser_hint.style().polish(self.browser_hint)
        self.loading_indicator.setVisible(bool(text) or self.loading_indicator.is_showing)

    def _update_selection_metrics(self) -> None:
        loaded_count = len(self.session.selected_paths)
        selected_count = len(self.get_selected_paths())
        gps_count = sum(1 for item in self.session.thumbnail_items if item.has_gps)
        needs_gps_count = max(0, loaded_count - gps_count)

        self._update_status_row()
        for key, label, count in (
            ("all", "All", loaded_count),
            ("needs", "Needs GPS", needs_gps_count),
            ("has", "Has GPS", gps_count),
        ):
            self.grid_filter_buttons[key].setText(f"{label} ({count})")

        # Selection bar: orange once something is selected.
        has_selection = selected_count > 0
        self.selection_count_label.setText(f"{selected_count} selected")
        if self.selection_bar.property("active") != has_selection:
            self.selection_bar.setProperty("active", has_selection)
            for widget in [self.selection_bar, *self.selection_bar.findChildren(QWidget)]:
                self._repolish(widget)
        visible_unselected = any(
            not item.isHidden() and not item.isSelected() for item in self._photo_items()
        )
        self.select_all_button.setEnabled(visible_unselected and not self.is_only_selected)

        # Only Show Selected Photos: can be turned on with a selection, and
        # off at any time. It switches itself off if the list is emptied.
        if self.is_only_selected and not self._grid_items_by_path:
            self.set_only_selected(False)
            return
        self._refresh_faded_marks()
        self.only_selected_button.setEnabled(self.is_only_selected or has_selection)
        self.only_selected_button.setToolTip(
            "Show every photo again"
            if self.is_only_selected
            else "Show only the selected photos, to check them before changing them"
            if has_selection
            else "Select photos first"
        )
        self.deselect_all_button.setEnabled(has_selection)
        self.remove_from_list_button.setEnabled(has_selection)

        self._update_pick_button()
        self._refresh_camera_checkboxes()
        self.clear_list_button.setEnabled(loaded_count > 0)
        if hasattr(self, "select_all_action"):
            self.select_all_action.setEnabled(loaded_count > 0)
        if hasattr(self, "clear_list_action"):
            self.clear_list_action.setEnabled(loaded_count > 0)
            self._update_geotag_action(loaded_count)
        if hasattr(self, "copy_action"):
            self.copy_action.setEnabled(self._selected_browser_gps_coordinates() is not None)
        self._update_undo_redo_actions()

    def _gps_states_for_paths(
        self,
        paths: list[Path],
    ) -> dict[Path, tuple[float | None, float | None]]:
        states: dict[Path, tuple] = {}
        for path in paths:
            info = self.session.loaded_photo_infos.get(path)
            if info is None or info.current_latitude is None or info.current_longitude is None:
                states[path] = (None, None)
            else:
                # With the altitude (None for none), so undo puts it back or clears it.
                states[path] = (info.current_latitude, info.current_longitude, info.current_altitude)
        return states

    def _remember_gps_edit(
        self,
        *,
        before_states: dict[Path, tuple[float | None, float | None]],
        after_states: dict[Path, tuple[float | None, float | None]],
        backups: list[Path] | None = None,
        kind: str = EDIT_GPS,
    ) -> None:
        self.gps_history.record(
            before=before_states,
            after=after_states,
            backups=tuple(backups or ()),
            kind=kind,
            photo_list=PhotoListSnapshot(
                paths=tuple(self.session.selected_paths),
                selected=tuple(self.get_selected_paths()),
            ),
        )
        self._update_undo_redo_actions()

    def _clear_gps_edit_history(self) -> None:
        self.gps_history.clear()
        self._update_undo_redo_actions()

    def _update_undo_redo_actions(self) -> None:
        if hasattr(self, "undo_action"):
            self.undo_action.setEnabled(self.gps_history.can_undo)
        if hasattr(self, "redo_action"):
            self.redo_action.setEnabled(self.gps_history.can_redo)
        self._apply_pick_mode_lock()

    def undo_gps_edit(self) -> None:
        states = self.gps_history.undo_states()
        if not states:
            return

        what = "date" if self.gps_history.kind == EDIT_DATE else "GPS"

        def done(failed_paths: list[str], _backups: list[Path]) -> None:
            failed_paths += self._delete_backups(self.gps_history.backups)
            self.gps_history.mark_undone()
            self._update_undo_redo_actions()
            self._report_write_failures(f"undo the {what} change for", failed_paths)
            self._set_status_message(f"{what[0].upper()}{what[1:]} change undone.", "info")

        # Undo puts the photos back: it never backs up the version it's undoing.
        self._restore_edit_states(states, f"Undoing the {what} change", done, make_backups=False)

    def redo_gps_edit(self) -> None:
        states = self.gps_history.redo_states()
        if not states:
            return

        what = "date" if self.gps_history.kind == EDIT_DATE else "GPS"

        def done(failed_paths: list[str], backups: list[Path]) -> None:
            # Redo made the backups again: the next undo deletes these.
            self.gps_history.set_backups(tuple(backups))
            self.gps_history.mark_redone()
            self._update_undo_redo_actions()
            self._report_write_failures(f"redo the {what} change for", failed_paths)
            self._set_status_message(f"{what[0].upper()}{what[1:]} change redone.", "info")

        self._restore_edit_states(states, f"Redoing the {what} change", done)

    def _restore_edit_states(self, states: dict, text: str, on_done, *, make_backups: bool = True) -> None:
        """
        Write the remembered states back, GPS or dates (see gps_history.kind),
        then on_done(failure messages, backups made). make_backups False:
        no backup copies even with Keep Backup Copies of Originals on (undo).
        """
        if self.gps_history.kind == EDIT_DATE:
            self._restore_date_states(states, text, on_done, make_backups=make_backups)
        else:
            self._restore_gps_states(states, text, on_done, make_backups=make_backups)

    def _restore_gps_states(
        self,
        states: dict[Path, tuple[float | None, float | None]],
        text: str,
        on_done,
        *,
        make_backups: bool = True,
    ) -> None:
        self._restore_states(
            text,
            len(states),
            lambda progress: self.workflow.restore_gps_states_workflow(
                session=self.session,
                states=states,
                on_progress=progress,
            ),
            on_done,
            make_backups=make_backups,
        )

    def _restore_states(self, text: str, total: int, write, on_done, *, make_backups: bool = True) -> None:
        """
        Write remembered states back to files in the background (write does
        it; see _run_writes), and put the photo list back the way it was
        when the edit was made. Then on_done(failure messages, the backups
        the writes made).

        make_backups False (undo): no backup copies even with Keep Backup
        Copies of Originals on. Otherwise undoing a location added to a photo
        without GPS "backed up" the location being removed.
        """
        if not make_backups:
            write = self._without_backups(write)
        # A load still running would replace the list put back here.
        self.cancel_loading()
        snapshot = self.gps_history.photo_list
        if snapshot is not None:
            # Photos moved or deleted since then can't come back.
            self.session.selected_paths = [path for path in snapshot.paths if path.exists()]
            kept = set(self.session.selected_paths)
            self.session.target_paths = [
                path for path in self.session.target_paths if path in kept
            ]

        def done(result) -> None:
            self.session = result.session
            self._render_current_photo_session()
            if snapshot is not None:
                self.select_browser_paths(list(snapshot.selected))
            else:
                self.list_widget.clearSelection()
                self.update_details_panel()
            on_done(list(result.execution_result.failed_paths), self._take_new_backups())

        self._run_writes(text, total, write, done)

    def _without_backups(self, write):
        """
        write with the writer's backups switched off while it runs (on the
        background thread), then switched back. Input is blocked meanwhile
        (see _run_writes), so Settings can't change the option at the same
        time.
        """
        writer = self.workflow.writer

        def run(progress):
            keep = getattr(writer, "keep_backups", False)
            writer.keep_backups = False
            try:
                return write(progress)
            finally:
                writer.keep_backups = keep

        return run

    def _run_writes(self, text: str, total: int, write, on_done) -> None:
        """
        Write to the photos in the background (writing to many photos, or
        photos on a network share, can take a while), with a progress bar
        under the Photo List ("Changing dates… 37 of 114") and the window
        ignoring clicks and keys until it's done.

        Args:
            text:
                What is happening, e.g. "Changing dates".
            total:
                How many photos are written.
            write:
                write(on_progress) does the writes on the background thread
                and returns the workflow result; on_progress(done, total)
                is called after each photo.
            on_done:
                on_done(result) runs on the GUI thread when it's finished.
        """
        # A load still running would use ExifTool at the same time.
        self.cancel_loading(update_indicator=False)
        self._input_blocker = InputBlocker(self)
        QApplication.instance().installEventFilter(self._input_blocker)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.loading_indicator.begin(f"{text}… 0 of {total}", total, cancellable=False)

        def progress(done: int, count: int) -> None:
            # Called on the background thread: the bar updates on the GUI thread.
            self.background.post(
                lambda value: self.loading_indicator.set_progress(*value, f"{text}… {value[0]} of {value[1]}"),
                (done, count),
            )

        def finished(result) -> None:
            self._end_writes()
            on_done(result)

        def failed(exc: BaseException) -> None:
            self._end_writes()
            dialog = QMessageBox(self)
            dialog.setIcon(QMessageBox.Warning)
            dialog.setWindowTitle("Could Not Change the Photos")
            dialog.setText(f"The change could not be finished:\n\n{exc}")
            dialog.setStandardButtons(QMessageBox.Ok)
            self.show_message(dialog)

        self.background.submit(lambda: write(progress), finished, failed)

    def _end_writes(self) -> None:
        if self._input_blocker is not None:
            QApplication.instance().removeEventFilter(self._input_blocker)
            self._input_blocker.deleteLater()
            self._input_blocker = None
            QApplication.restoreOverrideCursor()
        self.loading_indicator.finish()

    def _take_new_backups(self) -> list[Path]:
        """
        The backups ("<name>_original.<ext>") the last change just made.
        """
        take = getattr(self.workflow.writer, "take_created_backups", None)
        return take() if take is not None else []

    def _delete_backups(self, backups: tuple[Path, ...]) -> list[str]:
        """
        Undo: delete the backups the undone change made (the photos have
        their earlier GPS back, so the copies aren't needed). Backups never
        join the Photo List (a copy at the old location next to the moved
        photo looked like the photo hadn't moved); they stay in the folder
        for whoever needs them. Returns failure messages.
        """
        failed = []
        for backup in backups:
            try:
                backup.unlink(missing_ok=True)
            except OSError as exc:
                failed.append(f"{backup.name}: could not delete the backup ({exc})")
        return failed

    def _report_write_failures(self, action: str, failed_paths: list[str]) -> None:
        """
        Tell the user which files could not be changed, if any.

        Args:
            action:
                Completes the sentence "Could not <action> N photo(s).",
                for example "apply GPS to".
            failed_paths:
                One "file name: reason" entry per failed file.
        """
        if not failed_paths:
            return

        self._set_status_message(
            f"Could not {action} {len(failed_paths)} photo(s).",
            "error",
        )
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Warning)
        dialog.setWindowTitle("Some Photos Were Not Changed")
        dialog.setText(f"Could not {action} {len(failed_paths)} photo(s).")
        dialog.setInformativeText(
            "The other photos were changed. Show Details lists each file and the reason."
        )
        dialog.setDetailedText("\n".join(failed_paths))
        dialog.setStandardButtons(QMessageBox.Ok)
        self.show_message(dialog)

    def show_message(
        self,
        dialog: QMessageBox,
        on_closed: Callable[[QAbstractButton | None], None] | None = None,
    ) -> None:
        """
        Show a message box without blocking: modal (the rest of the app waits
        for it), but shown with show(), not exec(). exec() runs a second event
        loop inside the code that opened it, and background results arriving
        inside that loop crashed the Windows build.

        on_closed(button) runs when it closes, with the button clicked (None
        if it was closed another way).
        """
        # Kept until it closes, so Python doesn't delete it while it's open.
        self._open_messages.append(dialog)

        def closed(_result: int) -> None:
            if dialog in self._open_messages:
                self._open_messages.remove(dialog)
            if on_closed is not None:
                on_closed(dialog.clickedButton())

        dialog.finished.connect(closed)
        # Application-modal and show(), not open(): open() makes it a sheet
        # on macOS (see _open_photo_picker).
        dialog.setWindowModality(Qt.ApplicationModal)
        dialog.show()

    def open_settings(self) -> None:
        """
        Open Edit > Settings. Modal like the picker, shown with show() (not
        a blocking exec()); Save applies the values when it closes.
        """
        dialog = SettingsDialog(
            self,
            keep_backups=self.keep_backups,
            esri_key=self.settings.value(ESRI_KEY_SETTING, "", type=str),
            check_updates=self.check_updates_on_start,
            use_feet=self.use_feet,
        )
        # Kept so tests (and late signals) find a live object.
        self._settings_dialog = dialog

        def closed(result: int) -> None:
            if result != QDialog.Accepted:
                return
            self.set_keep_backups(dialog.keep_backups())
            self.set_esri_key(dialog.esri_key())
            self.set_check_updates_on_start(dialog.check_updates())
            self.set_use_feet(dialog.use_feet())

        dialog.finished.connect(closed)
        dialog.setWindowModality(Qt.ApplicationModal)
        dialog.show()

    @property
    def use_feet(self) -> bool:
        """Altitudes in feet (the default) or metres (Edit > Settings)."""
        return self.settings.value(USE_FEET_SETTING, True, type=bool)

    def set_use_feet(self, use_feet: bool) -> None:
        self.settings.setValue(USE_FEET_SETTING, use_feet)
        # The Photo List's tile hints and the geotag window show altitudes.
        if self.session.selected_paths:
            self._rerender_selecting(self.get_selected_paths())
        self._geotag_photos_changed()

    @property
    def keep_backups(self) -> bool:
        return self.settings.value(KEEP_BACKUPS_SETTING, False, type=bool)

    def set_keep_backups(self, keep_backups: bool) -> None:
        """
        Turn backup copies on or off, and remember the choice.
        """
        self.settings.setValue(KEEP_BACKUPS_SETTING, keep_backups)
        self._apply_backup_setting()

    def _apply_backup_setting(self) -> None:
        # The writer is ExifToolWrapper in the app; test fakes simply ignore it.
        self.workflow.writer.keep_backups = self.keep_backups

    def _default_photo_directory(self) -> Path:
        """
        The user's Pictures folder, as the operating system knows it.

        Asking the system matters: Windows lets "My Pictures" be moved (for
        example to OneDrive or another drive), which leaves an empty
        C:\\Users\\<name>\\Pictures behind. Linux desktops can rename it too.
        """
        system_pictures = QStandardPaths.writableLocation(QStandardPaths.PicturesLocation)
        for candidate in (system_pictures, str(Path.home() / "Pictures")):
            if candidate and Path(candidate).is_dir():
                return Path(candidate)
        return Path.home()

    def _pick_photo_files(self, title: str, on_chosen: Callable[[list[Path]], None]) -> None:
        """
        Choose photos to add with the app's own picker (folder tree on the
        left; folders and photos on the right). The system pickers mix
        folders and photos, and on Linux choosing both at once silently does
        nothing.

        on_chosen(paths) runs after the picker closes with photos chosen.
        For folders chosen, their photos are found first (see
        _add_photos_from_folders) and included in paths.
        """
        self._open_photo_picker(title, single=False, on_chosen=on_chosen)

    def _pick_photo_file(
        self,
        title: str,
        on_chosen: Callable[[Path], None],
        *,
        blocked: set[Path] | None = None,
    ) -> None:
        """
        Choose one photo (to use its location) with the app's picker.
        on_chosen(path) runs after the picker closes with a photo chosen.
        blocked: photos that can't be chosen ("Being Changed").
        """
        self._open_photo_picker(
            title,
            single=True,
            on_chosen=lambda paths: on_chosen(paths[0]),
            blocked=blocked,
        )

    def _open_photo_picker(
        self,
        title: str,
        *,
        single: bool,
        on_chosen: Callable[[list[Path]], None],
        blocked: set[Path] | None = None,
    ) -> None:
        """
        Show the picker without blocking the code: it is modal, but the app
        keeps running its one event loop. A blocking exec() ran a second event loop
        inside the button's click, and the Windows build crashed when
        background results arrived inside it.
        """
        dialog = PhotoPickerDialog(
            self,
            title=title,
            start_folder=self._photo_picker_start_folder(),
            in_list=set(self.session.selected_paths),
            workflow=self.workflow,
            thumbnail_loader=self.thumbnail_loader,
            background=self.background,
            single=single,
            include_subfolders=self._picker_include_subfolders,
            blocked=blocked,
        )
        # Kept until the next picker opens, so background results that arrive
        # after it closes still find a live (ignored) object.
        self._photo_picker = dialog

        def closed(result: int) -> None:
            if dialog.current_folder is not None:
                self._remember_photo_folder(dialog.current_folder)
            if not single:
                self._picker_include_subfolders = dialog.include_subfolders()
            paths = dialog.selected_paths()
            folders = [] if single else dialog.selected_folders()
            if result != QDialog.Accepted or not (paths or folders):
                return
            if folders:
                self._add_photos_from_folders(
                    paths, folders, dialog.include_subfolders(), on_chosen
                )
            else:
                on_chosen(paths)

        dialog.finished.connect(closed)
        # Application-modal and shown with show(), not open(): open() makes
        # it a sheet on macOS (stuck to the main window's title bar). This
        # is a normal window on every system that blocks the rest of the app.
        dialog.setWindowModality(Qt.ApplicationModal)
        dialog.show()

    def _add_photos_from_folders(
        self,
        photos: list[Path],
        folders: list[Path],
        recursive: bool,
        on_chosen: Callable[[list[Path]], None],
    ) -> None:
        """
        Find the photos in the folders chosen in the picker (in the
        background: a big folder tree on a network share takes a while),
        then pass them, after the photos chosen one by one, to on_chosen.
        """
        self._set_status_message("Reading folders…", "info")

        def work() -> list[Path]:
            return photos_in_folders(folders, recursive=recursive)

        def done(found: list[Path]) -> None:
            if not photos and not found:
                self._set_status_message(
                    "No photos found in "
                    + ("that folder." if len(folders) == 1 else "those folders."),
                    "info",
                )
                return
            on_chosen([*photos, *found])

        def failed(exc: BaseException) -> None:
            self._set_status_message(f"The folders could not be read: {exc}", "error")

        self.background.submit(work, done, failed)

    def _photo_picker_start_folder(self) -> Path:
        """
        Where the file pickers open: the last folder photos were chosen from,
        or the Pictures folder the first time (or if that folder is gone).
        """
        last_folder = self.settings.value(LAST_PHOTO_FOLDER_SETTING, "", type=str)
        if last_folder and Path(last_folder).is_dir():
            return Path(last_folder)
        return self._default_photo_directory()

    def _remember_photo_folder(self, folder: Path) -> None:
        self.settings.setValue(LAST_PHOTO_FOLDER_SETTING, str(folder))

    def _format_overwrite_entries(
        self,
        overwrite_entries: list[OverwriteEntry],
    ) -> list[str]:
        return [entry.display_text() for entry in overwrite_entries]

    def show_about_dialog(self) -> None:
        self.show_message(self._build_about_dialog())

    def _build_about_dialog(self) -> QMessageBox:
        repo_url = "https://github.com/Petruchio96/fotofixer"
        about_dialog = QMessageBox(self)
        about_dialog.setWindowTitle(f"About {APP_NAME} {APP_VERSION}")
        about_dialog.setIconPixmap(
            QIcon(str(resource_path("assets/app_icon_128.png"))).pixmap(64, 64)
        )
        about_dialog.setStandardButtons(QMessageBox.Ok)

        link_label = QLabel(
            (
                f"<p><strong>{APP_NAME} – {APP_SUBTITLE}</strong><br>Version {APP_VERSION}</p>"
                "<p>Fixes where and when photos were taken: the GPS location and the "
                "date, time, and time zone of photos from cameras and phones.</p>"
                "<p>Formerly Photo GPS Editor.</p>"
                "<p>Instructions and more information:<br>"
                f'<a href="{repo_url}">{repo_url}</a></p>'
            )
        )
        link_label.setObjectName("aboutRepositoryLink")
        link_label.setTextFormat(Qt.RichText)
        link_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        link_label.setOpenExternalLinks(True)
        link_label.setWordWrap(True)
        link_label.setMinimumWidth(360)

        about_dialog.layout().addWidget(
            link_label,
            0,
            1,
            1,
            about_dialog.layout().columnCount(),
        )
        about_dialog.setMinimumWidth(520)
        return about_dialog

    def clipboard(self):
        return QApplication.clipboard()
