"""
The Date & Time tab: shift the selected photos' dates, set one date, or
change their time zone.

Shift (the main job): the camera's clock was off, so every selected photo is
off by the same amount. The tab shows a reference photo (the earliest
selected; the arrows choose another) and its current date. Enter its correct
date and time, or copy the time from a photo known to be right that was taken
at the same moment, and every selected photo moves by the same amount.

Set: every selected photo gets one date and time.

Change Time Zone: the photos get another time zone. Normally the moment they
were taken stays the same (the clock times change); "Keep the clock time"
keeps the clock times instead, which moves the moment (for photos whose times
were right but whose zone was wrong). Every change works on the moment a
photo was taken.

It works like the Location tab: the photo the correct time came from is the
"source" (blue card, SOURCE mark in the Photo List, never changed itself),
picking from the Photo List locks the other controls (Esc cancels), typing a
date drops the source, and after a change the photos are deselected and the
status row offers Undo. Date changes make no backup copies: undo writes back
the exact date tags read before.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QMessageBox, QTreeWidgetItem

from core.photo_dates import format_display_datetime
from core.time_zones import ZONES_BY_KEY, computer_utc_offset, offset_at_local, to_zone
from gui.presenters.date_time_state import (
    MODE_SET,
    MODE_SHIFT,
    MODE_ZONE,
    DateTimeState,
    build_date_time_state,
    describe_shift,
    keep_clock_message,
)
from gui.widgets.date_time_picker import fill_zone_box
from gui.widgets.editor_panel import CHANGE_ROW_ROLE, DATE_TIME_TAB, refresh_tab_icons
from services.date_time_service import date_tag_values, photo_instant, photos_by_date, saved_date_tags
from services.gps_edit_history import EDIT_DATE

# Change Time Zone's drop-down hint, when the selected photos have more than
# one time zone (it shows in red then).
MIXED_ZONES_CHANGE_TIP = (
    "The selected photos have more than one time zone. All of them will change "
    "to this time zone."
)

TIME_PICK_PROMPT = (
    "Click the photo taken at the same moment as {reference}. Its time becomes "
    "{reference}'s correct time. Press Esc or Cancel to stop."
)

# "Changing date to:" colors: orange = the new date (what will change),
# blue = the source photo, grey = not changed.
NEW_DATE_COLOR = QColor("#b45f06")
SOURCE_COLOR = QColor("#1f5fc4")
MUTED_COLOR = QColor("#6b7a8c")


class DateTimeEditorMixin:
    # --- Mode -----------------------------------------------------------------

    @property
    def is_date_mode(self) -> bool:
        """True while the Date & Time tab is shown (the Photo List follows it)."""
        tabs = getattr(self, "editor_tabs", None)
        return tabs is not None and tabs.currentIndex() == DATE_TIME_TAB

    def editor_tab_changed(self, _index: int) -> None:
        """
        Switch the Photo List between GPS groups (Location) and camera groups
        (Date & Time). The selection is kept.
        """
        refresh_tab_icons(self)
        if self.is_picking_location:
            self.stop_picking_location()
        if self.is_only_selected:
            # Not offered in Date & Time mode.
            self.set_only_selected(False)
        selected = self.get_selected_paths()
        self._render_current_photo_session()
        self.select_browser_paths(selected)

    def choose_date_change_mode(self, mode: str) -> None:
        """Step 2: Shift or Set (a choice card was clicked)."""
        if mode == self._date_change_mode:
            # The chosen card: while step 2 is folded up to it, open all the
            # choices again; while open, fold back up.
            self._date_choices_open = not self._date_choices_open
            self.update_details_panel()
            return
        self._date_choices_open = False
        if self.is_picking_location:
            self.stop_picking_location()
        self._date_change_mode = mode
        if mode == MODE_SET and self._date_set_value is None:
            # Start from the reference photo's date, or today at noon.
            state = self._build_date_time_state()
            self._date_set_value = state.corrected_reference or datetime.now().replace(
                hour=12, minute=0, second=0, microsecond=0
            )
        self.update_details_panel()

    # --- Reference photo and the corrected date (Shift) -----------------------

    def _dated_selection(self) -> list[Path]:
        """The selected photos with a date, earliest first (the source left out)."""
        selected = self.get_selected_paths()
        exclude = self._time_source if self._time_source in selected else None
        return photos_by_date(self.session.loaded_photo_infos, selected, exclude=exclude)

    def _resolved_reference(self) -> Path | None:
        dated = self._dated_selection()
        if self._date_reference in dated:
            return self._date_reference
        return dated[0] if dated else None

    def step_date_reference(self, step: int) -> None:
        """The arrows on the reference card: use the previous/next photo by date."""
        dated = self._dated_selection()
        reference = self._resolved_reference()
        if reference is None:
            return
        index = dated.index(reference) + step
        if 0 <= index < len(dated):
            self._date_reference = dated[index]
            self.update_details_panel()

    def date_reference_edited(self) -> None:
        """
        The correct date and time typed for the reference photo: in the
        chosen time zone, or in the photo's own when none was chosen.
        """
        reference = self._resolved_reference()
        info = self.session.loaded_photo_infos.get(reference) if reference else None
        if info is None or info.date_taken is None:
            return
        value = self.date_reference_picker.value()
        zone = self._date_zone
        if zone is None:
            self._date_shift = value - info.date_taken
        else:
            self._date_shift = (value - offset_at_local(zone, value)) - photo_instant(info, zone)
        # Typed by hand: no longer from a photo (as on the Location tab).
        self._set_time_source(None)
        self.update_details_panel()

    def date_zone_chosen(self, key: str) -> None:
        """
        A time zone picked in a drop-down: the times shown convert to it
        (the same moment), and every photo changed gets it. (Change Time
        Zone with "Keep the clock time" keeps the clock times instead.)
        """
        zone = ZONES_BY_KEY.get(key)
        if self._date_change_mode == MODE_SET and self._date_set_value is not None:
            # Set's date and time is converted too, so the zone alone never
            # moves the moment (8:26 am MDT -> 9:26 am CDT); only editing the
            # date or time does. With no zone shown before, there's no moment
            # to keep: the time just gets the zone.
            shown = ZONES_BY_KEY.get(self._build_date_time_state().zone_key)
            if shown is not None and zone is not None:
                instant = self._date_set_value - offset_at_local(shown, self._date_set_value)
                self._date_set_value = to_zone(instant, zone)[0]
        self._date_zone = zone
        self.update_details_panel()

    def keep_clock_clicked(self, checked: bool) -> None:
        """
        Change Time Zone's "Keep the clock time" checkbox. Turning it on asks
        first (it moves the moment the photos were taken); Cancel unchecks
        it. Turning it off needs no question.
        """
        if not checked:
            self._date_keep_clock = False
            self.update_details_panel()
            return
        state = self._build_date_time_state()
        zone = ZONES_BY_KEY.get(state.zone_key)
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Question)
        dialog.setWindowTitle("Keep the Clock Time?")
        dialog.setText(
            keep_clock_message(self.session.loaded_photo_infos, self.get_selected_paths(), zone)
            if zone is not None
            else "When enabled, the photos keep their clock times and only get the new time zone."
        )
        keep_button = dialog.addButton("Keep Clock Time", QMessageBox.AcceptRole)
        dialog.addButton(QMessageBox.Cancel)
        dialog.setDefaultButton(keep_button)

        def closed(button) -> None:
            self._date_keep_clock = button is keep_button
            self.date_keep_clock_check.setChecked(self._date_keep_clock)
            self.update_details_panel()

        self.show_message(dialog, closed)

    def date_set_value_edited(self) -> None:
        self._date_set_value = self.date_set_picker.value()
        self.update_details_panel()

    def _current_shift(self) -> timedelta:
        """
        The shift (of the moment each photo was taken): from the source
        photo's time when there is one (it was taken at the same moment as
        the reference photo), else as entered.
        """
        source = self._time_source_photo()
        reference = self._resolved_reference()
        info = self.session.loaded_photo_infos.get(reference) if reference else None
        if source is None or info is None or info.date_taken is None:
            return self._date_shift
        zone = self._date_zone
        if zone is None and (source.time_offset is None or info.time_offset is None):
            # A photo without a time zone: compare clock times as they are.
            return source.date_taken - info.date_taken
        return photo_instant(source, zone) - photo_instant(info, zone)

    # --- The photo with the correct time (source) -----------------------------

    def _time_source_photo(self):
        """The source photo's PhotoInfo (in the list, or chosen from the computer)."""
        source = self._time_source
        if source is None:
            return None
        info = self.session.loaded_photo_infos.get(source)
        if info is None or source not in self.session.selected_paths:
            info = self._time_source_info
        return info if info is not None and info.date_taken is not None else None

    def _set_time_source(self, source: Path | None, info=None) -> None:
        self._time_source = source
        # Kept for a photo chosen from the computer (not in the Photo List).
        self._time_source_info = info
        self._refresh_source_marker()

    def clear_time_source(self) -> None:
        """The source card's ✕: stop using the photo's time."""
        self._set_time_source(None)
        self._date_shift = timedelta(0)
        self.update_details_panel()

    def use_time_from_path(self, path: Path) -> bool:
        """
        Use the time of a photo in the Photo List. Returns False if it has
        no date.
        """
        info = self.session.loaded_photo_infos.get(path)
        if info is None or info.date_taken is None or self._resolved_reference() is None:
            return False
        self._set_time_source(path)
        self.update_details_panel()
        self._set_status_message(
            f"Using the time from {path.name}: {format_display_datetime(info.date_taken)}.",
            "success",
        )
        return True

    def choose_time_from_photo(self) -> None:
        """Choose any photo file to use its time (see use_time_from_file)."""
        self._pick_photo_file("Use the Time from a Photo", self.use_time_from_file)

    def use_time_from_file(self, path: Path) -> None:
        """Use the date taken of a photo file as the reference photo's time."""
        if path in self.session.selected_paths and path in self.session.loaded_photo_infos:
            if not self.use_time_from_path(path):
                self._show_no_date_message()
            return
        info = self.workflow.read_photo_info(path)
        if info.gps_error:
            dialog = QMessageBox(self)
            dialog.setIcon(QMessageBox.Warning)
            dialog.setWindowTitle("Could Not Read Photo")
            dialog.setText(f"Could not read the date from {path.name}:\n{info.gps_error}")
            dialog.setStandardButtons(QMessageBox.Ok)
            self.show_message(dialog)
            return
        if info.date_taken is None:
            self._show_no_date_message()
            return
        self._set_time_source(path, info)
        self.update_details_panel()
        self._set_status_message(
            f"Using the time from {path.name}: {format_display_datetime(info.date_taken)}.",
            "success",
        )

    def _show_no_date_message(self) -> None:
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Information)
        dialog.setWindowTitle("No Date")
        dialog.setText("Selected Photo has no date taken, so its time can't be used.")
        dialog.setStandardButtons(QMessageBox.Ok)
        self.show_message(dialog)

    # --- From a Photo in the Photo List (pick mode) ---------------------------

    def toggle_picking_time(self, _checked: bool = False) -> None:
        if self.is_picking_location:
            self.stop_picking_location()
        else:
            self.start_picking_time()

    def start_picking_time(self) -> None:
        """
        Pick mode for the time: the next click on a photo with a date (not
        one of the photos being changed) uses its time. Shares the Location
        tab's pick mode (banner, lock, Esc).
        """
        reference = self._resolved_reference()
        if reference is None or not self._time_pickable_paths():
            self.pick_time_button.setChecked(False)
            return
        self._pick_kind = "time"
        self._picking_location = True
        self.pick_time_button.setChecked(True)
        self.pick_time_button.setText("Cancel")
        self.pick_banner_label.setText(TIME_PICK_PROMPT.format(reference=reference.name))
        self.pick_banner.show()
        self.list_widget.viewport().setCursor(Qt.CrossCursor)
        self._pick_escape_shortcut.setEnabled(True)
        self._refresh_pick_marks()
        self._apply_pick_mode_lock()

    def _time_pickable_paths(self) -> list[Path]:
        """Photos whose time can be used: they have a date and aren't selected."""
        selected = set(self.get_selected_paths())
        infos = self.session.loaded_photo_infos
        return [
            path for path in self.session.selected_paths
            if path not in selected and (info := infos.get(path)) is not None and info.date_taken
        ]

    def _time_pick_label(self, path: Path, selected: set[Path]) -> str:
        """Why a photo can't be picked for its time ("" if it can)."""
        info = self.session.loaded_photo_infos.get(path)
        if info is None or info.date_taken is None:
            return "No Date"
        if path in selected:
            return "Being Changed"
        return ""

    # --- Showing the state ----------------------------------------------------

    def reset_date_change(self) -> None:
        """
        Start the Date & Time change over, back to step 1 or 2: no kind of
        change chosen, no shift, the earliest photo as the reference, no
        source photo, each photo's own time zone. (Set's date stays.)
        """
        self._date_change_mode = None
        self._date_shift = timedelta(0)
        self._date_reference = None
        self._date_zone = None
        self._date_keep_clock = False
        self._date_choices_open = False
        if hasattr(self, "date_keep_clock_check"):
            self.date_keep_clock_check.setChecked(False)
        self._set_time_source(None)

    def _build_date_time_state(self) -> DateTimeState:
        in_list = set(self.session.selected_paths)
        source = self._time_source
        source_removed = source is not None and self._time_source_info is None and source not in in_list
        reference_removed = self._date_reference is not None and self._date_reference not in in_list
        if source_removed or reference_removed:
            # The source or the chosen reference photo was taken out of the
            # Photo List: the change based on it no longer applies.
            self.reset_date_change()
        return build_date_time_state(
            selected_paths=self.get_selected_paths(),
            photo_infos=self.session.loaded_photo_infos,
            mode=self._date_change_mode,
            reference=self._date_reference,
            shift=self._current_shift(),
            set_value=self._date_set_value or datetime.now().replace(microsecond=0),
            source=self._time_source,
            zone=self._date_zone,
            keep_clock=self._date_keep_clock,
            computer_offset=computer_utc_offset(),
        )

    def _apply_date_time_state(self, state: DateTimeState) -> None:
        shift_mode = self._date_change_mode == MODE_SHIFT
        self._apply_date_steps(state)
        self.date_shift_box.setVisible(shift_mode)
        self.date_set_box.setVisible(self._date_change_mode == MODE_SET)
        self.date_zone_box.setVisible(self._date_change_mode == MODE_ZONE)

        # Reference card.
        has_reference = state.reference is not None
        self.date_reference_title.setText(state.reference_title)
        self.date_reference_detail.setText(state.reference_detail)
        self.date_reference_detail.setVisible(bool(state.reference_detail))
        self.date_reference_earliest.setVisible(state.reference_is_earliest and state.selected_count > 1)
        self.date_reference_position.setText(state.reference_position)
        self.date_reference_back.setEnabled(state.can_step_back)
        self.date_reference_forward.setEnabled(state.can_step_forward)
        self.date_reference_thumbnail.setPixmap(self._thumbnail_pixmap(state.reference))
        if state.corrected_reference is not None:
            self.date_reference_picker.set_value(state.corrected_reference)
        # The whole picker comes back on after pick mode; then only its date
        # and time need a reference photo (the time zone box doesn't).
        self.date_reference_picker.setEnabled(True)
        self.date_reference_picker.set_time_enabled(has_reference)

        # Copy the time from a photo.
        if not self.is_picking_location:
            can_pick = has_reference and bool(self._time_pickable_paths())
            self.pick_time_button.setEnabled(can_pick)
            self.pick_time_button.setToolTip(
                "Click this, then click a photo in the Photo List whose time is right "
                "(e.g. from your phone), taken at the same moment as the reference photo."
                if can_pick
                else "Select the photos to change first; the photo with the right time must "
                "be in the Photo List and not selected."
            )
        self.time_from_photo_button.setEnabled(has_reference)
        self._refresh_time_source_card(state)

        # Set.
        if self._date_set_value is not None:
            self.date_set_picker.set_value(self._date_set_value)
        self.date_set_picker.setEnabled(True)

        # Time zone (both pickers: one per mode).
        for picker in (self.date_reference_picker, self.date_set_picker):
            picker.set_zones(
                state.zone_items,
                state.zone_key,
                mixed=state.zone_mixed,
                tooltip=state.zone_tooltip,
            )
        fill_zone_box(
            self.date_zone_combo,
            state.zone_items,
            state.zone_key,
            mixed=state.zone_mixed,
            # Only worth a hint when the photos are in several zones (red).
            tooltip=MIXED_ZONES_CHANGE_TIP if state.zone_mixed else "",
        )
        # Off (and blank) until a photo is selected, then always available,
        # even when the selected photos have no date (and no reference).
        for box in (self.date_reference_picker.zone_box, self.date_set_picker.zone_box, self.date_zone_combo):
            box.setEnabled(state.selected_count > 0)
        self.date_keep_clock_check.setChecked(self._date_keep_clock)

        self._fill_date_changes_list(state)
        self.date_hint_label.setText(state.hint)
        self.date_hint_label.setVisible(bool(state.hint))
        self._set_tone(self.date_hint_label, state.hint_tone)
        self.date_apply_button.setText(state.apply_label)
        self.date_apply_button.setEnabled(state.can_apply)

    def _apply_date_steps(self, state: DateTimeState) -> None:
        """
        The four steps: each done (✓), active (orange: do this now), or
        locked (grey, closed) until the steps before it are done. The pane
        scrolls to the step that just became active.
        """
        has_photos = bool(self.session.selected_paths)
        selected = state.selected_count
        mode = self._date_change_mode
        # Step 2 isn't done while its choices are open again (step 3 waits).
        done = [selected > 0, selected > 0 and mode is not None and not self._date_choices_open, False]
        done[2] = done[1] and state.can_apply

        select_step, mode_step, correct_step, apply_step = self.date_steps
        select_step.set_state(
            "done" if done[0] else "active",
            f"{selected} photo{'' if selected == 1 else 's'} selected" if done[0] else "",
        )
        self.step_add_photos_button.setVisible(not has_photos)
        self.step_select_hint.setText(
            "The Photo List is empty. Add photos first, then select the ones to change."
            if not has_photos
            else "Click photos in the Photo List, or a camera's checkbox to select all of its photos."
        )
        self.step_select_hint.setVisible(not done[0])

        # Step 2 folds up to the chosen card (more room for step 3); clicking
        # it opens all three choices again.
        folded = done[1]
        mode_step.set_state("locked" if not done[0] else "done" if folded else "active")
        for card_mode, card in self.date_choice_cards.items():
            card.setChecked(mode == card_mode)
            card.setEnabled(True)
            card.setVisible(not folded or mode == card_mode)
            card.set_folded(folded and mode == card_mode)

        correct_step.title.setText(
            "Enter the date and time"
            if mode == MODE_SET
            else "Choose the new time zone"
            if mode == MODE_ZONE
            else "Correct the date and time"
        )
        correct_step.set_state("locked" if not done[1] else "done" if done[2] else "active")
        apply_step.set_state("active" if done[2] else "locked")

        # Scroll to the step to do now (once, when it changes).
        active = 3 if done[2] else 2 if done[1] else 1 if done[0] else 0
        if active != self._date_active_step:
            self._date_active_step = active
            target = self.date_steps[active]
            # After the layout has caught up with the steps opening.
            QTimer.singleShot(0, lambda: self.date_scroll.ensureWidgetVisible(target, 0, 10))

    def _refresh_time_source_card(self, state: DateTimeState) -> None:
        source = self._time_source
        if source is None:
            self.time_source_card.hide()
            return
        info = self.session.loaded_photo_infos.get(source) or self._time_source_info
        self.time_source_title.setText(f"Time from {source.name}")
        camera = (info.camera if info is not None else None) or "Unknown Camera"
        date = format_display_datetime(info.date_taken if info is not None else None)
        self.time_source_detail.setText(f"{camera} · {date}")
        self.time_source_thumbnail.setPixmap(self._thumbnail_pixmap(source))
        self.time_source_clear.setEnabled(True)
        self.time_source_card.show()

    def _thumbnail_pixmap(self, path: Path | None):
        if path is None:
            return self._blank_thumbnail_icon().pixmap(52, 52)
        item = self._grid_items_by_path.get(str(path))
        icon = item.icon() if item is not None else self.thumbnail_loader.load_icon(path, has_gps=False)
        return icon.pixmap(52, 52)

    def _fill_date_changes_list(self, state: DateTimeState) -> None:
        """The "Changing date to:" list: name, current date, → new date."""
        changes = self.date_changes_list
        changes.setUpdatesEnabled(False)
        try:
            changes.clear()
            for row in state.rows:
                new = f"→  {row.new}" if row.kind == "change" else row.new
                item = QTreeWidgetItem([row.name, row.current, new])
                # For the hover hint when the row is cut short (DateChangesList).
                item.setData(0, CHANGE_ROW_ROLE, (row.name, row.current, row.new or "Not changed"))
                item.setForeground(1, QBrush(MUTED_COLOR))
                color = {
                    "change": NEW_DATE_COLOR,
                    "source": SOURCE_COLOR,
                }.get(row.kind, MUTED_COLOR)
                item.setForeground(2, QBrush(color))
                font = item.font(2)
                font.setBold(row.kind == "change")
                item.setFont(2, font)
                item.setTextAlignment(2, Qt.AlignRight | Qt.AlignVCenter)
                changes.addTopLevelItem(item)
            # Names and new dates in full; the current date takes the room left.
            changes.header().setStretchLastSection(False)
            changes.fit_columns()
        finally:
            changes.setUpdatesEnabled(True)

    # --- Apply ----------------------------------------------------------------

    def apply_date_change(self) -> None:
        """
        Write the new dates (Shift or Set) to the selected photos. Every
        photo is attempted; afterwards the changed photos are deselected and
        the status row offers Undo.
        """
        state = self._build_date_time_state()
        plan = state.plan
        if not plan.new_dates:
            return
        infos = self.session.loaded_photo_infos
        before = {path: saved_date_tags(infos.get(path)) for path in plan.new_dates}
        values = {
            path: date_tag_values(new, plan.new_offsets.get(path))
            for path, new in plan.new_dates.items()
        }
        selected_before = self.get_selected_paths()

        # The writes run in the background with a progress bar (see _run_writes).
        def done(result) -> None:
            self.session = result.session
            execution = result.execution_result
            succeeded = execution.successful_paths
            if succeeded:
                self._remember_gps_edit(
                    before_states={path: before[path] for path in succeeded},
                    after_states={path: values[path] for path in succeeded},
                    kind=EDIT_DATE,
                )
            else:
                self._clear_gps_edit_history()

            # Start over for the next change (back to step 1).
            shift_text = describe_shift(state.shift)
            state_mode = self._date_change_mode
            self.reset_date_change()

            # Deselect what changed; keep failures selected to retry.
            self._rerender_selecting(
                self._failed_targets(selected_before, list(plan.new_dates), succeeded)
            )
            if succeeded:
                count = len(succeeded)
                photos = f"{count} photo{'' if count == 1 else 's'}"
                if state_mode == MODE_SHIFT:
                    message = f"Shifted {photos} ({shift_text})."
                elif state_mode == MODE_ZONE:
                    zone = ZONES_BY_KEY.get(state.zone_key)
                    message = f"Changed the time zone of {photos}" + (f" to {zone.name}." if zone else ".")
                else:
                    message = f"Set the date on {photos} to {format_display_datetime(state.plan.new_dates[succeeded[0]])}."
                self._set_status_message(message, "success", undo=True)
            self._report_write_failures("change the date of", execution.failed_paths)

        self._run_writes(
            "Changing time zones" if self._date_change_mode == MODE_ZONE else "Changing dates",
            len(values),
            lambda progress: self.workflow.write_date_tags_workflow(
                session=self.session,
                values_by_path=values,
                on_progress=progress,
            ),
            done,
        )

    def _restore_date_states(self, states: dict, text: str, on_done) -> None:
        """Undo/redo of a date change: write the remembered date tags back."""
        self._restore_states(
            text,
            len(states),
            lambda progress: self.workflow.write_date_tags_workflow(
                session=self.session,
                values_by_path=states,
                on_progress=progress,
            ),
            on_done,
        )
