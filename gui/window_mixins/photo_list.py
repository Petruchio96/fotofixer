from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSignalBlocker, QSize, Qt
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.photo_dates import UNKNOWN_CAMERA, format_display_datetime
from gui.background import CancelToken
from gui.presenters.thumbnail_items import build_thumbnail_item_data_list, reselect_paths
from gui.widgets.thumbnail_delegate import FADED_ROLE, GROUP_HEADER_ROLE, SHIMMER_ROLE
from services.date_time_service import group_by_camera
from services.models import WorkflowSession

THUMBNAIL_PATH_ROLE = Qt.UserRole
THUMBNAIL_LATITUDE_ROLE = Qt.UserRole + 1
THUMBNAIL_LONGITUDE_ROLE = Qt.UserRole + 2
# Date & Time mode: the photo's camera group (past the delegate's roles).
THUMBNAIL_CAMERA_ROLE = Qt.UserRole + 10
# Group heading keys in Date & Time mode start with this, then the camera.
CAMERA_GROUP_PREFIX = "camera:"
THUMBNAIL_ITEM_SIZE = QSize(170, 190)
# Group heading heights: just the title, or the title with a divider line
# above it (separating it from the group shown above).
GPS_HEADER_HEIGHT = 26
GPS_HEADER_WITH_DIVIDER_HEIGHT = 44
GPS_HEADER_MIN_WIDTH = THUMBNAIL_ITEM_SIZE.width()

# Thumbnails are built in batches so the grid fills in steadily and Cancel
# takes effect quickly. RAW previews within a batch are read in one go.
THUMBNAIL_BATCH_SIZE = 24

# Placeholder tiles only appear for thumbnails not ready after this long, so
# quick loads show thumbnails directly with no placeholder flash (milliseconds).
PLACEHOLDER_DELAY_MS = 300

# Shimmer animation frame interval (milliseconds); 40 ms is 25 frames a second.
SHIMMER_FRAME_MS = 40


