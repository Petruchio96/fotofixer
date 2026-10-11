import unittest
from datetime import datetime, timedelta
from pathlib import Path

from core.models import PhotoInfo
from core.time_zones import ZONES_BY_KEY
from services.date_time_service import (
    cameras_in,
    date_tag_values,
    group_by_camera,
    photos_by_date,
    plan_set,
    plan_shift,
    plan_zone_change,
    saved_date_tags,
)


def info(name: str, taken: datetime | None, camera: str | None = None, tags=None, offset=None) -> PhotoInfo:
    return PhotoInfo(
        path=Path(f"/photos/{name}"), file_type="JPG", date_taken=taken, camera=camera,
        date_tags=tags or {}, time_offset=offset,
    )


class DateTimeServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.photos = [
            info("b.jpg", datetime(2026, 10, 3, 23, 50), "Canon EOS R6"),
            info("a.jpg", datetime(2026, 10, 3, 9, 14, 2), "Canon EOS R6"),
            info("scan.jpg", None, None),
            info("phone.jpg", datetime(2026, 10, 3, 10, 16, 12), "Apple iPhone 15 Pro"),
        ]
        self.infos = {photo.path: photo for photo in self.photos}
        self.paths = [photo.path for photo in self.photos]

    def path(self, name: str) -> Path:
        return Path(f"/photos/{name}")

    def test_photos_by_date_is_earliest_first_and_skips_undated(self) -> None:
        self.assertEqual(
            photos_by_date(self.infos, self.paths),
            [self.path("a.jpg"), self.path("phone.jpg"), self.path("b.jpg")],
        )
        self.assertEqual(
            photos_by_date(self.infos, self.paths, exclude=self.path("a.jpg"))[0],
            self.path("phone.jpg"),
        )

    def test_shift_moves_every_dated_photo_by_the_same_amount(self) -> None:
        plan = plan_shift(self.infos, self.paths, timedelta(hours=1, minutes=2, seconds=10))

        self.assertEqual(plan.new_dates[self.path("a.jpg")], datetime(2026, 10, 3, 10, 16, 12))
        # Crosses midnight into the next day.
        self.assertEqual(plan.new_dates[self.path("b.jpg")], datetime(2026, 10, 4, 0, 52, 10))
        self.assertEqual(plan.skipped_undated, [self.path("scan.jpg")])

    def test_shift_earlier_across_a_month_and_leap_day(self) -> None:
        photo = info("leap.jpg", datetime(2028, 3, 1, 0, 30))
        plan = plan_shift({photo.path: photo}, [photo.path], timedelta(hours=-1))
        self.assertEqual(plan.new_dates[photo.path], datetime(2028, 2, 29, 23, 30))

    def test_shift_leaves_out_the_source_photo(self) -> None:
        plan = plan_shift(self.infos, self.paths, timedelta(hours=1), exclude=self.path("phone.jpg"))
        self.assertNotIn(self.path("phone.jpg"), plan.new_dates)
        self.assertNotIn(self.path("phone.jpg"), plan.skipped_undated)

    def test_no_shift_changes_nothing(self) -> None:
        plan = plan_shift(self.infos, self.paths, timedelta(0))
        self.assertEqual(plan.new_dates, {})
        self.assertEqual(len(plan.unchanged), 3)

    def test_set_gives_every_photo_the_date_including_undated(self) -> None:
        value = datetime(1987, 6, 1, 12, 0)
        plan = plan_set(self.infos, self.paths, value)
        self.assertEqual(set(plan.new_dates), set(self.paths))
        self.assertTrue(all(new == value for new in plan.new_dates.values()))

        same = plan_set(self.infos, self.paths, datetime(2026, 10, 3, 9, 14, 2))
        self.assertEqual(same.unchanged, [self.path("a.jpg")])

    def test_tag_values_and_saved_tags(self) -> None:
        self.assertEqual(
            date_tag_values(datetime(2026, 10, 3, 10, 16, 12)),
            {
                "DateTimeOriginal": "2026:10:03 10:16:12",
                "CreateDate": "2026:10:03 10:16:12",
                "ModifyDate": "2026:10:03 10:16:12",
                "FileModifyDate": "2026:10:03 10:16:12",
            },
        )
        photo = info("x.jpg", None, tags={"DateTimeOriginal": "2026:10:03 09:14:02", "FileModifyDate": "2026:10:04 08:00:00-06:00"})
        self.assertEqual(
            saved_date_tags(photo),
            {
                "DateTimeOriginal": "2026:10:03 09:14:02",
                "CreateDate": None,
                "ModifyDate": None,
                "FileModifyDate": "2026:10:04 08:00:00-06:00",
                # Time zone tags are remembered too, for undo.
                "OffsetTimeOriginal": None,
                "OffsetTimeDigitized": None,
                "OffsetTime": None,
            },
        )

    def test_camera_groups_are_sorted_with_unknown_last(self) -> None:
        groups = group_by_camera(self.infos, self.paths)
        self.assertEqual(
            groups,
            [
                ("Apple iPhone 15 Pro", [self.path("phone.jpg")]),
                ("Canon EOS R6", [self.path("a.jpg"), self.path("b.jpg")]),
                ("Unknown Camera", [self.path("scan.jpg")]),
            ],
        )
        self.assertEqual(cameras_in(self.infos, self.paths), ["Apple iPhone 15 Pro", "Canon EOS R6", "Unknown Camera"])

    def test_undated_photos_come_last_in_their_group(self) -> None:
        undated = info("0-first-by-name.jpg", None, "Canon EOS R6")
        infos = {**self.infos, undated.path: undated}
        _, canon = group_by_camera(infos, [*self.paths, undated.path])[1]
        self.assertEqual(canon[-1], undated.path)


