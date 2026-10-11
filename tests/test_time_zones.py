import unittest
from datetime import datetime, timedelta

from core.time_zones import (
    EASTERN,
    ZONES,
    ZONES_BY_KEY,
    abbreviation,
    default_zone,
    describe_offset,
    format_offset,
    offset_at_local,
    offset_short,
    parse_offset,
    to_zone,
    zone_for_offset,
    zone_label,
)

H = lambda hours: timedelta(hours=hours)
OCTOBER = datetime(2026, 10, 3, 9, 0)
JANUARY = datetime(2026, 1, 15, 9, 0)


class OffsetTextTests(unittest.TestCase):
    def test_parse_and_format(self) -> None:
        self.assertEqual(parse_offset("-06:00"), H(-6))
        self.assertEqual(parse_offset("+05:30"), timedelta(hours=5, minutes=30))
        self.assertEqual(parse_offset("+00:00"), timedelta(0))
        for bad in (None, "", "6", "-6:00", "+15:00", "abc"):
            self.assertIsNone(parse_offset(bad))
        self.assertEqual(format_offset(H(-6)), "-06:00")
        self.assertEqual(format_offset(timedelta(hours=-3, minutes=-30)), "-03:30")
        self.assertEqual(offset_short(H(-6)), "UTC−6")
        self.assertEqual(offset_short(timedelta(hours=5, minutes=30)), "UTC+5:30")
        self.assertEqual(offset_short(timedelta(0)), "UTC")


class ZoneTests(unittest.TestCase):
    def test_list_runs_east_to_west_without_repeats(self) -> None:
        # By standard (winter) offset: summer time can reorder the southern zones.
        offsets = [zone.standard_hours for zone in ZONES]
        self.assertEqual(offsets, sorted(offsets, reverse=True))
        patterns = [(offset_at_local(z, JANUARY), offset_at_local(z, OCTOBER)) for z in ZONES]
        repeats = {p for p in patterns if patterns.count(p) > 1}
        # Only UTC and London share winter time; London has summer time.
        self.assertEqual(repeats, set())

    def test_daylight_saving_per_date(self) -> None:
        mountain = ZONES_BY_KEY["mountain"]
        self.assertEqual(offset_at_local(mountain, OCTOBER), H(-6))
        self.assertEqual(offset_at_local(mountain, JANUARY), H(-7))
        self.assertEqual(abbreviation(mountain, OCTOBER), "MDT")
        self.assertEqual(zone_label(mountain, JANUARY), "Mountain Time (Denver) — MST")
        self.assertEqual(zone_label(mountain, OCTOBER), "Mountain Time (Denver) — MDT")
        self.assertEqual(zone_label(ZONES_BY_KEY["dubai"], OCTOBER), "Gulf (Dubai) — UTC+4")

    def test_offset_means_a_us_zone_on_that_date(self) -> None:
        self.assertEqual(zone_for_offset(H(-6), OCTOBER).key, "mountain")
        self.assertEqual(zone_for_offset(H(-6), JANUARY).key, "central")
        self.assertEqual(zone_for_offset(H(2), OCTOBER).key, "paris")
        self.assertIsNone(zone_for_offset(H(-11), OCTOBER))
        self.assertEqual(describe_offset(H(-6), OCTOBER), "MDT")
        self.assertEqual(describe_offset(H(-11), OCTOBER), "UTC−11")

    def test_to_zone_keeps_the_moment(self) -> None:
        clock, offset = to_zone(datetime(2026, 10, 3, 15, 0), ZONES_BY_KEY["eastern"])
        self.assertEqual((clock, offset), (datetime(2026, 10, 3, 11, 0), H(-4)))


class DefaultZoneTests(unittest.TestCase):
    def default(self, photos, computer=H(-6), now=OCTOBER):
        return default_zone(photos, computer_offset=computer, now=now)

    def test_no_photos_uses_the_computers_zone(self) -> None:
        self.assertEqual(self.default([]).key, "mountain")
        self.assertEqual(self.default([], computer=H(-6), now=JANUARY).key, "central")

    def test_never_defaults_east_of_eastern(self) -> None:
        self.assertEqual(self.default([], computer=H(2)), EASTERN)
        self.assertEqual(self.default([(OCTOBER, H(2)), (OCTOBER, H(2))]), EASTERN)

    def test_no_photo_has_a_zone(self) -> None:
        self.assertIsNone(self.default([(OCTOBER, None), (None, None)]))

    def test_the_most_common_zone(self) -> None:
        photos = [(OCTOBER, H(-6)), (OCTOBER, H(-6)), (OCTOBER, H(-4)), (OCTOBER, None)]
        self.assertEqual(self.default(photos).key, "mountain")

    def test_a_tie_goes_to_the_earliest_photos_zone(self) -> None:
        photos = [(datetime(2026, 10, 3, 12), H(-6)), (datetime(2026, 10, 3, 8), H(-7))]
        self.assertEqual(self.default(photos).key, "pacific")

    def test_an_unlisted_western_offset_falls_back_to_the_computer(self) -> None:
        self.assertEqual(self.default([(OCTOBER, H(-11))]).key, "mountain")


if __name__ == "__main__":
    unittest.main()
