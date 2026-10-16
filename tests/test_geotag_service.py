import unittest
from datetime import datetime, timedelta
from pathlib import Path

from core.gpx_track import TrackPoint
from core.models import PhotoInfo
from services.geotag_service import (
    AFTER,
    BEFORE,
    GAP,
    NO_DATE,
    ON_TRACK,
    READING,
    build_geotag_plan,
    describe_duration,
    format_coordinates,
    geotag_values,
    nothing_matches_hint,
)

MDT = timedelta(hours=-6)
PDT = timedelta(hours=-7)


def utc(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 10, 3, hour, minute, second)


def info(name: str, taken: datetime | None, offset: timedelta | None = None, gps=None) -> PhotoInfo:
    latitude, longitude = gps if gps else (None, None)
    return PhotoInfo(
        path=Path(f"/photos/{name}"), file_type="JPG", date_taken=taken, time_offset=offset,
        current_latitude=latitude, current_longitude=longitude,
    )


# A straight track from 15:12 to 15:42 UTC (9:12 to 9:42 MDT), then a two-hour gap.
TRACK = [
    TrackPoint(utc(15, 12), 40.60, -111.60, 2000.0),
    TrackPoint(utc(15, 22), 40.61, -111.59, 2100.0),
    TrackPoint(utc(15, 32), 40.62, -111.58, 2200.0),
    TrackPoint(utc(15, 42), 40.63, -111.57, 2300.0),
    TrackPoint(utc(17, 42), 40.70, -111.50, 2600.0),
]


class GeotagPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.photos = {
            # Its own zone (a phone): 9:17 MDT = 15:17 UTC, halfway between the first two points.
            "phone.jpg": info("phone.jpg", datetime(2026, 10, 3, 9, 17), MDT),
            # No zone: the computer's (MDT) stands in. 9:27 MDT, halfway between points 2 and 3.
            "canon.cr3": info("canon.cr3", datetime(2026, 10, 3, 9, 27)),
            # Already has GPS, on the track.
            "tagged.jpg": info("tagged.jpg", datetime(2026, 10, 3, 9, 37), MDT, gps=(40.5, -111.5)),
            # A Pacific-zone photo at the same moment as canon.cr3 (8:27 PDT).
            "pacific.jpg": info("pacific.jpg", datetime(2026, 10, 3, 8, 27), PDT),
            "early.jpg": info("early.jpg", datetime(2026, 10, 3, 7, 0), MDT),
            "late.jpg": info("late.jpg", datetime(2026, 10, 3, 12, 30), MDT),
            "paused.jpg": info("paused.jpg", datetime(2026, 10, 3, 10, 40), MDT),
            "scan.jpg": info("scan.jpg", None),
        }
        self.infos = {photo.path: photo for photo in self.photos.values()}
        self.paths = [photo.path for photo in self.photos.values()] + [Path("/photos/reading.cr3")]

    def plan(self, **kwargs):
        return build_geotag_plan(self.paths, self.infos, TRACK, MDT, **kwargs)

    def test_rows_are_oldest_first_with_undated_and_reading_last(self) -> None:
        plan = self.plan()
        self.assertEqual(
            [(row.name, row.status) for row in plan.rows],
            [
                ("early.jpg", BEFORE), ("phone.jpg", ON_TRACK), ("canon.cr3", ON_TRACK), ("pacific.jpg", ON_TRACK),
                ("tagged.jpg", ON_TRACK), ("paused.jpg", GAP), ("late.jpg", AFTER), ("scan.jpg", NO_DATE),
                ("reading.cr3", READING),
            ],
        )
        self.assertEqual(plan.summary(), "4 of 9 photos on the track")
        self.assertEqual(plan.track_span_text(), "10/03/2026 9:12:00am – 11:42:00am MDT")
        self.assertEqual((plan.photo_start, plan.photo_end), (utc(13, 0), utc(18, 30)))

    def test_positions_use_each_photos_zone_or_the_computers(self) -> None:
        rows = {row.name: row for row in self.plan().rows}
        self.assertAlmostEqual(rows["phone.jpg"].latitude, 40.605)
        self.assertAlmostEqual(rows["phone.jpg"].altitude, 2050.0)
        self.assertAlmostEqual(rows["canon.cr3"].latitude, 40.615)
        self.assertAlmostEqual(rows["pacific.jpg"].latitude, 40.615, msg="the same moment in another zone")
        self.assertEqual(rows["phone.jpg"].time_text, "10/03/2026 9:17:00am MDT")
        self.assertEqual(rows["canon.cr3"].time_text, "10/03/2026 9:27:00am MDT")
        self.assertEqual(rows["pacific.jpg"].time_text, "10/03/2026 8:27:00am PDT")
        self.assertIn("Will be placed at 40.605000, -111.595000 · 6,726 ft, between the track's points at 9:12:00am and 9:22:00am.", rows["phone.jpg"].hint)
        metres = build_geotag_plan(self.paths, self.infos, TRACK, MDT, feet=False)
        self.assertIn("· 2,050 m, between", {row.name: row for row in metres.rows}["phone.jpg"].hint)
        self.assertIn("between the track's points at 8:22:00am and 8:32:00am", rows["pacific.jpg"].hint)

    def test_chips_and_hints_for_photos_off_the_track(self) -> None:
        rows = {row.name: row for row in self.plan().rows}
        self.assertEqual(rows["early.jpg"].chip, "Before the Track")
        self.assertIn("Taken 2 h 12 min before the track starts (9:12:00am).", rows["early.jpg"].hint)
        self.assertIn("Date & Time tab", rows["early.jpg"].hint)
        self.assertNotIn("no time zone", rows["early.jpg"].hint)
        self.assertEqual(rows["late.jpg"].chip, "After the Track")
        self.assertIn("Taken 48 min after the track ends (11:42:00am).", rows["late.jpg"].hint)
        self.assertEqual(rows["paused.jpg"].chip, "In a Gap")
        self.assertIn("the track paused", rows["paused.jpg"].hint)
        self.assertEqual(rows["scan.jpg"].chip, "No Date")
        self.assertEqual(rows["reading.cr3"].chip, "Reading…")
        # A photo without a zone is told which zone stood in.
        # (9:27 as Hawaii time is 19:27 UTC, after the track.)
        no_zone = build_geotag_plan([self.photos["canon.cr3"].path], self.infos, TRACK, timedelta(hours=-10)).rows[0]
        self.assertEqual(no_zone.status, AFTER)
        self.assertIn("taken as this computer's zone (HST)", no_zone.hint)

    def test_suggested_track_location_needs_a_point_within_5_minutes_and_a_real_difference(self) -> None:
        # Track points every 10 minutes from 9:12 MDT: 9:17 is 5 min from both (within).
        rows = {row.name: row for row in self.plan().rows}
        self.assertTrue(rows["phone.jpg"].near_track)
        self.assertTrue(rows["tagged.jpg"].suggested, "9:37, far from its own (40.5, -111.5)")
        # Past the last point (11:42 MDT) but still matched to it: 4 min 59 s and 5 min 1 s after.
        far = info("far.jpg", datetime(2026, 10, 3, 11, 46, 59), MDT, gps=(40.5, -111.5))
        late = info("late.jpg", datetime(2026, 10, 3, 11, 47, 1), MDT, gps=(40.5, -111.5))
        # 9:12 is the first point (40.60, -111.60): 24 m and 26 m north of it.
        close = info("close.jpg", datetime(2026, 10, 3, 9, 12), MDT, gps=(40.60 + 24 / 111_195, -111.60))
        apart = info("apart.jpg", datetime(2026, 10, 3, 9, 12), MDT, gps=(40.60 + 26 / 111_195, -111.60))
        plan = build_geotag_plan([p.path for p in (far, late, close, apart)], {p.path: p for p in (far, late, close, apart)}, TRACK, MDT)
        by_name = {row.name: row for row in plan.rows}
        self.assertTrue(by_name["far.jpg"].suggested, "4 min 59 s from a point")
        self.assertFalse(by_name["late.jpg"].suggested, "5 min 1 s from a point")
        self.assertFalse(by_name["close.jpg"].suggested, "the track agrees within 25 m")
        self.assertAlmostEqual(by_name["close.jpg"].distance, 24, delta=0.5)
        self.assertTrue(by_name["apart.jpg"].suggested)
        self.assertIn("within 5 min of when it was taken", by_name["far.jpg"].hint)
        self.assertIn("check the box to use it", by_name["far.jpg"].hint)
        self.assertIn("Check the box to replace", by_name["late.jpg"].hint)
        self.assertIn("agrees within 79 ft, so its own coordinates are kept", by_name["close.jpg"].hint)
        # Check All takes photos without GPS and suggested ones, not the close one.
        self.assertEqual(sorted(row.name for row in plan.rows if row.checkable), ["apart.jpg", "far.jpg"])
        self.assertTrue(rows["phone.jpg"].checkable)

    def test_has_gps_rows(self) -> None:
        rows = {row.name: row for row in self.plan().rows}
        tagged = rows["tagged.jpg"]
        self.assertTrue(tagged.has_gps)
        self.assertEqual(tagged.chip, "Has GPS")
        self.assertIn("already has GPS coordinates (40.500000, -111.500000)", tagged.hint)
        self.assertFalse(tagged.included, "a photo with GPS starts unchecked")
        self.assertIn("check the box to use it", tagged.hint, "kilometres from its own GPS: suggested")
        self.assertIn("(40.625000, -111.575000 · 7,382 ft)", tagged.hint)
        self.assertFalse(rows["phone.jpg"].has_gps)

    def test_included_defaults_and_values(self) -> None:
        plan = self.plan()
        self.assertEqual([row.name for row in plan.included], ["phone.jpg", "canon.cr3", "pacific.jpg"])
        plan.set_included(self.photos["canon.cr3"].path, False)
        plan.set_included(self.photos["tagged.jpg"].path, True)
        plan.set_included(self.photos["scan.jpg"].path, True)  # not on the track: ignored
        self.assertEqual([row.name for row in plan.included], ["phone.jpg", "pacific.jpg", "tagged.jpg"])
        self.assertIn("Geotag will ask before replacing", [row for row in plan.rows if row.name == "tagged.jpg"][0].hint)
        self.assertIn("Left out: check the box to geotag it.", [row for row in plan.rows if row.name == "canon.cr3"][0].hint)
        values = geotag_values(plan)
        self.assertEqual(set(values), {self.photos[n].path for n in ("phone.jpg", "pacific.jpg", "tagged.jpg")})
        latitude, longitude, altitude = values[self.photos["phone.jpg"].path]
        self.assertAlmostEqual(latitude, 40.605)
        self.assertAlmostEqual(longitude, -111.595)
        self.assertAlmostEqual(altitude, 2050.0)
        # Rebuilding (after Add More Photos) keeps the checks.
        again = self.plan(previous=plan)
        self.assertEqual([row.name for row in again.included], ["phone.jpg", "pacific.jpg", "tagged.jpg"])

    def test_nothing_matches_hints(self) -> None:
        self.assertEqual(nothing_matches_hint(self.plan()), "")
        early = build_geotag_plan([self.photos["early.jpg"].path], self.infos, TRACK, MDT)
        self.assertEqual(
            nothing_matches_hint(early),
            "Your photos were taken about 2 h 12 min before this track (photos 10/03/2026 7:00:00am – 7:00:00am MDT; "
            "track 10/03/2026 9:12:00am – 11:42:00am MDT, in this computer's time zone). Check the time zone or "
            "the camera clock on the Date & Time tab, then load the track again.",
        )
        late = build_geotag_plan([self.photos["late.jpg"].path], self.infos, TRACK, MDT)
        self.assertIn("about 48 min after this track", nothing_matches_hint(late))
        paused = build_geotag_plan([self.photos["paused.jpg"].path], self.infos, TRACK, MDT)
        self.assertIn("within 30 min of a track point", nothing_matches_hint(paused))
        undated = build_geotag_plan([self.photos["scan.jpg"].path], self.infos, TRACK, MDT)
        self.assertEqual(nothing_matches_hint(undated), "None of these photos has a date, so none can be matched to the track.")

    def test_helpers(self) -> None:
        self.assertEqual(describe_duration(timedelta(seconds=20)), "20 s")
        self.assertEqual(describe_duration(timedelta(minutes=35)), "35 min")
        self.assertEqual(describe_duration(timedelta(hours=2, minutes=10)), "2 h 10 min")
        self.assertEqual(describe_duration(timedelta(hours=3)), "3 h")
        self.assertEqual(describe_duration(timedelta(days=3, hours=2, minutes=5)), "3 days 2 h")
        self.assertEqual(describe_duration(timedelta(days=-1)), "1 day")
        self.assertEqual(format_coordinates(40.6, -111.6), "40.600000, -111.600000")
        self.assertEqual(format_coordinates(40.6, -111.6, 1842.4), "40.600000, -111.600000 · 6,045 ft")
        self.assertEqual(format_coordinates(40.6, -111.6, 1842.4, feet=False), "40.600000, -111.600000 · 1,842 m")


if __name__ == "__main__":
    unittest.main()
