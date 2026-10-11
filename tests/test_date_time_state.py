import unittest
from datetime import datetime, timedelta
from pathlib import Path

from core.models import PhotoInfo
from gui.presenters.date_time_state import MODE_SET, MODE_SHIFT, MODE_ZONE, build_date_time_state, describe_shift


def photo(name: str, taken: datetime | None, camera: str | None = "Canon EOS R6", offset=None) -> PhotoInfo:
    return PhotoInfo(path=Path(f"/photos/{name}"), file_type="JPG", date_taken=taken, camera=camera, time_offset=offset)


class DateTimeStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.infos = {
            p.path: p
            for p in (
                photo("IMG_2.CR3", datetime(2026, 10, 3, 9, 15, 40)),
                photo("IMG_1.CR3", datetime(2026, 10, 3, 9, 14, 2)),
                photo("IMG_8801.jpg", datetime(2026, 10, 3, 10, 16, 12), "Apple iPhone 15 Pro"),
                photo("scan.jpg", None, None),
            )
        }

    def path(self, name: str) -> Path:
        return Path(f"/photos/{name}")

    def state(self, names, *, mode=MODE_SHIFT, reference=None, shift=timedelta(0), source=None, set_value=datetime(2000, 1, 1)):
        return build_date_time_state(
            selected_paths=[self.path(name) for name in names],
            photo_infos=self.infos,
            mode=mode,
            reference=self.path(reference) if reference else None,
            shift=shift,
            set_value=set_value,
            source=self.path(source) if source else None,
        )

    def test_reference_is_the_earliest_selected(self) -> None:
        state = self.state(["IMG_2.CR3", "IMG_1.CR3"])

        self.assertEqual(state.reference, self.path("IMG_1.CR3"))
        self.assertEqual(state.reference_title, "IMG_1.CR3 · Canon EOS R6")
        self.assertEqual(state.reference_detail, "Current Date: 10/03/2026 9:14:02am")
        self.assertTrue(state.reference_is_earliest)
        self.assertEqual(state.reference_position, "1 of 2")
        self.assertFalse(state.can_step_back)
        self.assertTrue(state.can_step_forward)

    def test_chosen_reference_and_corrected_date(self) -> None:
        state = self.state(["IMG_2.CR3", "IMG_1.CR3"], reference="IMG_2.CR3", shift=timedelta(hours=1))
        self.assertEqual(state.reference_position, "2 of 2")
        self.assertFalse(state.reference_is_earliest)
        self.assertEqual(state.corrected_reference, datetime(2026, 10, 3, 10, 15, 40))

    def test_rows_show_a_new_date_only_when_it_changes(self) -> None:
        unchanged = self.state(["IMG_1.CR3", "IMG_2.CR3"])
        self.assertEqual([row.new for row in unchanged.rows], ["", ""])
        self.assertFalse(unchanged.can_apply)

        shifted = self.state(["IMG_1.CR3", "IMG_2.CR3"], shift=timedelta(hours=1, minutes=2, seconds=10))
        self.assertEqual(
            [(row.name, row.current, row.new) for row in shifted.rows],
            [
                ("IMG_1.CR3", "10/03/2026 9:14:02am", "10/03/2026 10:16:12am"),
                ("IMG_2.CR3", "10/03/2026 9:15:40am", "10/03/2026 10:17:50am"),
            ],
        )
        self.assertTrue(shifted.can_apply)
        self.assertEqual(shifted.apply_label, "Shift 2 Photos")

    def test_source_photo_is_not_changed(self) -> None:
        state = self.state(["IMG_1.CR3", "IMG_8801.jpg"], shift=timedelta(hours=1), source="IMG_8801.jpg")
        self.assertTrue(state.source_selected)
        self.assertNotIn(self.path("IMG_8801.jpg"), state.plan.new_dates)
        self.assertEqual(state.rows[-1].new, "Source, not changed")
        self.assertEqual(state.apply_label, "Shift 1 Photo")
        # The source's camera doesn't count toward the mixed-camera warning.
        self.assertNotIn("cameras", state.hint)

    def test_warnings_for_mixed_cameras_and_undated_photos(self) -> None:
        state = self.state(["IMG_1.CR3", "IMG_8801.jpg", "scan.jpg"], shift=timedelta(hours=1))
        self.assertEqual(state.hint_tone, "warning")
        self.assertIn("These photos come from 3 cameras: Apple iPhone 15 Pro, Canon EOS R6, Unknown Camera.", state.hint)
        self.assertIn("1 photo without a date will be skipped", state.hint)
        self.assertEqual(state.rows[-1].new, "Skipped")

    def test_set_mode_changes_every_photo_including_undated(self) -> None:
        state = self.state(["IMG_1.CR3", "scan.jpg"], mode=MODE_SET, set_value=datetime(1987, 6, 1, 12, 0))
        self.assertEqual(state.apply_label, "Set Date on 2 Photos")
        self.assertEqual(len(state.plan.new_dates), 2)
        self.assertEqual({row.new for row in state.rows}, {"06/01/1987 12:00:00pm"})
        # Mixed cameras only matter for a shift.
        mixed = self.state(["IMG_1.CR3", "IMG_8801.jpg"], mode=MODE_SET, set_value=datetime(1987, 6, 1))
        self.assertEqual(mixed.hint, "")

    def test_summary(self) -> None:
        self.assertEqual(self.state([]).title, "No Photos Selected")
        one = self.state(["IMG_1.CR3"])
        self.assertEqual(one.summary, "IMG_1.CR3 · Taken 10/03/2026 9:14:02am")
        many = self.state(["IMG_1.CR3", "IMG_2.CR3"])
        self.assertEqual(many.summary, "10/03/2026 9:14:02am – 10/03/2026 9:15:40am · Canon EOS R6")

    def test_describe_shift(self) -> None:
        self.assertEqual(describe_shift(timedelta(0)), "")
        self.assertEqual(describe_shift(timedelta(hours=1, minutes=2, seconds=10)), "1 h 2 min 10 s later")
        self.assertEqual(describe_shift(-timedelta(days=1, hours=1)), "1 day 1 h earlier")


class TimeZoneStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.infos = {
            p.path: p
            for p in (
                photo("m1.jpg", datetime(2026, 10, 3, 9, 0), offset=timedelta(hours=-6)),
                photo("m2.jpg", datetime(2026, 10, 3, 9, 30), offset=timedelta(hours=-6)),
                photo("e1.jpg", datetime(2026, 10, 3, 11, 0), offset=timedelta(hours=-4)),
                photo("bare.jpg", datetime(2026, 10, 3, 8, 0)),
            )
        }

    def state(self, names, *, zone=None, shift=timedelta(0), mode=MODE_SHIFT, keep_clock=False, source=None):
        from core.time_zones import ZONES_BY_KEY

        return build_date_time_state(
            selected_paths=[Path(f"/photos/{n}") for n in names],
            photo_infos=self.infos,
            mode=mode,
            keep_clock=keep_clock,
            reference=None,
            shift=shift,
            set_value=datetime(2026, 10, 3),
            source=Path(f"/photos/{source}") if source else None,
            zone=ZONES_BY_KEY[zone] if zone else None,
            now=datetime(2026, 10, 3, 12, 0),
            computer_offset=timedelta(hours=-6),
        )

    def test_default_is_the_selected_photos_zone(self) -> None:
        state = self.state(["m1.jpg", "m2.jpg"])
        self.assertEqual(state.zone_key, "mountain")
        self.assertFalse(state.zone_mixed)
        self.assertNotIn("", [key for key, _ in state.zone_items])
        self.assertEqual(state.reference_detail, "Current Date: 10/03/2026 9:00:00am MDT")

    def test_mixed_zones_are_flagged(self) -> None:
        state = self.state(["m1.jpg", "e1.jpg"])
        self.assertTrue(state.zone_mixed)
        self.assertIn("more than one time zone", state.zone_tooltip)
        # A tie: the earliest photo's zone (m1, 9:00).
        self.assertEqual(state.zone_key, "mountain")

    def test_no_zones_offers_no_time_zone(self) -> None:
        state = self.state(["bare.jpg"])
        self.assertEqual(state.zone_key, "")
        self.assertEqual(state.zone_items[0], ("", "No time zone"))

    def test_blank_until_a_photo_is_selected(self) -> None:
        state = self.state([])
        self.assertEqual(state.zone_key, "")
        self.assertEqual(state.zone_items[0], ("", ""))
        self.assertFalse(state.zone_mixed)

    def test_choosing_a_zone_shows_the_same_moment_and_lists_zones(self) -> None:
        state = self.state(["m1.jpg"], zone="eastern")
        self.assertEqual(state.corrected_reference, datetime(2026, 10, 3, 11, 0))
        self.assertEqual(
            [(row.current, row.new) for row in state.rows],
            [("10/03/2026 9:00:00am MDT", "10/03/2026 11:00:00am EDT")],
        )
        self.assertTrue(state.can_apply)


    # --- Change Time Zone ------------------------------------------------------

    def test_zone_mode_keeps_the_moment_by_default(self) -> None:
        state = self.state(["m1.jpg", "bare.jpg"], mode=MODE_ZONE, zone="central")
        self.assertEqual(
            [(row.current, row.new) for row in state.rows],
            [
                ("10/03/2026 8:00:00am", "10/03/2026 8:00:00am CDT (time kept, time zone added)"),
                ("10/03/2026 9:00:00am MDT", "10/03/2026 10:00:00am CDT"),
            ],
        )
        self.assertEqual(state.apply_label, "Change Time Zone of 2 Photos")
        self.assertTrue(state.can_apply)

    def test_zone_mode_can_keep_the_clock_time(self) -> None:
        state = self.state(["m1.jpg"], mode=MODE_ZONE, zone="central", keep_clock=True)
        self.assertEqual(
            [(row.current, row.new) for row in state.rows],
            [("10/03/2026 9:00:00am MDT", "10/03/2026 9:00:00am CDT")],
        )

    def test_zone_mode_starts_on_the_default_zone_and_changes_nothing(self) -> None:
        state = self.state(["m1.jpg", "m2.jpg"], mode=MODE_ZONE)
        self.assertEqual(state.zone_key, "mountain")
        self.assertFalse(state.can_apply)
        self.assertIn("already in this time zone", state.hint)

    def test_zone_mode_ignores_the_time_source(self) -> None:
        state = self.state(["m1.jpg", "m2.jpg"], mode=MODE_ZONE, zone="central", source="m2.jpg")
        self.assertFalse(state.source_selected)
        self.assertEqual(len(state.plan.new_dates), 2)


if __name__ == "__main__":
    unittest.main()
