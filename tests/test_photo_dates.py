import unittest
from datetime import datetime

from core.photo_dates import (
    camera_name,
    date_taken_from_tags,
    format_display_datetime,
    format_exif_datetime,
    parse_exif_datetime,
)


class PhotoDateTests(unittest.TestCase):
    def test_parses_exif_dates(self) -> None:
        self.assertEqual(parse_exif_datetime("2026:10:03 09:14:02"), datetime(2026, 10, 3, 9, 14, 2))
        # Time zone and sub-seconds after the seconds are ignored.
        self.assertEqual(parse_exif_datetime("2026:10:03 09:14:02-06:00"), datetime(2026, 10, 3, 9, 14, 2))
        self.assertEqual(parse_exif_datetime("2026:10:03 09:14:02.55"), datetime(2026, 10, 3, 9, 14, 2))

    def test_invalid_or_missing_dates_are_none(self) -> None:
        for text in (None, "", "0000:00:00 00:00:00", "not a date", 20261003):
            self.assertIsNone(parse_exif_datetime(text))

    def test_formats(self) -> None:
        moment = datetime(2026, 10, 3, 9, 14, 2)
        self.assertEqual(format_exif_datetime(moment), "2026:10:03 09:14:02")
        self.assertEqual(format_display_datetime(moment), "10/03/2026 9:14:02am")
        self.assertEqual(format_display_datetime(datetime(2026, 10, 3, 0, 5, 0)), "10/03/2026 12:05:00am")
        self.assertEqual(format_display_datetime(datetime(2026, 10, 3, 12, 0, 1)), "10/03/2026 12:00:01pm")
        self.assertEqual(format_display_datetime(datetime(2026, 10, 3, 23, 59, 59)), "10/03/2026 11:59:59pm")
        self.assertEqual(format_display_datetime(None), "No date")

    def test_date_taken_prefers_date_time_original(self) -> None:
        self.assertEqual(
            date_taken_from_tags({"DateTimeOriginal": "2026:10:03 09:14:02", "CreateDate": "2020:01:01 00:00:00"}),
            datetime(2026, 10, 3, 9, 14, 2),
        )
        self.assertEqual(
            date_taken_from_tags({"DateTimeOriginal": None, "CreateDate": "2020:01:01 00:00:00"}),
            datetime(2020, 1, 1),
        )
        # The file's own date is not when the photo was taken.
        self.assertIsNone(date_taken_from_tags({"FileModifyDate": "2026:10:03 09:14:02-06:00"}))

    def test_camera_names(self) -> None:
        self.assertEqual(camera_name("Canon", "Canon EOS R6"), "Canon EOS R6")
        self.assertEqual(camera_name("Apple", "iPhone 15 Pro"), "Apple iPhone 15 Pro")
        self.assertEqual(camera_name("NIKON CORPORATION", "NIKON D850"), "NIKON D850")
        self.assertEqual(camera_name("  Google ", ""), "Google")
        self.assertEqual(camera_name(None, "EOS R6"), "EOS R6")
        self.assertIsNone(camera_name(None, None))
        self.assertIsNone(camera_name("", "  "))


if __name__ == "__main__":
    unittest.main()