class PhotoListMixin:
    def select_all_photos(self) -> None:
        """
        Add every photo currently shown to the selection. Photos hidden by
        the Show filter keep whatever selection they have.
        """
        with QSignalBlocker(self.list_widget):
            for item in self._photo_items():
                if not item.isHidden():
                    item.setSelected(True)
        self.list_widget.viewport().update()
        self.update_details_panel()

    def clear_photo_selection(self) -> None:
        self.list_widget.clearSelection()
        # Deselect All also starts the Date & Time change over.
        self.reset_date_change()
        self.update_details_panel()

    def remove_selected_from_list(self) -> None:
        """
        Take the selected photos out of the list. Files are not touched.
        """
        self._remove_browser_paths(set(self.get_selected_paths()))

    def clear_photo_list(self) -> None:
        """
        Take every photo out of the list. Files are not touched.
        """
        self.cancel_loading()
        self._remove_browser_paths(set(self.session.selected_paths))

    def _remove_browser_paths(self, paths_to_remove: set[Path]) -> None:
        if not paths_to_remove:
            return

        self.session.selected_paths = [
            path for path in self.session.selected_paths if path not in paths_to_remove
        ]
        self.session.target_paths = [
            path for path in self.session.target_paths if path not in paths_to_remove
        ]
        self.populate_list()

    def add_photos(self) -> None:
        """
        Choose photos to add to the list (see _add_chosen_photos).
        """
        self._pick_photo_files("Add Photos", self._add_chosen_photos)

    def _add_chosen_photos(self, file_paths: list[Path]) -> None:
        """
        Add photos to the list. Photos already in it are skipped.
        """
        if not file_paths:
            return

        in_list = set(self.session.selected_paths)
        new_paths = list(dict.fromkeys(path for path in file_paths if path not in in_list))
        skipped = len(file_paths) - len(new_paths)
        if not new_paths:
            self._set_status_message(
                "Those photos are already in the list.",
                "info",
            )
            return

        self.load_photos(
            self.session.selected_paths + new_paths,
            added_count=len(new_paths),
            skipped_count=skipped,
        )

    def load_photos(
        self,
        file_paths: list[Path],
        *,
        added_count: int | None = None,
        skipped_count: int = 0,
    ) -> None:
        """
        Read GPS data for the photo list in the background, then show it.

        The current grid stays usable while this runs, and the photos
        selected in it stay selected. Thumbnails are loaded afterwards, also
        in the background (see _start_thumbnail_job).

        Args:
            file_paths:
                Every photo the list should hold, in order.
            added_count / skipped_count:
                For the message afterwards: how many photos are new, and how
                many chosen photos were already in the list.
        """
        was_empty = not self.session.selected_paths
        self.cancel_loading(update_indicator=False)
        self._gps_load_generation += 1
        generation = self._gps_load_generation
        token = CancelToken()
        self._gps_load_token = token
        paths = list(file_paths)
        workflow = self.workflow

        self.loading_indicator.begin(f"Reading GPS data for {len(paths)} photos…")

        def work() -> WorkflowSession | None:
            if token.cancelled:
                return None
            return workflow.refresh_photo_workflow(WorkflowSession(selected_paths=paths))

        def done(new_session: WorkflowSession | None) -> None:
            if generation != self._gps_load_generation or new_session is None:
                return
            self._gps_load_token = None
            # Keep the update list and source photo as they are now, including
            # any changes made while GPS data was being read.
            new_session.target_paths = list(self.session.target_paths)
            new_session.source_photo_info = self.session.source_photo_info
            new_session.source_photo_path = self.session.source_photo_path
            still_selected = self.get_selected_paths()
            self.session = new_session
            # Open on Needs GPS only for a fresh list; adding to a list keeps
            # the Show filter the user is on.
            if was_empty:
                self._choose_default_grid_filter()
            self._render_current_photo_session()
            if still_selected:
                self.select_browser_paths(still_selected)
            if added_count is not None:
                message = f"Added {added_count} photo{'' if added_count == 1 else 's'}."
                if skipped_count:
                    message += (
                        f" {skipped_count} {'was' if skipped_count == 1 else 'were'} "
                        "already in the list."
                    )
                self._set_status_message(message, "success")

        def failed(exc: BaseException) -> None:
            if generation != self._gps_load_generation:
                return
            self._gps_load_token = None
            self.loading_indicator.finish()
            dialog = QMessageBox(self)
            dialog.setIcon(QMessageBox.Warning)
            dialog.setWindowTitle("Could Not Load Photos")
            dialog.setText(f"The photos could not be read:\n\n{exc}")
            dialog.setStandardButtons(QMessageBox.Ok)
            # Not the blocking QMessageBox.warning(): see show_message.
            self.show_message(dialog)

        self.background.submit(work, done, failed)

    def cancel_loading(self, update_indicator: bool = True) -> None:
        """
        Stop any background loading. Thumbnails not loaded yet get a plain icon.
        """
        if self._gps_load_token is not None:
            self._gps_load_token.cancel()
            self._gps_load_token = None
            # Ignore the result if it arrives anyway.
            self._gps_load_generation += 1

        self._cancel_thumbnail_job(use_fallback_icons=True)
        if update_indicator:
            self.loading_indicator.finish()

    def populate_list(self) -> None:
        self._refresh_photo_session()
        self._render_current_photo_session()

    def _refresh_photo_session(self) -> None:
        self.session = self.workflow.refresh_photo_workflow(self.session)

    def _render_current_photo_session(self) -> None:
        self.session.thumbnail_items = build_thumbnail_item_data_list(
            self.session.loaded_photos
        )
        self._render_photo_list()

    def _render_photo_list(self) -> None:
        # The items are about to be replaced, so forget any still-loading ones.
        self._cancel_thumbnail_job(use_fallback_icons=False)
        pending: list[tuple[Path, QListWidgetItem, bool]] = []

        self.list_widget.setUpdatesEnabled(False)
        try:
            self.list_widget.clear()
            self._group_header_items = []
            self._grid_items_by_path = {}
            if self.is_date_mode:
                self._add_camera_groups(pending)
            gps_header_added = False
            gps_count = sum(1 for item_data in self.session.thumbnail_items if item_data.has_gps)
            no_gps_count = len(self.session.thumbnail_items) - gps_count

            # Photos without GPS are listed first, under their own heading.
            if no_gps_count and not self.is_date_mode:
                self._build_group_header_item(
                    f"Photos without GPS Coordinates ({no_gps_count})",
                    with_divider=False,
                    group="no_gps",
                )

            for item_data in [] if self.is_date_mode else self.session.thumbnail_items:
                if item_data.has_gps and not gps_header_added:
                    self._build_group_header_item(
                        f"Photos with GPS Coordinates ({gps_count})",
                        with_divider=True,
                        group="gps",
                    )
                    gps_header_added = True

                path = item_data.path
                # Thumbnails already built are shown right away; the rest start
                # blank and are filled in by the background job.
                icon = self.thumbnail_loader.cached_icon(path, has_gps=item_data.has_gps)

                item = QListWidgetItem(
                    icon if icon is not None else self._blank_thumbnail_icon(),
                    item_data.filename,
                )
                if icon is None:
                    pending.append((path, item, item_data.has_gps))
                item.setData(THUMBNAIL_PATH_ROLE, str(path))
                self._grid_items_by_path[str(path)] = item
                item.setData(THUMBNAIL_LATITUDE_ROLE, item_data.latitude)
                item.setData(THUMBNAIL_LONGITUDE_ROLE, item_data.longitude)
                item.setToolTip(item_data.tooltip)
                item.setSizeHint(THUMBNAIL_ITEM_SIZE)
                self.list_widget.addItem(item)
        finally:
            self.list_widget.setUpdatesEnabled(True)

        self._show_filter_bars()
        self._apply_grid_filter()
        self._refresh_source_marker()
        self._refresh_pick_marks()
        self._apply_pick_filter_rules()
        self.update_details_panel()
        self._start_thumbnail_job(pending)

    def _add_camera_groups(self, pending: list[tuple[Path, QListWidgetItem, bool]]) -> None:
        """
        Date & Time mode: one group per camera, photos in date order, each
        tile showing its date under the name. No GPS badges here.
        """
        infos = self.session.loaded_photo_infos
        data_by_path = {item_data.path: item_data for item_data in self.session.thumbnail_items}
        groups = group_by_camera(infos, list(data_by_path))
        for index, (camera, paths) in enumerate(groups):
            self._build_group_header_item(
                f"{camera} ({len(paths)})",
                with_divider=index > 0,
                group=CAMERA_GROUP_PREFIX + camera,
                camera=camera,
            )
            for path in paths:
                item_data = data_by_path[path]
                info = infos.get(path)
                taken = info.date_taken if info is not None else None
                icon = self.thumbnail_loader.cached_icon(path, has_gps=False)
                item = QListWidgetItem(
                    icon if icon is not None else self._blank_thumbnail_icon(),
                    f"{item_data.filename}\n{format_display_datetime(taken)}",
                )
                if icon is None:
                    pending.append((path, item, False))
                item.setData(THUMBNAIL_PATH_ROLE, str(path))
                item.setData(THUMBNAIL_LATITUDE_ROLE, item_data.latitude)
                item.setData(THUMBNAIL_LONGITUDE_ROLE, item_data.longitude)
                item.setData(THUMBNAIL_CAMERA_ROLE, camera)
                item.setToolTip(
                    f"{item_data.filename}\n{camera}\n"
                    + (f"Taken {format_display_datetime(taken)}" if taken else "No date taken")
                )
                item.setSizeHint(THUMBNAIL_ITEM_SIZE)
                self.list_widget.addItem(item)
                self._grid_items_by_path[str(path)] = item
        self._rebuild_camera_filter([camera for camera, _ in groups])

    # --- Date & Time mode: camera filter and camera checkboxes ---------------

    def _show_filter_bars(self) -> None:
        """
        Location: the Show filter. Date & Time: the camera filter, only when
        there is more than one camera.
        """
        date_mode = self.is_date_mode
        self.gps_filter_bar.setVisible(not date_mode)
        self.camera_filter_bar.setVisible(date_mode and len(self.camera_filter_buttons) > 2)

    def _rebuild_camera_filter(self, cameras: list[str]) -> None:
        """One button for All, then one per camera, with photo counts."""
        if self._camera_filter != "all" and self._camera_filter not in cameras:
            self._camera_filter = "all"
        for button in self.camera_filter_buttons.values():
            self.camera_filter_group.removeButton(button)
            button.deleteLater()
        self.camera_filter_buttons = {}
        counts = {
            camera: sum(
                1 for item_data in self.session.thumbnail_items
                if (self.session.loaded_photo_infos.get(item_data.path) is not None
                    and (self.session.loaded_photo_infos[item_data.path].camera or UNKNOWN_CAMERA) == camera)
            )
            for camera in cameras
        }
        keys = ["all", *cameras]
        for position, key in enumerate(keys):
            count = len(self.session.thumbnail_items) if key == "all" else counts[key]
            button = QPushButton(f"{'All' if key == 'all' else key} ({count})")
            button.setObjectName("filterButton")
            button.setCheckable(True)
            button.setProperty(
                "segment",
                "first" if position == 0 else "last" if position == len(keys) - 1 else "middle",
            )
            button.setToolTip(
                "Show photos from every camera" if key == "all" else f"Show only photos from the {key}"
            )
            button.setChecked(key == self._camera_filter)
            button.clicked.connect(lambda _checked=False, key=key: self.set_camera_filter(key))
            self.camera_filter_group.addButton(button)
            self.camera_filter_buttons[key] = button
            # Before the stretch at the end of the bar.
            self.camera_filter_layout.insertWidget(self.camera_filter_layout.count() - 1, button)

    def set_camera_filter(self, key: str) -> None:
        """Date & Time mode: show every camera's photos, or one camera's."""
        self._camera_filter = key
        button = self.camera_filter_buttons.get(key)
        if button is not None and not button.isChecked():
            button.setChecked(True)
        # The camera checkboxes are only in the All view.
        selected = self.get_selected_paths()
        self._render_photo_list()
        self.select_browser_paths(selected)

    def _camera_checkboxes(self) -> list[QCheckBox]:
        boxes = []
        for header in self._group_header_items:
            widget = self.list_widget.itemWidget(header)
            box = widget.findChild(QCheckBox, "cameraCheck") if widget is not None else None
            if box is not None:
                boxes.append(box)
        return boxes

    def _refresh_camera_checkboxes(self) -> None:
        """Checked when every photo from that camera is selected."""
        if not self.is_date_mode:
            return
        for box in self._camera_checkboxes():
            camera = box.property("camera")
            items = [
                item for item in self._grid_items_by_path.values()
                if item.data(THUMBNAIL_CAMERA_ROLE) == camera
            ]
            with QSignalBlocker(box):
                box.setChecked(bool(items) and all(item.isSelected() for item in items))

    def _set_camera_checkboxes_enabled(self, enabled: bool) -> None:
        for box in self._camera_checkboxes():
            box.setEnabled(enabled)

    def select_camera_photos(self, camera: str, selected: bool) -> None:
        """A camera checkbox: select (or deselect) every photo from that camera."""
        with QSignalBlocker(self.list_widget):
            for item in self._grid_items_by_path.values():
                if item.data(THUMBNAIL_CAMERA_ROLE) == camera:
                    item.setSelected(selected)
        self.list_widget.viewport().update()
        self.update_details_panel()

    def _choose_default_grid_filter(self) -> None:
        """
        Newly loaded photos open on "Needs GPS", since those are the photos
        to work on, or on "All" when every photo already has GPS.
        """
        needs_gps = any(
            info.current_latitude is None or info.current_longitude is None
            for info in self.session.loaded_photos
        )
        default = "needs" if needs_gps else "all"
        if self._picking_location:
            # Pick mode decides the filter for now; use this one afterwards.
            self._filter_before_pick = default
            return
        self._grid_filter = default
        self.grid_filter_buttons[default].setChecked(True)

    @property
    def is_only_selected(self) -> bool:
        return self._only_selected_paths is not None

    def set_only_selected(self, on: bool) -> None:
        """
        Turn "Only Show Selected Photos" on or off.

        While on, the grid shows the photos that were selected when it was
        turned on. Deselecting one leaves it in place, faded, so nothing moves
        and a stray click can be undone by clicking it again. No view button
        is shown as chosen; turning this off goes back to the view chosen
        before, and clicking a view button turns it off and shows that view.
        """
        if on == self.is_only_selected:
            return
        self._only_selected_paths = (
            {str(path) for path in self.get_selected_paths()} if on else None
        )
        if self.only_selected_button.isChecked() != on:
            with QSignalBlocker(self.only_selected_button):
                self.only_selected_button.setChecked(on)
        self._show_grid_filter_as_chosen(not on)
        self._apply_grid_filter()
        self.update_details_panel()

    def _show_grid_filter_as_chosen(self, chosen: bool) -> None:
        """
        Mark the current view's button as chosen, or mark none of them.
        """
        group = self.grid_filter_group
        group.setExclusive(False)
        for key, button in self.grid_filter_buttons.items():
            button.setChecked(chosen and key == self._grid_filter)
        group.setExclusive(True)

    def _refresh_faded_marks(self) -> None:
        """
        Fade deselected photos while "Only Show Selected Photos" is on.
        """
        for item in self._grid_items_by_path.values():
            faded = self.is_only_selected and not item.isSelected()
            if bool(item.data(FADED_ROLE)) != faded:
                item.setData(FADED_ROLE, faded)

    def set_grid_filter(self, key: str) -> None:
        """
        Show all photos, only those needing GPS, or only those that have it.
        Turns off Only Show Selected Photos.
        """
        if self.is_only_selected:
            self.set_only_selected(False)
        self._grid_filter = key
        button = self.grid_filter_buttons.get(key)
        if button is not None and not button.isChecked():
            button.setChecked(True)
        self._apply_grid_filter()
        self.update_details_panel()

    def _apply_grid_filter(self) -> None:
        if self.is_date_mode:
            self._apply_camera_filter()
            return
        show_no_gps = self._grid_filter in ("all", "needs")
        show_gps = self._grid_filter in ("all", "has")
        only_paths = self._only_selected_paths

        # Hiding photos doesn't deselect them: the selection is the same in
        # every view, and switching back shows the photos still selected.
        groups_shown = set()
        with QSignalBlocker(self.list_widget):
            for item in self._photo_items():
                has_gps = item.data(THUMBNAIL_LATITUDE_ROLE) is not None
                if only_paths is not None:
                    shown = item.data(THUMBNAIL_PATH_ROLE) in only_paths
                else:
                    shown = show_gps if has_gps else show_no_gps
                item.setHidden(not shown)
                if shown:
                    groups_shown.add("gps" if has_gps else "no_gps")

        # A group heading shows when any of its photos do, and its divider
        # line only when there is a group shown above it to divide from.
        for header in self._group_header_items:
            header.setHidden(header.data(GROUP_HEADER_ROLE) not in groups_shown)
            divider = self._group_header_divider(header)
            if divider is not None:
                divider.setHidden(len(groups_shown) < 2)
        self._refresh_faded_marks()

        self._refresh_thumbnail_group_header_sizes()

        # Say why the grid is empty instead of showing a blank box.
        any_visible = any(not item.isHidden() for item in self._photo_items())
        if any_visible:
            message = ""
        elif not self._grid_items_by_path:
            message = 'Click "+ Add Photos" to get started.'
        elif self._grid_filter == "needs":
            message = "No photos need GPS. Every photo shown here has coordinates."
        else:
            message = "None of these photos have GPS yet."
        self.list_widget.set_empty_message(message)

    def _apply_camera_filter(self) -> None:
        """Date & Time mode: show every camera, or only the chosen one."""
        camera_filter = self._camera_filter
        with QSignalBlocker(self.list_widget):
            for item in self._photo_items():
                item.setHidden(
                    camera_filter != "all" and item.data(THUMBNAIL_CAMERA_ROLE) != camera_filter
                )
        shown_groups = {
            CAMERA_GROUP_PREFIX + item.data(THUMBNAIL_CAMERA_ROLE)
            for item in self._photo_items() if not item.isHidden()
        }
        for header in self._group_header_items:
            header.setHidden(header.data(GROUP_HEADER_ROLE) not in shown_groups)
            divider = self._group_header_divider(header)
            if divider is not None:
                divider.setHidden(len(shown_groups) < 2)
        self._refresh_faded_marks()
        self._refresh_thumbnail_group_header_sizes()
        self.list_widget.set_empty_message(
            "" if shown_groups
            else 'Click "+ Add Photos" to get started.' if not self._grid_items_by_path
            else "No photos from this camera."
        )

    def _photo_items(self) -> list[QListWidgetItem]:
        return list(self._grid_items_by_path.values())

    def _selected_photo_items(self) -> list[QListWidgetItem]:
        # Every selected photo counts, including photos the Show filter hides
        # right now. Listed in on-screen order, not the order they were clicked.
        return [item for item in self._grid_items_by_path.values() if item.isSelected()]

    def _start_thumbnail_job(self, pending: list[tuple[Path, QListWidgetItem, bool]]) -> None:
        """
        Build missing thumbnails in the background, filling in the grid batch
        by batch.
        """
        if not pending:
            if self._gps_load_token is None:
                self.loading_indicator.finish()
            return

        self._thumbnail_generation += 1
        generation = self._thumbnail_generation
        token = CancelToken()
        self._thumbnail_token = token
        self._pending_thumbnail_items = {
            str(path): (item, has_gps) for path, item, has_gps in pending
        }
        self._thumbnail_total = len(pending)

        self.loading_indicator.begin(
            f"Loading thumbnails… 0 of {self._thumbnail_total}",
            total=self._thumbnail_total,
        )
        self._placeholder_timer.start(PLACEHOLDER_DELAY_MS)

        paths = [path for path, _, _ in pending]
        batch_size = self.thumbnail_batch_size
        loader = self.thumbnail_loader
        background = self.background

        def work() -> None:
            # Runs on the background thread: only reads files and builds QImages.
            for start in range(0, len(paths), batch_size):
                if token.cancelled:
                    return
                images = loader.load_images(paths[start:start + batch_size])
                background.post(self._apply_thumbnail_batch, (generation, images))

        def finished(_result: object) -> None:
            self._thumbnail_job_finished(generation)

        background.submit(work, finished, finished)

    def _apply_thumbnail_batch(self, payload) -> None:
        """
        Put a batch of finished thumbnails into the grid (GUI thread).
        """
        generation, images = payload
        if generation != self._thumbnail_generation:
            return

        hidden_changed = False
        for path, image in images.items():
            entry = self._pending_thumbnail_items.pop(str(path), None)
            if entry is None:
                continue
            item, has_gps = entry
            item.setIcon(self.thumbnail_loader.icon_from_image(path, has_gps, image))
            # A photo with GPS shows its badge on the Location tab and none on
            # Date & Time: build the other version now, so switching tabs
            # doesn't read the photos again.
            if item.data(THUMBNAIL_LATITUDE_ROLE) is not None:
                self.thumbnail_loader.icon_from_image(path, not has_gps, image)
            item.setData(SHIMMER_ROLE, False)
            hidden_changed = hidden_changed or item.isHidden()
            if path == self._location_source:
                self._refresh_source_card()
        if hidden_changed:
            self._relayout_after_hidden_icon_change()

        done = self._thumbnail_total - len(self._pending_thumbnail_items)
        self.loading_indicator.set_progress(
            done,
            self._thumbnail_total,
            f"Loading thumbnails… {done} of {self._thumbnail_total}",
        )
        if not self._pending_thumbnail_items:
            self._stop_thumbnail_animation()

    def _relayout_after_hidden_icon_change(self) -> None:
        """
        Lay the grid out again after a hidden photo's thumbnail changed.

        Qt quirk: in icon mode, changing the icon of a photo hidden by the
        Show filter leaves the grid's "which photo is under the mouse" lookup
        out of date, so clicks and hover miss parts of the photos shown.
        """
        self.list_widget.doItemsLayout()

    def _thumbnail_job_finished(self, generation: int) -> None:
        if generation != self._thumbnail_generation:
            return
        # Anything still waiting (the job failed) gets a plain icon.
        self._cancel_thumbnail_job(use_fallback_icons=True)
        if self._gps_load_token is None:
            self.loading_indicator.finish()

    def _cancel_thumbnail_job(self, *, use_fallback_icons: bool) -> None:
        """
        Stop the thumbnail job and stop tracking its items.

        Args:
            use_fallback_icons:
                True to give items still waiting a plain icon. False when the
                items are about to be deleted anyway.
        """
        if self._thumbnail_token is not None:
            self._thumbnail_token.cancel()
            self._thumbnail_token = None
        # Ignore any batches that arrive later.
        self._thumbnail_generation += 1

        if use_fallback_icons:
            hidden_changed = False
            for item, has_gps in self._pending_thumbnail_items.values():
                item.setIcon(self.thumbnail_loader.fallback_icon_for(has_gps))
                item.setData(SHIMMER_ROLE, False)
                hidden_changed = hidden_changed or item.isHidden()
            if hidden_changed:
                self._relayout_after_hidden_icon_change()
        self._pending_thumbnail_items = {}
        self._stop_thumbnail_animation()

    def _show_thumbnail_placeholders(self) -> None:
        """
        Thumbnails are taking a while: show shimmering placeholder tiles.
        """
        if not self._pending_thumbnail_items:
            return
        for item, _ in self._pending_thumbnail_items.values():
            item.setData(SHIMMER_ROLE, True)
        self._shimmer_clock.start()
        self._shimmer_timer.start(SHIMMER_FRAME_MS)

    def _advance_shimmer(self) -> None:
        self.thumbnail_delegate.advance(self._shimmer_clock.restart())
        self.list_widget.viewport().update()

    def _stop_thumbnail_animation(self) -> None:
        self._placeholder_timer.stop()
        self._shimmer_timer.stop()

    def _blank_thumbnail_icon(self) -> QIcon:
        """
        A transparent icon, so waiting items keep their size in the grid.
        """
        if self._blank_icon is None:
            pixmap = QPixmap(self.list_widget.iconSize())
            pixmap.fill(Qt.transparent)
            self._blank_icon = QIcon(pixmap)
        return self._blank_icon

    def get_selected_paths(self) -> list[Path]:
        """
        The photos to act on: every selected photo, shown or not.
        """
        return [
            Path(item.data(THUMBNAIL_PATH_ROLE))
            for item in self._selected_photo_items()
        ]

    def _build_group_header_item(
        self,
        title: str,
        *,
        with_divider: bool,
        group: str,
        camera: str | None = None,
    ) -> QListWidgetItem:
        item = QListWidgetItem()
        item.setFlags(Qt.NoItemFlags)
        item.setData(GROUP_HEADER_ROLE, group)
        item.setSizeHint(self._thumbnail_group_header_size(item))
        self.list_widget.addItem(item)
        self.list_widget.setItemWidget(
            item,
            self._build_group_header_widget(title, with_divider=with_divider, group=group, camera=camera),
        )
        self._group_header_items.append(item)
        return item

    def _group_header_divider(self, item: QListWidgetItem) -> QFrame | None:
        widget = self.list_widget.itemWidget(item)
        return widget.findChild(QFrame, "groupDivider") if widget is not None else None

    def _thumbnail_group_header_size(self, item: QListWidgetItem) -> QSize:
        divider = self._group_header_divider(item)
        shows_divider = divider is not None and not divider.isHidden()
        return QSize(
            max(self.list_widget.viewport().width(), GPS_HEADER_MIN_WIDTH),
            GPS_HEADER_WITH_DIVIDER_HEIGHT if shows_divider else GPS_HEADER_HEIGHT,
        )

    def _refresh_thumbnail_group_header_sizes(self) -> None:
        for item in getattr(self, "_group_header_items", []):
            item.setSizeHint(self._thumbnail_group_header_size(item))
        self.list_widget.doItemsLayout()

    def _build_group_header_widget(
        self,
        title: str,
        *,
        with_divider: bool,
        group: str,
        camera: str | None = None,
    ) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 0, 12, 0)
        layout.setSpacing(0)

        # The divider separates a group from the one above it. It is shown
        # only while that group is shown too (see _apply_grid_filter).
        if with_divider:
            line = QFrame()
            line.setObjectName("groupDivider")
            line.setFixedHeight(1)
            layout.addWidget(line)
        # The title sits at the bottom, close to its photos.
        layout.addStretch(1)

        # Blue for "has GPS" (what exists), orange for "needs GPS" (what will
        # change); see styles.py. Camera groups (Date & Time mode) are navy,
        # the Photo List's color, and in the All view have a checkbox that
        # selects every photo from that camera instead of the dot.
        if camera is not None and self._camera_filter == "all":
            dot = QCheckBox()
            dot.setObjectName("cameraCheck")
            dot.setProperty("camera", camera)
            dot.setToolTip(f"Select or deselect every photo from the {camera}")
            dot.setCursor(Qt.PointingHandCursor)
            dot.toggled.connect(lambda checked, camera=camera: self.select_camera_photos(camera, checked))
        else:
            dot = QLabel("●")
            dot.setObjectName("groupDot")
            dot.setProperty("group", "camera" if camera is not None else group)
        label = QLabel(title)
        label.setObjectName("thumbnailGroupHeader")
        label.setProperty("group", "camera" if camera is not None else group)
        label.setWordWrap(False)
        label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(6)
        title_row.addWidget(dot)
        title_row.addWidget(label)
        title_row.addStretch(1)
        layout.addLayout(title_row)
        return widget

    def reselect_paths(self, paths_to_select: list[Path]) -> None:
        reselect_paths(self.list_widget, paths_to_select)
        self._update_selection_metrics()

    def select_browser_paths(
        self,
        paths_to_select: list[Path],
        *,
        update_details: bool = True,
    ) -> None:
        self.reselect_paths(paths_to_select)
        if update_details:
            self.update_details_panel()

    def show_context_menu(self, position) -> None:
        item = self.list_widget.itemAt(position)

        if item is None:
            return

        if item.data(THUMBNAIL_PATH_ROLE) is None:
            return

        latitude = item.data(THUMBNAIL_LATITUDE_ROLE)
        longitude = item.data(THUMBNAIL_LONGITUDE_ROLE)

        menu = QMenu(self)

        has_gps = latitude is not None and longitude is not None

        copy_action = QAction("Copy GPS Coordinates", self)
        copy_action.setEnabled(has_gps)
        copy_action.triggered.connect(
            lambda: self.copy_gps_coordinates(latitude, longitude)
        )

        path = Path(item.data(THUMBNAIL_PATH_ROLE))
        use_action = QAction("Use This Location", self)
        use_action.setEnabled(has_gps)
        use_action.setToolTip("Put this photo's coordinates in New Location")
        use_action.triggered.connect(lambda: self.use_location_from_path(path))

        # Acts on the whole selection when this photo is part of it,
        # otherwise on just this photo.
        remove_paths = (
            set(self.get_selected_paths()) if item.isSelected() else {path}
        )
        remove_action = QAction("Remove from List", self)
        remove_action.setEnabled(not self.is_picking_location)
        remove_action.triggered.connect(lambda: self._remove_browser_paths(remove_paths))

        menu.addAction(copy_action)
        menu.addAction(use_action)
        menu.addSeparator()
        menu.addAction(remove_action)
        # popup(), not exec(): exec() blocks in a second event loop, where
        # background results arriving crashed the Windows build. The menu
        # deletes itself once closed (its actions belong to the window).
        menu.setAttribute(Qt.WA_DeleteOnClose)
        menu.popup(self.list_widget.viewport().mapToGlobal(position))

    def copy_gps_coordinates(
        self,
        latitude: float | None,
        longitude: float | None,
    ) -> None:
        if latitude is None or longitude is None:
            return

        QApplication.clipboard().setText(f"{latitude:.6f}, {longitude:.6f}")

    def copy_selected_photo_gps_coordinates(self) -> None:
        coordinates = self._selected_browser_gps_coordinates()
        if coordinates is None:
            return

        latitude, longitude = coordinates
        self.copy_gps_coordinates(latitude, longitude)

    def _selected_browser_gps_coordinates(self) -> tuple[float, float] | None:
        selected_paths = self.get_selected_paths()
        if len(selected_paths) != 1:
            return None

        info = self.session.loaded_photo_infos.get(selected_paths[0])
        if (
            info is None
            or info.current_latitude is None
            or info.current_longitude is None
        ):
            return None

        return info.current_latitude, info.current_longitude