class TimeZoneShiftTests(unittest.TestCase):
    """Choosing a time zone: same moment, shown in that zone, zone written."""

    def test_choosing_a_zone_converts_to_the_same_moment(self) -> None:
        mountain = info("m.jpg", datetime(2026, 10, 3, 9, 0), offset=timedelta(hours=-6))
        plan = plan_shift({mountain.path: mountain}, [mountain.path], timedelta(0), zone=ZONES_BY_KEY["eastern"])
        self.assertEqual(plan.new_dates[mountain.path], datetime(2026, 10, 3, 11, 0))
        self.assertEqual(plan.new_offsets[mountain.path], timedelta(hours=-4))

    def test_daylight_saving_is_worked_out_per_photo(self) -> None:
        summer = info("s.jpg", datetime(2026, 10, 31, 12, 0), offset=timedelta(hours=-6))
        winter = info("w.jpg", datetime(2026, 11, 2, 12, 0), offset=timedelta(hours=-7))
        infos = {summer.path: summer, winter.path: winter}
        plan = plan_shift(infos, list(infos), timedelta(0), zone=ZONES_BY_KEY["mountain"])
        # Already in Mountain time on both dates: nothing changes.
        self.assertEqual(plan.new_dates, {})

    def test_photo_without_a_zone_keeps_its_clock_and_gets_the_zone(self) -> None:
        bare = info("b.jpg", datetime(2026, 10, 3, 9, 0))
        plan = plan_shift({bare.path: bare}, [bare.path], timedelta(hours=1), zone=ZONES_BY_KEY["paris"])
        self.assertEqual(plan.new_dates[bare.path], datetime(2026, 10, 3, 10, 0))
        self.assertEqual(plan.new_offsets[bare.path], timedelta(hours=2))

    def test_without_a_zone_offsets_are_left_alone(self) -> None:
        photo = info("m.jpg", datetime(2026, 10, 3, 9, 0), offset=timedelta(hours=-6))
        plan = plan_shift({photo.path: photo}, [photo.path], timedelta(hours=1))
        self.assertEqual(plan.new_offsets, {})
        self.assertNotIn("OffsetTimeOriginal", date_tag_values(plan.new_dates[photo.path]))

    def test_set_in_a_zone_and_the_offset_tags_written(self) -> None:
        photo = info("x.jpg", None)
        plan = plan_set({photo.path: photo}, [photo.path], datetime(2026, 7, 4, 20, 0), zone=ZONES_BY_KEY["central"])
        self.assertEqual(plan.new_offsets[photo.path], timedelta(hours=-5))
        values = date_tag_values(plan.new_dates[photo.path], plan.new_offsets[photo.path])
        self.assertEqual(values["OffsetTimeOriginal"], "-05:00")
        self.assertEqual(values["OffsetTime"], "-05:00")



