import unittest
from pathlib import Path

from core.photo_loader import PhotoLoader


class FakeExifTool:
    def __init__(self) -> None:
        self.calls: list[Path] = []
        self.bulk_calls: list[list[Path]] = []
        self.response = {"latitude": 40.5, "longitude": -111.8}
        self.bulk_response: dict[Path, dict] = {}
        self.error: Exception | None = None
        self.bulk_error: Exception | None = None

    def read_gps(self, path: Path) -> dict:
        self.calls.append(path)
        if self.error is not None:
            raise self.error
        return self.response

    def read_gps_many(self, paths: list[Path]) -> dict[Path, dict]:
        self.bulk_calls.append(paths)
        if self.bulk_error is not None:
            raise self.bulk_error
        return self.bulk_response


class PhotoLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.exiftool = FakeExifTool()
        self.loader = PhotoLoader(self.exiftool)

    def test_load_photo_info_reads_supported_file(self) -> None:
        path = Path("/tmp/photo.jpg")

        info = self.loader.load_photo_info(path)

        self.assertEqual(info.path, path)
        self.assertEqual(info.file_type, "JPG")
        self.assertEqual(info.current_latitude, 40.5)
        self.assertEqual(info.current_longitude, -111.8)
        self.assertIsNone(info.gps_error)
        self.assertEqual(self.exiftool.calls, [path])

    def test_load_photo_info_keeps_missing_gps_as_none(self) -> None:
        self.exiftool.response = {"latitude": None, "longitude": None}

        info = self.loader.load_photo_info(Path("/tmp/photo.jpeg"))

        self.assertIsNone(info.current_latitude)
        self.assertIsNone(info.current_longitude)
        self.assertIsNone(info.gps_error)

    def test_load_photo_info_rejects_unsupported_file_without_exif_call(self) -> None:
        path = Path("/tmp/photo.gif")

        info = self.loader.load_photo_info(path)

        self.assertEqual(info.gps_error, "Unsupported file type.")
        self.assertEqual(self.exiftool.calls, [])

    def test_load_photo_info_captures_exif_errors(self) -> None:
        self.exiftool.error = RuntimeError("ExifTool failed")

        info = self.loader.load_photo_info(Path("/tmp/photo.jpg"))

        self.assertEqual(info.gps_error, "ExifTool failed")
        self.assertIsNone(info.current_latitude)
        self.assertIsNone(info.current_longitude)

    def test_load_photo_infos_reads_supported_files_in_bulk(self) -> None:
        first = Path("/tmp/first.jpg")
        second = Path("/tmp/second.dng")
        self.exiftool.bulk_response = {
            first: {"latitude": 40.5, "longitude": -111.8},
            second: {"latitude": None, "longitude": None},
        }

        infos = self.loader.load_photo_infos([first, second])

        self.assertEqual([info.path for info in infos], [first, second])
        self.assertEqual(infos[0].current_latitude, 40.5)
        self.assertIsNone(infos[1].current_latitude)
        self.assertEqual(self.exiftool.bulk_calls, [[first, second]])
        self.assertEqual(self.exiftool.calls, [])

    def test_load_photo_infos_preserves_unsupported_file_handling(self) -> None:
        supported = Path("/tmp/photo.jpg")
        unsupported = Path("/tmp/photo.gif")
        self.exiftool.bulk_response = {
            supported: {"latitude": 40.5, "longitude": -111.8},
        }

        infos = self.loader.load_photo_infos([unsupported, supported])

        self.assertEqual(infos[0].gps_error, "Unsupported file type.")
        self.assertEqual(infos[1].current_longitude, -111.8)
        self.assertEqual(self.exiftool.bulk_calls, [[supported]])

    def test_load_photo_infos_falls_back_to_single_reads_when_bulk_fails(self) -> None:
        first = Path("/tmp/first.jpg")
        second = Path("/tmp/second.jpg")
        self.exiftool.bulk_error = RuntimeError("bulk failed")

        infos = self.loader.load_photo_infos([first, second])

        self.assertEqual([info.current_latitude for info in infos], [40.5, 40.5])
        self.assertEqual(self.exiftool.bulk_calls, [[first, second]])
        self.assertEqual(self.exiftool.calls, [first, second])

    def test_load_photo_infos_falls_back_when_bulk_omits_file(self) -> None:
        first = Path("/tmp/first.jpg")
        second = Path("/tmp/second.jpg")
        self.exiftool.bulk_response = {
            first: {"latitude": 41.0, "longitude": -112.0},
        }

        infos = self.loader.load_photo_infos([first, second])

        self.assertEqual(infos[0].current_latitude, 41.0)
        self.assertEqual(infos[1].current_latitude, 40.5)
        self.assertEqual(self.exiftool.calls, [second])


if __name__ == "__main__":
    unittest.main()
