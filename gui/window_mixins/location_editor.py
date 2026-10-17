"""
The New Location fields in the inspector panel.

Two separate jobs, kept visually separate:
    - The photos selected in the grid are the photos to change.
    - The New Location is where their new coordinates come from: typed,
      pasted, read from a photo file ("From a Photo on Your Computer"), or
      copied from a photo in the Photo List with "From a Photo in the Photo
      List" or the right-click menu.
      Picking never changes the selection.

When the location came from a photo, that photo is the "location source":
the New Location box shows it on a blue card and the grid marks it in blue.
Whatever is in the fields is what Apply writes to the selected photos.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QLineEdit, QListWidgetItem, QMessageBox

from core.models import GpsCoordinates
from gui.presenters.inspector_state import format_coordinates
from gui.widgets.editor_panel import COORDINATE_FIELD_TIP, PICK_BUTTON_TEXT, PICK_BUTTON_TIP, PICK_TIME_BUTTON_TEXT
from gui.widgets.thumbnail_delegate import PICK_DISABLED_ROLE, SOURCE_ROLE
from gui.window_mixins.photo_list import THUMBNAIL_LATITUDE_ROLE
from services.coordinate_service import (
    parse_coordinate_text,
    parse_latitude_text,
    parse_longitude_text,
    parse_manual_coordinates,
)

PICK_PROMPT = (
    "Click a photo on the left to copy its location. "
    "Only photos with GPS can be picked. Press Esc or Cancel to stop."
)

# How long after the clipboard changes the Paste button re-checks it, and how
# many times it tries again when another program still has the clipboard open.
CLIPBOARD_CHECK_DELAY_MS = 250
CLIPBOARD_CHECK_RETRIES = 8


def clipboard_is_busy() -> bool:
    """
    True when another program has the Windows clipboard open right now.

    Windows announces a clipboard change the moment the writer closes it, but
    clipboard managers and programs that add several formats re-open it
    straight away. Reading it then makes Qt retry and log "Retrying to obtain
    clipboard" (and it may read nothing). Opening and closing it ourselves is
    a silent probe: it fails only while someone else holds it. Other
    platforms have no such lock.
    """
    if sys.platform != "win32":
        return False
    import ctypes

    user32 = ctypes.windll.user32
    if not user32.OpenClipboard(None):
        return True
    user32.CloseClipboard()
    return False


class LocationEditorMixin:
    def set_location_fields(
        self,
        latitude: str,
        longitude: str,
        *,
        source: Path | None = None,
    ) -> None:
        """
        Fill both fields, without the auto-split of pasted pairs kicking in.

        Args:
            source:
                The photo the coordinates came from, or None if they did not
                come from a photo (typed, pasted, cleared).
        """
        self._is_splitting_manual_coordinates = True
        try:
            self.latitude_input.setText(latitude)
            self.longitude_input.setText(longitude)
        finally:
            self._is_splitting_manual_coordinates = False
        self.set_input_error_state(self.latitude_input, False)
        self.set_input_error_state(self.longitude_input, False)
        self._set_location_source(source)
        self.update_details_panel()

    def clear_location_fields(self) -> None:
        self.set_location_fields("", "")

    def use_location_from_path(self, path: Path) -> bool:
        """
        Make a loaded photo the location source. Returns False if it has no GPS.
        """
        info = self.session.loaded_photo_infos.get(path)
        if info is None or info.current_latitude is None or info.current_longitude is None:
            return False

        self.set_location_fields(
            f"{info.current_latitude:.6f}",
            f"{info.current_longitude:.6f}",
            source=path,
        )
        self._location_source_altitude = info.current_altitude
        self._set_status_message(
            f"Using the location from {path.name}. "
            "Now select the photos to change and click Apply.",
            "success",
        )
        return True

    def choose_location_from_photo(self) -> None:
        """
        Choose any photo file to use its location (see use_location_from_file).
        """
        self._pick_photo_file("Use the Location from a Photo", self.use_location_from_file)

    def use_location_from_file(self, path: Path) -> None:
        """
        Read the GPS coordinates of a photo file into New Location. (The
        picker doesn't offer photos selected to change.)
        """
        info = self.workflow.read_photo_info(path)
        if info.gps_error:
            dialog = QMessageBox(self)
            dialog.setIcon(QMessageBox.Warning)
            dialog.setWindowTitle("Could Not Read Photo")
            dialog.setText(f"Could not read GPS from {path.name}:\n{info.gps_error}")
            dialog.setStandardButtons(QMessageBox.Ok)
            self.show_message(dialog)
            return
        if info.current_latitude is None or info.current_longitude is None:
            # No GPS, or only half of it (latitude without longitude, or the
            # reverse): nothing usable to copy.
            self._show_no_gps_message()
            return

        self.set_location_fields(
            f"{info.current_latitude:.6f}",
            f"{info.current_longitude:.6f}",
            source=path,
        )
        self._location_source_altitude = info.current_altitude
        self._set_status_message(
            f"Using the location from {path.name}: "
            f"{format_coordinates(GpsCoordinates(info.current_latitude, info.current_longitude))}.",
            "success",
        )

    def _show_no_gps_message(self) -> None:
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Information)
        dialog.setWindowTitle("No GPS Coordinates")
        dialog.setText("Selected Photo has no GPS Coordinates")
        dialog.setStandardButtons(QMessageBox.Ok)
        self.show_message(dialog)

    # --- From a Photo in the Photo List (pick mode) ---------------------------

    @property
    def is_picking_location(self) -> bool:
        return self._picking_location

    def toggle_picking_location(self, checked: bool = False) -> None:
        if self._picking_location:
            self.stop_picking_location()
        else:
            self.start_picking_location()

    def start_picking_location(self) -> None:
        """
        Enter pick mode: the next click on a photo with GPS copies its location.

        While picking, the grid shows Has GPS (the photos that can be
        picked), and everything is disabled except Add Photos, Clear List,
        and this button (which reads "Cancel"). A selected photo can be
        picked too: it becomes the source and is deselected. Picking ends
        back on the view used before.
        """
        if not self._photos_with_gps_count():
            return
        self._pick_kind = "location"
        # Only Show Selected Photos steps aside while picking, then comes back.
        self._only_selected_before_pick = self.is_only_selected
        if self._only_selected_before_pick:
            self.set_only_selected(False)
        self._picking_location = True
        # Remember the Show filter, to put it back when picking ends.
        self._filter_before_pick = self._grid_filter
        self._apply_pick_filter_rules()

        self.pick_location_button.setChecked(True)
        self.pick_location_button.setText("Cancel")
        self.pick_banner_label.setText(PICK_PROMPT)
        self.pick_banner.show()
        self.list_widget.viewport().setCursor(Qt.CrossCursor)
        self._pick_escape_shortcut.setEnabled(True)
        self._refresh_pick_marks()
        self._apply_pick_mode_lock()

    def stop_picking_location(self) -> None:
        """
        Leave pick mode, whichever tab started it (a location or, on the
        Date & Time tab, a time; see DateTimeEditorMixin.start_picking_time).
        """
        self._picking_location = False
        self._pick_kind = "location"
        self.pick_location_button.setChecked(False)
        self.pick_location_button.setText(PICK_BUTTON_TEXT)
        self.pick_time_button.setChecked(False)
        self.pick_time_button.setText(PICK_TIME_BUTTON_TEXT)
        self.pick_banner.hide()
        self.list_widget.viewport().unsetCursor()
        self._pick_escape_shortcut.setEnabled(False)
        self._refresh_pick_marks()
        # Controls that are normally always on: turn them back on. The rest
        # get their normal state recomputed by update_details_panel().
        for widget in (
            self.latitude_input,
            self.longitude_input,
            self.location_from_photo_button,
            self.show_map_button,
            self.source_card_clear,
            *self.grid_filter_buttons.values(),
            *self.camera_filter_buttons.values(),
        ):
            widget.setEnabled(True)
        if self._map_window is not None:
            self._map_window.setEnabled(True)
        self._set_camera_checkboxes_enabled(True)

        # Back to the Show filter used before picking, ready to select the
        # photos to change.
        previous_filter = self._filter_before_pick or self._grid_filter
        self._filter_before_pick = None
        if previous_filter != self._grid_filter:
            self.set_grid_filter(previous_filter)
        else:
            self._apply_grid_filter()
        if self._only_selected_before_pick:
            self._only_selected_before_pick = False
            if self.get_selected_paths():
                self.set_only_selected(True)
        # Picking a time showed every camera: back to the camera shown before
        # (unless its photos were removed meanwhile).
        previous_camera = self._camera_filter_before_pick
        self._camera_filter_before_pick = None
        if (
            previous_camera is not None
            and previous_camera != self._camera_filter
            and previous_camera in self.camera_filter_buttons
        ):
            self.set_camera_filter(previous_camera)
        self.update_details_panel()

    def pick_location_from_item(self, item: QListWidgetItem | None) -> None:
        """
        Called for a click on the grid while picking.
        """
        if item is None or item.data(PICK_DISABLED_ROLE):
            # Empty space, or a dimmed photo without GPS: nothing to pick.
            return
        path_text = item.data(Qt.UserRole)
        if path_text is None:
            # A group heading, not a photo.
            return

        if self._pick_kind == "time":
            if self.use_time_from_path(Path(path_text)):
                self.stop_picking_location()
            return
        if self.use_location_from_path(Path(path_text)):
            self.stop_picking_location()

    def _apply_pick_filter_rules(self) -> None:
        """
        While picking, show Has GPS: only photos with GPS can be picked.
        If no photo with GPS is left (Clear List, for example), stop picking.

        Runs when picking starts and whenever the photos change while picking.
        """
        if not self._picking_location:
            return
        if self._pick_kind == "time":
            # Any photo with a date that isn't being changed can be picked;
            # the view stays as it is.
            if not self._time_pickable_paths():
                self.stop_picking_location()
                return
            self._refresh_pick_marks()
            self._apply_pick_mode_lock()
            return
        if not self._photos_with_gps_count():
            self.stop_picking_location()
            return

        if self._grid_filter != "has":
            self.set_grid_filter("has")
        else:
            self._apply_grid_filter()
        self._apply_pick_mode_lock()

    def _photos_with_gps_count(self) -> int:
        """Photos that can be the location source: every photo with GPS (a selected one is deselected when picked)."""
        return sum(1 for item in self.session.thumbnail_items if item.has_gps)

    def _update_pick_button(self) -> None:
        """
        The pick button needs a photo with GPS in the list to copy from.
        While picking it is the Cancel button, so it stays on.
        """
        if self._picking_location:
            return
        can_pick = self._photos_with_gps_count() > 0
        self.pick_location_button.setEnabled(can_pick)
        self.pick_location_button.setToolTip(
            PICK_BUTTON_TIP
            if can_pick
            else "No photo in the Photo List has GPS coordinates to copy."
        )

    def _refresh_pick_marks(self) -> None:
        """
        Dim the photos that can't be picked while picking ("No GPS"; for a
        time "No Date" or "Being Changed"); clear the dimming otherwise. A
        selected photo can be picked as the location source: it is
        deselected when it becomes the source.
        """
        selected = set(self.get_selected_paths())
        for path_text, item in self._grid_items_by_path.items():
            if not self._picking_location:
                label = ""
            elif self._pick_kind == "time":
                label = self._time_pick_label(Path(path_text), selected)
            elif item.data(THUMBNAIL_LATITUDE_ROLE) is None:
                label = "No GPS"
            else:
                label = ""
            if (item.data(PICK_DISABLED_ROLE) or "") != label:
                item.setData(PICK_DISABLED_ROLE, label or None)

    def _apply_pick_mode_lock(self) -> None:
        """
        While picking, disable everything except the allowed controls.

        Called after anything that recomputes enabled states, so the lock
        stays in place (for example when Add Photos loads new photos).
        """
        if not self._picking_location:
            return

        for widget in (
            self.select_all_button,
            self.deselect_all_button,
            self.remove_from_list_button,
            self.only_selected_button,
            *self.grid_filter_buttons.values(),
            self.copy_location_button,
            self.latitude_input,
            self.longitude_input,
            self.paste_coordinates_button,
            self.location_from_photo_button,
            self.show_map_button,
            self.clear_location_button,
            self.source_card_clear,
            self.apply_button,
            self.remove_gps_button,
            *self.camera_filter_buttons.values(),
            self.date_shift_choice,
            self.date_set_choice,
            self.date_reference_picker,
            self.date_reference_back,
            self.date_reference_forward,
            self.time_from_photo_button,
            self.time_source_clear,
            self.date_set_picker,
            self.date_apply_button,
        ):
            widget.setEnabled(False)
        # The other tab's pick button: only the one that started picking
        # (now "Cancel") stays on.
        (self.pick_location_button if self._pick_kind == "time" else self.pick_time_button).setEnabled(False)
        self._set_camera_checkboxes_enabled(False)
        # The map is another way to set New Location: off while picking.
        if self._map_window is not None:
            self._map_window.setEnabled(False)

        for action_name in (
            "select_all_action",
            "copy_action",
            "paste_action",
            "undo_action",
            "redo_action",
        ):
            action = getattr(self, action_name, None)
            if action is not None:
                action.setEnabled(False)

    # --- Location source display ---------------------------------------------

    def _set_location_source(self, source: Path | None) -> None:
        self._location_source = source
        self._refresh_source_card()
        self._refresh_source_marker()

    def _refresh_source_card(self) -> None:
        source = self._location_source
        if source is None:
            self.source_card.hide()
            return

        self.source_card_title.setText(f"From {source.name}")
        location = parse_manual_coordinates(self.latitude_input.text(), self.longitude_input.text())
        self.source_card_detail.setText(
            format_coordinates(GpsCoordinates(*location)) if location else ""
        )
        item = self._grid_items_by_path.get(str(source))
        icon = item.icon() if item is not None else self.thumbnail_loader.load_icon(source, has_gps=True)
        self.source_card_thumbnail.setPixmap(icon.pixmap(52, 52))
        self.source_card.show()

    def _refresh_source_marker(self) -> None:
        """
        Mark the source photo in the grid (blue outline, SOURCE): where the
        location came from, or on the Date & Time tab, the time.

        On the Location tab a photo is either the source or being changed,
        never both: the location source can't be selected (and is
        deselected when it becomes the source). It's selectable again once
        it stops being the source (the source card's ✕, Clear, typed
        coordinates, or another photo as the source). The Date & Time tab
        keeps its own rules (its time source can be selected; Shift leaves
        it out).
        """
        source = self._time_source if self.is_date_mode else self._location_source
        source_text = str(source) if source else None
        blocked_text = None if self.is_date_mode or self._location_source is None else str(self._location_source)
        for path_text, item in self._grid_items_by_path.items():
            is_source = path_text == source_text
            if bool(item.data(SOURCE_ROLE)) != is_source:
                item.setData(SOURCE_ROLE, is_source)
            flags = item.flags()
            if path_text == blocked_text:
                if flags & Qt.ItemIsSelectable:
                    item.setSelected(False)
                    item.setFlags(flags & ~Qt.ItemIsSelectable)
            elif not flags & Qt.ItemIsSelectable:
                item.setFlags(flags | Qt.ItemIsSelectable)
                # It couldn't be selected until now: clear any selection Qt
                # kept for it while it was the source (it stays deselected).
                item.setSelected(False)

    def paste_coordinates_from_clipboard(self) -> None:
        clipboard_text = QApplication.clipboard().text().strip()
        parsed = self.parse_coordinate_text(clipboard_text)

        if parsed is None:
            # The remembered state was wrong (the clipboard changed while it
            # was busy, say), so read it again now.
            self._clipboard_is_stale = True
            self._refresh_clipboard_state()
            self._set_status_message(
                "The clipboard doesn't contain coordinates.",
                "error",
            )
            return

        latitude, longitude = parsed
        self.set_location_fields(latitude, longitude)

    def _handle_location_input_change(self, text: str) -> None:
        """
        Typing or pasting "40.5865, -111.6558" into either field splits it
        into the two fields automatically. Editing the fields by hand means
        the location no longer comes from the source photo.
        """
        if self._is_splitting_manual_coordinates:
            return

        parsed = self.parse_coordinate_text(text)
        if parsed is not None:
            self.set_location_fields(*parsed)
            return

        if self._location_source is not None:
            self._set_location_source(None)
        self.update_details_panel()

    def _handle_clipboard_change(self) -> None:
        """
        The clipboard changed (in this app or any other). Re-check it a
        moment later rather than now: the program that wrote it may still
        have it open (see clipboard_is_busy), and a burst of changes becomes
        one read.
        """
        self._clipboard_is_stale = True
        self._clipboard_check_retries = 0
        self._clipboard_check_timer.start(CLIPBOARD_CHECK_DELAY_MS)

    def _refresh_clipboard_state(self) -> None:
        """Read the clipboard once and remember whether it holds coordinates."""
        if not self._clipboard_is_stale:
            return
        if clipboard_is_busy():
            # Try again shortly; after enough tries, leave the last known state.
            if self._clipboard_check_retries < CLIPBOARD_CHECK_RETRIES:
                self._clipboard_check_retries += 1
                self._clipboard_check_timer.start(CLIPBOARD_CHECK_DELAY_MS)
            return
        self._clipboard_is_stale = False
        clipboard_text = QApplication.clipboard().text().strip()
        self._clipboard_has_coordinates = self.parse_coordinate_text(clipboard_text) is not None
        self._update_clipboard_buttons()

    def _update_clipboard_buttons(self) -> None:
        # Uses the remembered state: this runs on every inspector refresh,
        # and reading the clipboard each time is what collided with other
        # programs on Windows.
        can_paste_coordinates = self._clipboard_has_coordinates
        self.paste_coordinates_button.setEnabled(can_paste_coordinates)
        self.paste_coordinates_button.setToolTip(
            "Paste coordinates copied from a map or another photo"
            if can_paste_coordinates
            else "Copy coordinates (for example from a map) to paste them here"
        )
        if hasattr(self, "paste_action"):
            self.paste_action.setEnabled(can_paste_coordinates)
        self._apply_pick_mode_lock()

    def parse_coordinate_text(self, text: str) -> tuple[str, str] | None:
        return parse_coordinate_text(text)

    def set_input_error_state(self, field: QLineEdit, has_error: bool) -> None:
        if has_error:
            field.setStyleSheet(
                "QLineEdit {"
                "border: 1px solid #c62828;"
                "background-color: #fff5f5;"
                "}"
            )

            if field is self.latitude_input:
                field.setToolTip(
                    "Invalid latitude. Use decimal, DMS, or DDM within -90 to 90"
                )
            elif field is self.longitude_input:
                field.setToolTip(
                    "Invalid longitude. Use decimal, DMS, or DDM within -180 to 180"
                )
        else:
            field.setStyleSheet("")
            # Back to the usual hint (an empty one hid it after any valid edit).
            field.setToolTip(COORDINATE_FIELD_TIP)

    def validate_latitude_field(self) -> None:
        text = self.latitude_input.text().strip()

        if not text:
            self.set_input_error_state(self.latitude_input, False)
            return

        try:
            parse_latitude_text(text)
            self.set_input_error_state(self.latitude_input, False)
        except ValueError:
            self.set_input_error_state(self.latitude_input, True)

    def validate_longitude_field(self) -> None:
        text = self.longitude_input.text().strip()

        if not text:
            self.set_input_error_state(self.longitude_input, False)
            return

        try:
            parse_longitude_text(text)
            self.set_input_error_state(self.longitude_input, False)
        except ValueError:
            self.set_input_error_state(self.longitude_input, True)