class ZoneChangeTests(unittest.TestCase):
    """Change Time Zone: the same moment by default, or the same clock time."""

    def setUp(self) -> None:
        # The wedding photos: right clock time (Central), wrong zone (MDT).
        self.wedding = info("w.jpg", datetime(2026, 5, 23, 11, 16, 41), offset=timedelta(hours=-6))
        self.no_zone = info("n.jpg", datetime(2026, 5, 23, 11, 30, 10))
        self.undated = info("u.jpg", None)
        self.infos = {p.path: p for p in (self.wedding, self.no_zone, self.undated)}
        self.paths = list(self.infos)

    def test_same_moment_changes_the_clock(self) -> None:
        plan = plan_zone_change(self.infos, self.paths, ZONES_BY_KEY["central"])
        self.assertEqual(plan.new_dates[self.wedding.path], datetime(2026, 5, 23, 12, 16, 41))
        self.assertEqual(plan.new_offsets[self.wedding.path], timedelta(hours=-5))

    def test_keep_clock_changes_only_the_zone(self) -> None:
        plan = plan_zone_change(self.infos, self.paths, ZONES_BY_KEY["central"], keep_clock=True)
        self.assertEqual(plan.new_dates[self.wedding.path], datetime(2026, 5, 23, 11, 16, 41))
        self.assertEqual(plan.new_offsets[self.wedding.path], timedelta(hours=-5))

    def test_photo_without_a_zone_keeps_its_clock_either_way(self) -> None:
        for keep_clock in (False, True):
            plan = plan_zone_change(self.infos, self.paths, ZONES_BY_KEY["central"], keep_clock=keep_clock)
            self.assertEqual(plan.new_dates[self.no_zone.path], datetime(2026, 5, 23, 11, 30, 10))
            self.assertEqual(plan.new_offsets[self.no_zone.path], timedelta(hours=-5))

    def test_undated_photos_are_skipped(self) -> None:
        for keep_clock in (False, True):
            plan = plan_zone_change(self.infos, self.paths, ZONES_BY_KEY["central"], keep_clock=keep_clock)
            self.assertEqual(plan.skipped_undated, [self.undated.path])
            self.assertNotIn(self.undated.path, plan.new_dates)

    def test_photos_already_in_the_zone_are_unchanged(self) -> None:
        for keep_clock in (False, True):
            plan = plan_zone_change(self.infos, [self.wedding.path], ZONES_BY_KEY["mountain"], keep_clock=keep_clock)
            self.assertEqual(plan.new_dates, {})
            self.assertEqual(plan.unchanged, [self.wedding.path])

    def test_to_europe_across_daylight_saving(self) -> None:
        # Paris changes clocks on 2026-10-25, Denver on 2026-11-01.
        before = info("b.jpg", datetime(2026, 10, 24, 10, 5), offset=timedelta(hours=-6))
        between = info("m.jpg", datetime(2026, 10, 28, 10, 5), offset=timedelta(hours=-6))
        infos = {before.path: before, between.path: between}
        plan = plan_zone_change(infos, list(infos), ZONES_BY_KEY["paris"])
        self.assertEqual(plan.new_dates[before.path], datetime(2026, 10, 24, 18, 5))
        self.assertEqual(plan.new_offsets[before.path], timedelta(hours=2))
        self.assertEqual(plan.new_dates[between.path], datetime(2026, 10, 28, 17, 5))
        self.assertEqual(plan.new_offsets[between.path], timedelta(hours=1))


if __name__ == "__main__":
    unittest.main()
