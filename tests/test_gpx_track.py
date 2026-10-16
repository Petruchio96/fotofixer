import unittest
from datetime import datetime, timedelta
from pathlib import Path

from core.gpx_track import (
    AFTER_TRACK,
    BEFORE_TRACK,
    IN_GAP,
    GpxError,
    Match,
    NoMatch,
    TrackPoint,
    locate,
    merge_tracks,
    parse_gpx,
    read_gpx_files,
    track_span,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample.gpx"


def utc(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 10, 3, hour, minute, second)


class ParseGpxTests(unittest.TestCase):
    def test_reads_timed_track_points_oldest_first_and_skips_the_rest(self) -> None:
        points = parse_gpx(FIXTURE.read_bytes(), "sample.gpx")
        # The waypoint and the point without a time are left out; the point
        # written with a -06:00 offset lands in UTC and sorts into place.
        self.assertEqual(
            [point.time for point in points],
            # Fractional seconds are kept.
            [utc(15, 12), utc(15, 22), utc(15, 32), datetime(2026, 10, 3, 15, 42, 0, 500000), utc(17, 42), utc(17, 52)],
        )
        self.assertEqual(points[0], TrackPoint(utc(15, 12), 40.6, -111.6, 2000.0))
        self.assertIsNone(points[2].elevation)

    def test_gpx_without_a_namespace_and_gpx_1_0(self) -> None:
        for header in ('<gpx version="1.0">', '<gpx xmlns="http://www.topografix.com/GPX/1/0" version="1.0">'):
            text = f'{header}<trk><trkseg><trkpt lat="1.5" lon="2.5"><time>2026-01-01T00:00:00Z</time></trkpt></trkseg></trk></gpx>'
            self.assertEqual(parse_gpx(text), [TrackPoint(datetime(2026, 1, 1), 1.5, 2.5, None)])

    def test_errors_name_the_file(self) -> None:
        with self.assertRaises(GpxError) as error:
            parse_gpx("<gpx><trk><trkseg><trkpt lat='1' lon='2'/></trkseg></trk></gpx>", "walk.gpx")
        self.assertIn("walk.gpx has no track points with times", str(error.exception))
        with self.assertRaises(GpxError) as error:
            parse_gpx("not xml at all", "notes.gpx")
        self.assertIn("notes.gpx is not a GPX file", str(error.exception))

    def test_read_gpx_files_merges_into_one_timeline(self) -> None:
        points = read_gpx_files([FIXTURE, FIXTURE])
        self.assertEqual(len(points), 12)
        self.assertEqual(points, sorted(points))
        with self.assertRaises(GpxError) as error:
            read_gpx_files([FIXTURE.parent / "missing.gpx"])
        self.assertIn("missing.gpx could not be read", str(error.exception))

    def test_merge_tracks_sorts_across_files(self) -> None:
        day_2 = [TrackPoint(utc(20, 0), 1, 1)]
        day_1 = [TrackPoint(utc(10, 0), 0, 0), TrackPoint(utc(11, 0), 0, 1)]
        merged = merge_tracks([day_2, day_1])
        self.assertEqual([point.time for point in merged], [utc(10, 0), utc(11, 0), utc(20, 0)])
        self.assertEqual(track_span(merged), (utc(10, 0), utc(20, 0)))


class LocateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.track = parse_gpx(FIXTURE.read_bytes())

    def test_interpolates_between_the_points_around_the_photo(self) -> None:
        # Halfway between 15:12 (40.60, -111.60, 2000 m) and 15:22 (40.61, -111.59, 2100 m).
        match = locate(self.track, utc(15, 17))
        self.assertIsInstance(match, Match)
        self.assertAlmostEqual(match.latitude, 40.605)
        self.assertAlmostEqual(match.longitude, -111.595)
        self.assertAlmostEqual(match.elevation, 2050.0)
        self.assertEqual((match.before.time, match.after.time), (utc(15, 12), utc(15, 22)))

    def test_elevation_needs_both_ends(self) -> None:
        match = locate(self.track, utc(15, 27))
        self.assertAlmostEqual(match.latitude, 40.615)
        self.assertIsNone(match.elevation)

    def test_a_photo_at_a_track_point_gets_that_point(self) -> None:
        match = locate(self.track, utc(15, 22))
        self.assertEqual((match.latitude, match.longitude, match.elevation), (40.61, -111.59, 2100.0))

    def test_within_the_gap_limit_of_the_ends(self) -> None:
        first = locate(self.track, utc(14, 50))
        self.assertEqual((first.latitude, first.longitude), (40.6, -111.6))
        last = locate(self.track, utc(18, 20))
        self.assertEqual((last.latitude, last.longitude), (40.71, -111.49))

    def test_too_far_before_or_after_the_track(self) -> None:
        before = locate(self.track, utc(14, 30))
        self.assertEqual(before, NoMatch(BEFORE_TRACK, timedelta(minutes=42)))
        after = locate(self.track, utc(18, 30))
        self.assertEqual(after, NoMatch(AFTER_TRACK, timedelta(minutes=38)))

    def test_in_a_gap_longer_than_the_limit(self) -> None:
        # The two segments are two hours apart (15:42 to 17:42).
        gap = locate(self.track, utc(16, 30))
        self.assertIsInstance(gap, NoMatch)
        self.assertEqual(gap.reason, IN_GAP)
        self.assertEqual(gap.distance, timedelta(minutes=47, seconds=59, microseconds=500000))

    def test_the_gap_limit_can_be_changed(self) -> None:
        match = locate(self.track, utc(16, 30), max_gap=timedelta(hours=3))
        self.assertIsInstance(match, Match)
        self.assertAlmostEqual(match.latitude, 40.64 + (40.70 - 40.64) * 0.4, places=3)


if __name__ == "__main__":
    unittest.main()
