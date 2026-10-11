"""
Keeps the inspector panel in sync with the photos selected in the grid.
"""

from __future__ import annotations

from gui.presenters.inspector_state import InspectorState, build_inspector_state


class InspectorMixin:
    def update_details_panel(self) -> None:
        self._update_selection_metrics()
        state = self._build_inspector_state()
        self._apply_inspector_state(state)

    def _build_inspector_state(self) -> InspectorState:
        return build_inspector_state(
            selected_paths=self.get_selected_paths(),
            photo_infos=self.session.loaded_photo_infos,
            latitude_text=self.latitude_input.text(),
            longitude_text=self.longitude_input.text(),
            source_path=self._location_source,
        )

    def _apply_inspector_state(self, state: InspectorState) -> None:
        self.selection_title_label.setText(state.title)
        self.selection_gps_label.setText(state.gps_summary)

        single = state.selected_count == 1
        self.copy_location_button.setVisible(single)
        self.copy_location_button.setEnabled(state.can_use_location)

        has_fields = bool(self.latitude_input.text().strip() or self.longitude_input.text().strip())
        self.clear_location_button.setEnabled(has_fields)
        self._update_clipboard_buttons()

        self.apply_button.setText(state.apply_label)
        self.apply_button.setEnabled(state.can_apply)
        self.apply_hint_label.setText(state.apply_hint)
        self.apply_hint_label.setVisible(bool(state.apply_hint))
        self._set_tone(self.apply_hint_label, state.apply_hint_tone)

        self.remove_gps_button.setText(state.remove_gps_label)
        self.remove_gps_button.setEnabled(state.can_remove_gps)

        # The Date & Time tab, and the summary above the tabs while it shows
        # (dates instead of GPS; Copy is for GPS only). Only worked out while
        # it shows: switching to it updates it (see editor_tab_changed).
        if self.is_date_mode:
            date_state = self._build_date_time_state()
            self._apply_date_time_state(date_state)
            self.selection_title_label.setText(date_state.title)
            self.selection_gps_label.setText(date_state.summary)
            self.copy_location_button.setVisible(False)
        self._refresh_map()
        self._apply_pick_mode_lock()

    def _set_tone(self, widget, tone: str) -> None:
        if widget.property("tone") != tone:
            widget.setProperty("tone", tone)
            self._repolish(widget)

    @staticmethod
    def _repolish(widget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()
