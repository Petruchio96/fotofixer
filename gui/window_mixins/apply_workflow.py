"""
Apply and Remove GPS: the two actions on the photos selected in the grid.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from PySide6.QtWidgets import QMessageBox


def _photos(count: int) -> str:
    return f"{count} photo" if count == 1 else f"{count} photos"


def _backup_note(count: int) -> str:
    """
    Added to the message after a change that made backups.
    """
    if not count:
        return ""
    copies = "a backup of the original" if count == 1 else f"{count} backups of the originals"
    return f" Saved {copies} next to {'it' if count == 1 else 'them'}."


class ApplyWorkflowMixin:
    def apply_coordinates_to_selected(self) -> None:
        """
        Write the New Location coordinates to every selected photo.
        """
        selected_paths = self.get_selected_paths()
        if not selected_paths:
            self._set_status_message("Select the photos to change in the Photo List first.", "error")
            return

        self.validate_latitude_field()
        self.validate_longitude_field()

        # The source photo already has this location: never write to it.
        targets = [path for path in selected_paths if path != self._location_source]
        if not targets:
            self._set_status_message(
                "The source photo isn't changed. Select the photos to give its location to.",
                "error",
            )
            return

        preparation = self.workflow.prepare_apply_workflow(
            session=self.session,
            selected_paths=targets,
            using_photo_source=False,
            latitude_text=self.latitude_input.text(),
            longitude_text=self.longitude_input.text(),
        )
        if preparation.error_message is not None:
            self._set_status_message(preparation.error_message, "error")
            return
        # The location came from a photo with an altitude: the targets get it too.
        if self._location_source is not None and self._location_source_altitude is not None:
            preparation.coordinates.altitude = self._location_source_altitude

        overwrite_entries = preparation.overwrite_entries
        if not overwrite_entries:
            self._apply_with_choice(preparation, selected_paths, "replace")
            return

        # Ask first; the answer arrives when the dialog closes (no blocking
        # exec(), see show_message).
        self._ask_overwrite_choice(
            overwrite_entries,
            other_count=len(preparation.target_paths) - len(overwrite_entries),
            on_choice=lambda choice: self._apply_with_choice(preparation, selected_paths, choice),
        )

    def _apply_with_choice(self, preparation, selected_paths: list[Path], choice: str) -> None:
        """
        Write the location, after the overwrite question if there was one.

        Args:
            choice:
                "replace" (update all), "skip" (only photos without GPS), or
                "cancel" (change nothing).
        """
        skipped_count = 0
        if choice == "cancel":
            self._set_status_message("Nothing was changed.", "info")
            return
        if choice == "skip":
            # Leave photos that already have GPS untouched.
            keep = {entry.path for entry in preparation.overwrite_entries}
            preparation = replace(
                preparation,
                target_paths=[path for path in preparation.target_paths if path not in keep],
                overwrite_entries=[],
            )
            skipped_count = len(keep)

        before_states = self._gps_states_for_paths(preparation.target_paths)
        # The writes run in the background with a progress bar (see _run_writes).
        def done(apply_result) -> None:
            self.session = apply_result.session
            backups = self._take_new_backups()

            result = apply_result.execution_result
            if result.successful_paths:
                coordinates = preparation.coordinates
                self._remember_gps_edit(
                    before_states={
                        path: before_states[path] for path in result.successful_paths
                    },
                    after_states={
                        path: (
                            (coordinates.latitude, coordinates.longitude)
                            if coordinates.altitude is None
                            else (coordinates.latitude, coordinates.longitude, coordinates.altitude)
                        )
                        for path in result.successful_paths
                    },
                    backups=backups,
                )
            else:
                self._clear_gps_edit_history()

            self._rerender_selecting(
                self._failed_targets(selected_paths, preparation.target_paths, result.successful_paths)
            )
            backup_count = len(backups)
            if result.successful_paths:
                message = f"Applied GPS to {_photos(len(result.successful_paths))}."
                if skipped_count:
                    message += (
                        f" Skipped {skipped_count} that already "
                        f"{'has' if skipped_count == 1 else 'had'} GPS."
                    )
                message += _backup_note(backup_count)
                self._set_status_message(message, "success", undo=True)
            self._report_write_failures("apply GPS to", list(result.failed_paths))

        self._run_writes(
            "Applying GPS",
            len(preparation.target_paths),
            lambda progress: self.workflow.execute_apply_workflow(
                session=self.session,
                preparation=preparation,
                on_progress=progress,
            ),
            done,
        )

    def _ask_overwrite_choice(
        self,
        overwrite_entries,
        *,
        other_count: int,
        on_choice: Callable[[str], None],
    ) -> None:
        """
        Ask what to do when some selected photos already have GPS.

        Args:
            overwrite_entries:
                The selected photos that already have GPS.
            other_count:
                How many selected photos have no GPS yet.
            on_choice:
                Called when the dialog closes with "replace" (update all),
                "skip" (update only photos without GPS), or "cancel"
                (change nothing).
        """
        count = len(overwrite_entries)
        have = "has" if count == 1 else "have"

        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Warning)
        dialog.setWindowTitle("Replace Existing GPS?")
        already = f"{_photos(count).capitalize()} already {have} GPS Coordinates."
        undo_tip = "Click Edit → Undo if you accidentally overwrite GPS data."
        if other_count:
            dialog.setText(
                f"{already} Choose Skip to keep the existing GPS data, "
                f"Replace to overwrite them. {undo_tip}"
            )
        else:
            # Every selected photo has GPS, so there is nothing to skip to.
            dialog.setText(f"{already} Choose Replace to overwrite them. {undo_tip}")
        # Show Details still lists each photo and its current coordinates.
        dialog.setDetailedText("\n".join(self._format_overwrite_entries(overwrite_entries)))

        cancel_button = dialog.addButton("Cancel", QMessageBox.RejectRole)
        # Skip only makes sense when some photos have no GPS yet.
        skip_button = (
            dialog.addButton("Skip Photos with GPS", QMessageBox.AcceptRole)
            if other_count
            else None
        )
        replace_button = dialog.addButton("Replace", QMessageBox.DestructiveRole)
        dialog.setDefaultButton(cancel_button)
        dialog.setEscapeButton(cancel_button)

        def closed(clicked) -> None:
            if clicked is replace_button:
                on_choice("replace")
            elif skip_button is not None and clicked is skip_button:
                on_choice("skip")
            else:
                on_choice("cancel")

        self.show_message(dialog, closed)

    def remove_gps_from_selected(self) -> None:
        """
        Delete the GPS coordinates stored in the selected photos (after asking).
        """
        paths_with_gps = [
            path
            for path in self.get_selected_paths()
            if (info := self.session.loaded_photo_infos.get(path)) is not None
            and info.current_latitude is not None
            and info.current_longitude is not None
        ]
        if not paths_with_gps:
            return

        confirmation_dialog = QMessageBox(self)
        confirmation_dialog.setIcon(QMessageBox.Warning)
        confirmation_dialog.setWindowTitle("Remove GPS?")
        confirmation_dialog.setText(
            f"Remove the GPS coordinates from {_photos(len(paths_with_gps))}?"
        )
        confirmation_dialog.setInformativeText(
            "Show Details lists the photos. You can undo this afterwards."
        )
        confirmation_dialog.setDetailedText("\n".join(path.name for path in paths_with_gps))
        confirmation_dialog.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        confirmation_dialog.button(QMessageBox.Ok).setText("Remove GPS")
        confirmation_dialog.setDefaultButton(QMessageBox.Cancel)
        remove_button = confirmation_dialog.button(QMessageBox.Ok)

        def closed(clicked) -> None:
            if clicked is remove_button:
                self._remove_gps_confirmed(paths_with_gps)

        # The answer arrives when the dialog closes (no blocking exec()).
        self.show_message(confirmation_dialog, closed)

    def _remove_gps_confirmed(self, paths_with_gps: list[Path]) -> None:
        """
        Remove GPS from these photos, after the user confirmed.
        """
        selected_paths = self.get_selected_paths()
        before_states = self._gps_states_for_paths(paths_with_gps)
        # The backend attempts every file and reports failures instead of
        # stopping at the first one.
        # The writes run in the background with a progress bar (see _run_writes).
        def done(clear_result) -> None:
            self.session = clear_result.session
            backups = self._take_new_backups()
            result = clear_result.execution_result

            if result.successful_paths:
                self._remember_gps_edit(
                    before_states=before_states,
                    after_states={path: (None, None) for path in result.successful_paths},
                    backups=backups,
                )
            else:
                self._clear_gps_edit_history()

            self._rerender_selecting(
                self._failed_targets(selected_paths, paths_with_gps, result.successful_paths)
            )
            backup_count = len(backups)
            if result.successful_paths:
                self._set_status_message(
                    f"Removed GPS from {_photos(len(result.successful_paths))}."
                    + _backup_note(backup_count),
                    "success",
                    undo=True,
                )
            self._report_write_failures("remove GPS from", list(result.failed_paths))

        self._run_writes(
            "Removing GPS",
            len(paths_with_gps),
            lambda progress: self.workflow.clear_gps_workflow(
                session=self.session,
                target_paths=paths_with_gps,
                on_progress=progress,
            ),
            done,
        )

    @staticmethod
    def _failed_targets(
        selected_paths: list[Path],
        target_paths: list[Path],
        successful_paths: list[Path],
    ) -> list[Path]:
        """
        The photos to keep selected after Apply or Remove GPS: only those
        that should have changed and didn't (to retry). The rest are
        deselected: changed photos may move to a group the view hides, and
        would otherwise be changed again by the next Apply. Undo brings the
        old selection back.
        """
        targets = set(target_paths)
        changed = set(successful_paths)
        return [path for path in selected_paths if path in targets and path not in changed]

    def _rerender_selecting(self, paths: list[Path]) -> None:
        """
        Redraw the grid after a change (photos may move between groups) and
        select these photos.
        """
        self._render_current_photo_session()
        self.reselect_paths(paths)
        self.update_details_panel()
