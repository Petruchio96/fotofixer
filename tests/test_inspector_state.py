import unittest
from pathlib import Path

from core.models import GpsCoordinates, PhotoInfo
from gui.presenters.inspector_state import build_inspector_state

WITH_GPS = Path("/tmp/with-gps.jpg")
NO_GPS = Path("/tmp/no-gps.jpg")
OTHER_NO_GPS = Path("/tmp/other.jpg")

INFOS = {
    WITH_GPS: PhotoInfo(WITH_GPS, "JPG", 40.5, -111.8),
    NO_GPS: PhotoInfo(NO_GPS, "JPG"),
    OTHER_NO_GPS: PhotoInfo(OTHER_NO_GPS, "JPG"),
}


def state(selected, latitude="", longitude=""):
    return build_inspector_state(
        selected_paths=list(selected),
        photo_infos=INFOS,
        latitude_text=latitude,
        longitude_text=longitude,
    )


class InspectorStateTests(unittest.TestCase):
    def test_nothing_selected(self) -> None:
        result = state([])

        self.assertEqual(result.title, "No Photos Selected")
        self.assertFalse(result.can_apply)
        self.assertEqual(result.apply_label, "Apply Location to Selected Photos")
        self.assertEqual(result.apply_hint, "Select the photos to change in the Photo List.")
        self.assertFalse(result.can_remove_gps)
        self.assertEqual(result.remove_gps_label, "Remove GPS from Selected Photos")

    def test_single_photo_with_gps(self) -> None:
        result = state([WITH_GPS])

        self.assertEqual(result.title, "1 Photo Selected")
        self.assertEqual(result.gps_summary, "with-gps.jpg · GPS: 40.500000, -111.800000")
        self.assertEqual(result.single_photo_coordinates, GpsCoordinates(40.5, -111.8))
        self.assertTrue(result.can_use_location)
        self.assertEqual(result.remove_gps_label, "Remove GPS from Selected 1 Photo")

    def test_single_photo_without_gps(self) -> None:
        result = state([NO_GPS])

        self.assertEqual(result.gps_summary, "no-gps.jpg · No GPS")
        self.assertFalse(result.can_use_location)
        self.assertFalse(result.can_remove_gps)

    def test_multiple_photos_gps_summary(self) -> None:
        self.assertEqual(
            state([WITH_GPS, NO_GPS]).gps_summary,
            "1 without GPS · 1 with GPS",
        )
        self.assertEqual(
            state([NO_GPS, OTHER_NO_GPS]).gps_summary,
            "2 without GPS · 0 with GPS",
        )
        self.assertEqual(state([WITH_GPS]).title, "1 Photo Selected")
        self.assertEqual(state([NO_GPS, OTHER_NO_GPS]).title, "2 Photos Selected")

    def test_needs_location_before_apply(self) -> None:
        result = state([NO_GPS])

        self.assertFalse(result.can_apply)
        self.assertEqual(result.apply_hint_tone, "info")
        self.assertIn("Set a new location", result.apply_hint)

    def test_invalid_location_is_an_error(self) -> None:
        result = state([NO_GPS], "95", "10")

        self.assertFalse(result.can_apply)
        self.assertIsNone(result.new_location)
        self.assertEqual(result.apply_hint_tone, "error")

    def test_ready_to_apply(self) -> None:
        result = state([NO_GPS, OTHER_NO_GPS], "40.1", "-111.2")

        self.assertTrue(result.can_apply)
        self.assertEqual(result.apply_label, "Apply Location to 2 Photos")
        self.assertEqual(result.new_location, GpsCoordinates(40.1, -111.2))
        self.assertEqual(result.apply_hint, "")
        self.assertEqual(result.overwrite_count, 0)

    def test_overwrite_warning(self) -> None:
        result = state([WITH_GPS, NO_GPS], "40.1", "-111.2")

        self.assertTrue(result.can_apply)
        self.assertEqual(result.overwrite_count, 1)
        self.assertEqual(result.apply_hint, "1 photo already has GPS, which will be replaced.")
        self.assertEqual(result.apply_hint_tone, "warning")

    def test_overwrite_warning_plural(self) -> None:
        infos = dict(INFOS)
        second = Path("/tmp/second-gps.jpg")
        infos[second] = PhotoInfo(second, "JPG", 1.0, 2.0)

        result = build_inspector_state(
            selected_paths=[WITH_GPS, second],
            photo_infos=infos,
            latitude_text="40.1",
            longitude_text="-111.2",
        )

        self.assertEqual(result.apply_hint, "2 photos already have GPS, which will be replaced.")
        self.assertEqual(result.remove_gps_label, "Remove GPS from Selected 2 Photos")

    def test_source_photo_alone_cannot_be_applied_to(self) -> None:
        # The location was copied from the one selected photo: nothing to change.
        result = build_inspector_state(
            selected_paths=[WITH_GPS],
            photo_infos=INFOS,
            latitude_text="40.5",
            longitude_text="-111.8",
            source_path=WITH_GPS,
        )

        self.assertFalse(result.can_apply)
        self.assertEqual(result.apply_label, "Apply Location to Selected Photos")
        self.assertIn("is the source of the new location", result.apply_hint)
        self.assertEqual(result.overwrite_count, 0)

    def test_source_photo_is_left_out_of_apply(self) -> None:
        result = build_inspector_state(
            selected_paths=[WITH_GPS, NO_GPS, OTHER_NO_GPS],
            photo_infos=INFOS,
            latitude_text="40.5",
            longitude_text="-111.8",
            source_path=WITH_GPS,
        )

        self.assertTrue(result.can_apply)
        self.assertEqual(result.apply_label, "Apply Location to 2 Photos")
        # The source has GPS, but it isn't replaced, so no overwrite warning.
        self.assertEqual(result.overwrite_count, 0)
        self.assertEqual(result.apply_hint, "The source photo isn't changed.")

    def test_unselected_source_changes_nothing(self) -> None:
        result = build_inspector_state(
            selected_paths=[NO_GPS],
            photo_infos=INFOS,
            latitude_text="40.5",
            longitude_text="-111.8",
            source_path=WITH_GPS,
        )

        self.assertTrue(result.can_apply)
        self.assertEqual(result.apply_label, "Apply Location to 1 Photo")
        self.assertEqual(result.apply_hint, "")


if __name__ == "__main__":
    unittest.main()
