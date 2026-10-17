import base64
import json
import subprocess
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.exiftool_wrapper import METADATA_READ_OPTIONS, ExifToolWrapper
from core.models import EmbeddedPreview


def _gps(metadata: dict) -> dict:
    """Just the GPS part of a metadata read (it also has dates and camera)."""
    return {"latitude": metadata["latitude"], "longitude": metadata["longitude"]}


class ExifToolWrapperTests(unittest.TestCase):
    """
    Command-building tests. These replace the ExifTool process with a stub, so
    they check which arguments are sent without needing ExifTool installed.
    """

    def _wrapper_with_reply(self, status: int = 0, output: str = "", errors: str = ""):
        wrapper = ExifToolWrapper("exiftool")
        execute_mock = MagicMock(return_value=(status, output, errors))
        wrapper._execute = execute_mock
        return wrapper, execute_mock

    def test_is_available_checks_path(self) -> None:
        wrapper = ExifToolWrapper("custom-exiftool")

        with patch("core.exiftool_wrapper.shutil.which", return_value="/usr/bin/tool"):
            self.assertTrue(wrapper.is_available())

        with patch("core.exiftool_wrapper.shutil.which", return_value=None):
            self.assertFalse(wrapper.is_available())

    def test_read_gps_returns_coordinates(self) -> None:
        payload = json.dumps([{"GPSLatitude": 40.5, "GPSLongitude": -111.8}])
        wrapper, execute_mock = self._wrapper_with_reply(output=payload)

        result = wrapper.read_gps(Path("/tmp/photo.jpg"))

        self.assertEqual(_gps(result), {"latitude": 40.5, "longitude": -111.8})
        self.assertEqual(
            execute_mock.call_args.args[0],
            [
                "-charset",
                "filename=utf8",
                "-json",
                "-n",
                "-GPSLatitude",
                "-GPSLongitude",
                "-GPSAltitude",
                "-GPSAltitudeRef",
                *METADATA_READ_OPTIONS,
                str(Path("/tmp/photo.jpg")),
            ],
        )

    def test_read_gps_returns_none_values_for_empty_payload(self) -> None:
        wrapper, _ = self._wrapper_with_reply(output="[]")

        result = wrapper.read_gps(Path("/tmp/photo.jpg"))

        self.assertEqual(_gps(result), {"latitude": None, "longitude": None})
        self.assertEqual(result["date_tags"]["DateTimeOriginal"], None)
        self.assertIsNone(result["make"])

    def test_read_gps_raises_runtime_error_on_failure(self) -> None:
        wrapper, _ = self._wrapper_with_reply(status=1, errors="bad read")

        with self.assertRaisesRegex(RuntimeError, "bad read"):
            wrapper.read_gps(Path("/tmp/photo.jpg"))

    def test_failure_without_error_text_uses_default_message(self) -> None:
        wrapper, _ = self._wrapper_with_reply(status=1)

        with self.assertRaisesRegex(RuntimeError, "Failed to write metadata."):
            wrapper.write_gps(Path("/tmp/photo.jpg"), 1.0, 2.0)

    def test_read_gps_many_returns_coordinates_by_path(self) -> None:
        first = Path("/tmp/first.jpg")
        second = Path("/tmp/second.jpg")
        payload = json.dumps(
            [
                {
                    "SourceFile": str(first),
                    "GPSLatitude": 40.5,
                    "GPSLongitude": -111.8,
                },
                {
                    "SourceFile": str(second),
                    "GPSLatitude": None,
                    "GPSLongitude": None,
                },
            ]
        )
        wrapper, execute_mock = self._wrapper_with_reply(output=payload)

        result = wrapper.read_gps_many([first, second])

        self.assertEqual(
            {path: _gps(metadata) for path, metadata in result.items()},
            {
                first: {"latitude": 40.5, "longitude": -111.8},
                second: {"latitude": None, "longitude": None},
            },
        )
        arguments = execute_mock.call_args.args[0]
        self.assertEqual(arguments[2:6], ["-json", "-n", "-GPSLatitude", "-GPSLongitude"])
        self.assertEqual(arguments[-2:], [str(first), str(second)])

    def test_reads_return_date_tags_and_camera(self) -> None:
        payload = json.dumps([{
            "SourceFile": "/tmp/photo.jpg",
            "DateTimeOriginal": "2026:10:03 09:14:02",
            "CreateDate": "2026:10:03 09:14:02",
            "FileModifyDate": "2026:10:04 08:00:00-06:00",
            "Make": "Canon",
            "Model": "Canon EOS R6",
        }])
        wrapper, _ = self._wrapper_with_reply(output=payload)

        result = wrapper.read_gps_many([Path("/tmp/photo.jpg")])[Path("/tmp/photo.jpg")]

        self.assertEqual(
            result["date_tags"],
            {
                "DateTimeOriginal": "2026:10:03 09:14:02",
                "CreateDate": "2026:10:03 09:14:02",
                "ModifyDate": None,
                "FileModifyDate": "2026:10:04 08:00:00-06:00",
                "OffsetTimeOriginal": None,
                "OffsetTimeDigitized": None,
                "OffsetTime": None,
            },
        )
        self.assertEqual((result["make"], result["model"]), ("Canon", "Canon EOS R6"))

    def test_write_date_tags_sets_and_removes_tags(self) -> None:
        wrapper, execute_mock = self._wrapper_with_reply()

        wrapper.write_date_tags(
            Path("/tmp/photo.jpg"),
            {
                "DateTimeOriginal": "2026:10:03 10:16:12",
                "CreateDate": None,
                "FileModifyDate": None,
            },
        )

        # None removes a tag, but the file's own date is left as it is.
        self.assertEqual(
            execute_mock.call_args.args[0][2:],
            [
                "-overwrite_original",
                "-DateTimeOriginal=2026:10:03 10:16:12",
                "-CreateDate=",
                str(Path("/tmp/photo.jpg")),
            ],
        )

    def test_date_changes_never_make_a_backup(self) -> None:
        wrapper, _ = self._wrapper_with_reply()
        wrapper.keep_backups = True

        with patch.object(wrapper, "_back_up_original") as back_up:
            wrapper.write_date_tags(Path("/tmp/photo.jpg"), {"DateTimeOriginal": "2026:10:03 10:16:12"})

        back_up.assert_not_called()

    def test_read_gps_many_raises_runtime_error_on_failure(self) -> None:
        wrapper, _ = self._wrapper_with_reply(status=1, errors="bad bulk read")

        with self.assertRaisesRegex(RuntimeError, "bad bulk read"):
            wrapper.read_gps_many([Path("/tmp/photo.jpg")])

    def test_write_gps_builds_expected_command_for_negative_values(self) -> None:
        wrapper, execute_mock = self._wrapper_with_reply()

        wrapper.write_gps(Path("/tmp/photo.jpg"), -40.5, -111.8)

        arguments = execute_mock.call_args.args[0]
        self.assertIn("-overwrite_original", arguments)
        self.assertIn("-GPSLatitude=40.5", arguments)
        self.assertIn("-GPSLatitudeRef=S", arguments)
        self.assertIn("-GPSLongitude=111.8", arguments)
        self.assertIn("-GPSLongitudeRef=W", arguments)
        self.assertEqual(arguments[-1], str(Path("/tmp/photo.jpg")))

    def test_write_gps_raises_runtime_error_on_failure(self) -> None:
        wrapper, _ = self._wrapper_with_reply(status=1, errors="bad write")

        with self.assertRaisesRegex(RuntimeError, "bad write"):
            wrapper.write_gps(Path("/tmp/photo.jpg"), 40.5, -111.8)

    def test_clear_gps_blanks_gps_tags(self) -> None:
        wrapper, execute_mock = self._wrapper_with_reply()

        wrapper.clear_gps(Path("/tmp/photo.jpg"))

        arguments = execute_mock.call_args.args[0]
        self.assertIn("-overwrite_original", arguments)
        self.assertIn("-GPSLatitude=", arguments)
        self.assertIn("-GPSLongitudeRef=", arguments)
        # The altitude a geotag may have written goes too.
        self.assertIn("-GPSAltitude=", arguments)
        self.assertIn("-GPSAltitudeRef=", arguments)
        self.assertEqual(arguments[-1], str(Path("/tmp/photo.jpg")))

    def test_metadata_reads_the_altitude_with_its_sign(self) -> None:
        from core.exiftool_wrapper import _metadata_from_record
        self.assertEqual(_metadata_from_record({"GPSAltitude": 2050.5, "GPSAltitudeRef": 0})["altitude"], 2050.5)
        self.assertEqual(_metadata_from_record({"GPSAltitude": 3.5, "GPSAltitudeRef": 1})["altitude"], -3.5)
        self.assertEqual(_metadata_from_record({"GPSAltitude": 12})["altitude"], 12.0)
        self.assertIsNone(_metadata_from_record({"GPSLatitude": 1.0})["altitude"])

    def test_write_gps_with_none_clears_the_altitude(self) -> None:
        wrapper, execute_mock = self._wrapper_with_reply()
        wrapper.write_gps(Path("/tmp/photo.jpg"), 40.5, -111.8, None)
        arguments = execute_mock.call_args.args[0]
        self.assertIn("-GPSAltitude=", arguments)
        self.assertIn("-GPSAltitudeRef=", arguments)

    def test_write_gps_with_altitude(self) -> None:
        wrapper, execute_mock = self._wrapper_with_reply()

        wrapper.write_gps(Path("/tmp/photo.jpg"), 40.5, -111.8, 2050.25)
        arguments = execute_mock.call_args.args[0]
        self.assertIn("-GPSAltitude=2050.25", arguments)
        self.assertIn("-GPSAltitudeRef=0", arguments)

        wrapper.write_gps(Path("/tmp/photo.jpg"), 40.5, -111.8, -3.5)
        arguments = execute_mock.call_args.args[0]
        self.assertIn("-GPSAltitude=3.5", arguments)
        self.assertIn("-GPSAltitudeRef=1", arguments)

        # Without an altitude the command is unchanged (Apply Location).
        wrapper.write_gps(Path("/tmp/photo.jpg"), 40.5, -111.8)
        self.assertFalse(any(argument.startswith("-GPSAltitude") for argument in execute_mock.call_args.args[0]))

    def test_read_embedded_previews_tries_small_previews_first(self) -> None:
        small = Path("/tmp/small.cr2")
        large_only = Path("/tmp/large-only.dng")
        none = Path("/tmp/none.cr3")
        encoded = "base64:" + base64.b64encode(b"jpeg-bytes").decode()
        replies = [
            # ThumbnailImage pass: only one file has a small preview.
            (0, json.dumps([
                {"SourceFile": str(small), "ThumbnailImage": encoded, "Orientation": 6},
                {"SourceFile": str(large_only), "Orientation": 8},
                {"SourceFile": str(none)},
            ]), ""),
            # PreviewImage pass: asked only for the two remaining files.
            (0, json.dumps([
                {"SourceFile": str(large_only), "PreviewImage": encoded, "Orientation": 8},
                {"SourceFile": str(none)},
            ]), ""),
            # JpgFromRaw pass: an error status must not discard anything.
            (1, json.dumps([{"SourceFile": str(none)}]), "Error: bad file"),
        ]
        wrapper = ExifToolWrapper("exiftool")
        wrapper._execute = MagicMock(side_effect=replies)

        previews = wrapper.read_embedded_previews([small, large_only, none])

        self.assertEqual(
            previews,
            {small: EmbeddedPreview(b"jpeg-bytes", 6), large_only: EmbeddedPreview(b"jpeg-bytes", 8)},
        )
        calls = wrapper._execute.call_args_list
        self.assertIn("-ThumbnailImage", calls[0].args[0])
        self.assertEqual(calls[1].args[0][-2:], [str(large_only), str(none)])
        self.assertIn("-JpgFromRaw", calls[2].args[0])
        self.assertEqual(calls[2].args[0][-1], str(none))

    def test_gps_read_captures_raw_thumbnails_so_files_are_opened_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            cr3 = folder / "with-thumbnail.CR3"
            dng = folder / "without-thumbnail.dng"
            jpg = folder / "photo.jpg"
            for path in (cr3, dng, jpg):
                path.write_bytes(b"data")
            encoded = "base64:" + base64.b64encode(b"small-jpeg").decode()
            wrapper = ExifToolWrapper("exiftool")
            wrapper._execute = MagicMock(
                side_effect=[
                    # GPS read for JPEGs: no thumbnail options.
                    (0, json.dumps([{"SourceFile": str(jpg)}]), ""),
                    # GPS read for RAW files also returns small thumbnails.
                    (0, json.dumps([
                        {"SourceFile": str(cr3), "GPSLatitude": 1.0, "GPSLongitude": 2.0,
                         "ThumbnailImage": encoded, "Orientation": 8},
                        {"SourceFile": str(dng)},
                    ]), ""),
                    # Thumbnail request: only the DNG, straight to PreviewImage.
                    (0, json.dumps([
                        {"SourceFile": str(dng), "PreviewImage": encoded, "Orientation": 1},
                    ]), ""),
                ]
            )

            gps = wrapper.read_gps_many([cr3, jpg, dng])
            previews = wrapper.read_embedded_previews([cr3, dng])

        self.assertEqual(_gps(gps[cr3]), {"latitude": 1.0, "longitude": 2.0})
        self.assertEqual(previews, {cr3: EmbeddedPreview(b"small-jpeg", 8), dng: EmbeddedPreview(b"small-jpeg", 1)})

        calls = [call.args[0] for call in wrapper._execute.call_args_list]
        self.assertEqual(len(calls), 3)
        self.assertNotIn("-ThumbnailImage", calls[0])
        self.assertEqual(calls[0][-1], str(jpg))
        self.assertIn("-ThumbnailImage", calls[1])
        self.assertEqual(calls[1][-2:], [str(cr3), str(dng)])
        self.assertIn("-PreviewImage", calls[2])
        self.assertEqual(calls[2][-1], str(dng))
        self.assertNotIn(str(cr3), calls[2])

    def test_preview_includes_photo_size(self) -> None:
        photo = Path("/tmp/photo.cr3")
        encoded = "base64:" + base64.b64encode(b"jpeg").decode()
        for image_size in ("6000 4000", "6000x4000"):
            wrapper, _ = self._wrapper_with_reply(
                output=json.dumps([{
                    "SourceFile": str(photo),
                    "ThumbnailImage": encoded,
                    "Orientation": 8,
                    "ImageSize": image_size,
                }])
            )
            with self.subTest(image_size=image_size):
                self.assertEqual(
                    wrapper.read_embedded_preview(photo),
                    EmbeddedPreview(b"jpeg", 8, 6000, 4000),
                )

    def test_remembered_thumbnail_is_ignored_after_file_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cr3 = Path(temp_dir) / "photo.cr3"
            cr3.write_bytes(b"data")
            old = "base64:" + base64.b64encode(b"old").decode()
            new = "base64:" + base64.b64encode(b"new").decode()
            wrapper = ExifToolWrapper("exiftool")
            wrapper._execute = MagicMock(
                side_effect=[
                    (0, json.dumps([{"SourceFile": str(cr3), "ThumbnailImage": old}]), ""),
                    (0, json.dumps([{"SourceFile": str(cr3), "ThumbnailImage": new}]), ""),
                ]
            )

            wrapper.read_gps_many([cr3])
            cr3.write_bytes(b"changed data")  # e.g. GPS was written in between
            previews = wrapper.read_embedded_previews([cr3])

        self.assertEqual(previews, {cr3: EmbeddedPreview(b"new", 1)})
        self.assertIn("-ThumbnailImage", wrapper._execute.call_args.args[0])

    def test_read_embedded_preview_defaults_bad_orientation_to_normal(self) -> None:
        photo = Path("/tmp/photo.cr2")
        encoded = "base64:" + base64.b64encode(b"jpeg").decode()
        wrapper, _ = self._wrapper_with_reply(
            output=json.dumps([{"SourceFile": str(photo), "ThumbnailImage": encoded, "Orientation": 42}])
        )

        self.assertEqual(wrapper.read_embedded_preview(photo), EmbeddedPreview(b"jpeg", 1))

    def test_exiftool_always_changes_files_in_place(self) -> None:
        wrapper, execute_mock = self._wrapper_with_reply()

        wrapper.write_gps(Path("/tmp/no-such-photo.jpg"), 1.0, 2.0)
        self.assertIn("-overwrite_original", execute_mock.call_args.args[0])
        wrapper.clear_gps(Path("/tmp/no-such-photo.jpg"))
        self.assertIn("-overwrite_original", execute_mock.call_args.args[0])

    def test_backup_is_name_original_with_the_same_extension(self) -> None:
        wrapper, _execute_mock = self._wrapper_with_reply()
        wrapper.keep_backups = True
        wrapper.read_gps = MagicMock(return_value={"latitude": 1.0, "longitude": 2.0})
        with tempfile.TemporaryDirectory() as temp_dir:
            photo = Path(temp_dir) / "IMG_0995.JPG"
            photo.write_bytes(b"original bytes")

            wrapper.write_gps(photo, 1.0, 2.0)
            backup = Path(temp_dir) / "IMG_0995_original.JPG"
            self.assertEqual(backup.read_bytes(), b"original bytes")
            # Reported once, for the app to add it to the Photo List.
            self.assertEqual(wrapper.take_created_backups(), [backup])
            self.assertEqual(wrapper.take_created_backups(), [])

            # Later changes keep the first backup (the true original).
            photo.write_bytes(b"changed bytes")
            wrapper.clear_gps(photo)
            self.assertEqual(backup.read_bytes(), b"original bytes")

    def test_no_backup_when_off_or_for_a_backup(self) -> None:
        wrapper, _execute_mock = self._wrapper_with_reply()
        with tempfile.TemporaryDirectory() as temp_dir:
            photo = Path(temp_dir) / "a.jpg"
            photo.write_bytes(b"x")
            wrapper.write_gps(photo, 1.0, 2.0)
            self.assertFalse((Path(temp_dir) / "a_original.jpg").exists())

            wrapper.keep_backups = True
            wrapper.read_gps = MagicMock(return_value={"latitude": 1.0, "longitude": 2.0})
            backup = Path(temp_dir) / "b_original.jpg"
            backup.write_bytes(b"y")
            wrapper.write_gps(backup, 1.0, 2.0)
            self.assertFalse((Path(temp_dir) / "b_original_original.jpg").exists())

    def test_no_backup_for_a_photo_without_gps(self) -> None:
        wrapper, _execute_mock = self._wrapper_with_reply()
        wrapper.keep_backups = True
        wrapper.read_gps = MagicMock(return_value={"latitude": None, "longitude": None})
        with tempfile.TemporaryDirectory() as temp_dir:
            photo = Path(temp_dir) / "new.jpg"
            photo.write_bytes(b"x")

            wrapper.write_gps(photo, 1.0, 2.0)

            self.assertFalse((Path(temp_dir) / "new_original.jpg").exists())

    def test_a_failed_backup_leaves_the_photo_unchanged(self) -> None:
        wrapper, execute_mock = self._wrapper_with_reply()
        wrapper.keep_backups = True
        wrapper.read_gps = MagicMock(return_value={"latitude": 1.0, "longitude": 2.0})

        with self.assertRaises(OSError):
            wrapper.write_gps(Path("/tmp/no-such-folder/photo.jpg"), 1.0, 2.0)
        execute_mock.assert_not_called()

    def test_process_is_guarded_stay_open_utf8_and_hidden_console_window(self) -> None:
        wrapper = ExifToolWrapper("exiftool")
        fake_process = MagicMock()
        fake_process.poll.return_value = None
        fake_process.stdout = iter([])
        fake_process.stderr = iter([])

        with (
            patch(
                "core.exiftool_wrapper.start_guarded_process",
                return_value=fake_process,
            ) as popen_mock,
            patch("core.exiftool_wrapper.atexit.register"),
        ):
            wrapper._ensure_process()

        self.assertEqual(
            popen_mock.call_args.args[0],
            ["exiftool", "-stay_open", "True", "-@", "-"],
        )
        kwargs = popen_mock.call_args.kwargs
        self.assertEqual(kwargs["encoding"], "utf-8")
        self.assertEqual(
            kwargs["creationflags"],
            getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )


@unittest.skipUnless(ExifToolWrapper().is_available(), "ExifTool is not installed")
class ExifToolWrapperIntegrationTests(unittest.TestCase):
    """
    Tests against the real ExifTool program, including the long-running
    process protocol. Skipped when ExifTool is not installed.
    """

    def setUp(self) -> None:
        self.wrapper = ExifToolWrapper()
        self.addCleanup(self.wrapper.close)
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.temp_path = Path(temp_dir.name)

    def _make_photo(self, name: str) -> Path:
        # Pillow is a desktop dependency; it is only used here to make a JPEG.
        from PIL import Image

        photo = self.temp_path / name
        Image.new("RGB", (8, 8), "white").save(photo)
        return photo

    def test_write_read_clear_round_trip_with_unicode_file_name(self) -> None:
        photo = self._make_photo("Café 東京 #1.jpg")

        self.wrapper.write_gps(photo, -33.8568, 151.2153)
        gps = self.wrapper.read_gps(photo)
        self.assertAlmostEqual(gps["latitude"], -33.8568, places=4)
        self.assertAlmostEqual(gps["longitude"], 151.2153, places=4)

        bulk = self.wrapper.read_gps_many([photo])
        self.assertAlmostEqual(bulk[photo]["latitude"], -33.8568, places=4)

        self.wrapper.clear_gps(photo)
        self.assertEqual(
            _gps(self.wrapper.read_gps(photo)),
            {"latitude": None, "longitude": None},
        )

    def test_date_write_read_and_restore_round_trip(self) -> None:
        photo = self._make_photo("dates.jpg")
        before = self.wrapper.read_gps(photo)["date_tags"]

        self.wrapper.write_date_tags(
            photo,
            {
                "DateTimeOriginal": "2026:10:03 10:16:12",
                "CreateDate": "2026:10:03 10:16:12",
                "ModifyDate": "2026:10:03 10:16:12",
                "FileModifyDate": "2026:10:03 10:16:12",
            },
        )
        after = self.wrapper.read_gps(photo)["date_tags"]
        self.assertEqual(after["DateTimeOriginal"], "2026:10:03 10:16:12")
        self.assertEqual(after["ModifyDate"], "2026:10:03 10:16:12")
        self.assertTrue(after["FileModifyDate"].startswith("2026:10:03 10:16:12"))

        # Undo writes back exactly what was read before.
        self.wrapper.write_date_tags(photo, before)
        self.assertEqual(self.wrapper.read_gps(photo)["date_tags"], before)

    def test_gps_and_dates_in_heic(self) -> None:
        """iPhone photos: GPS, all three dates, and the time zone."""
        heic = self.temp_path / "IMG_1234.HEIC"
        shutil.copy(Path(__file__).parent / "fixtures" / "sample.heic", heic)
        dates = {
            "DateTimeOriginal": "2026:05:23 11:16:41",
            "CreateDate": "2026:05:23 11:16:41",
            "ModifyDate": "2026:05:23 11:16:41",
            "OffsetTimeOriginal": "-05:00",
            "OffsetTimeDigitized": "-05:00",
            "OffsetTime": "-05:00",
        }
        before = self.wrapper.read_gps(heic)["date_tags"]
        self.wrapper.write_gps(heic, 40.5865, -111.6558)
        self.wrapper.write_date_tags(heic, dates)

        read = self.wrapper.read_gps_many([heic])[heic]
        self.assertAlmostEqual(read["latitude"], 40.5865, places=4)
        self.assertAlmostEqual(read["longitude"], -111.6558, places=4)
        for tag, value in dates.items():
            self.assertEqual(read["date_tags"][tag], value, tag)

        # Undo puts the dates back exactly.
        self.wrapper.write_date_tags(heic, before)
        self.assertEqual(self.wrapper.read_gps(heic)["date_tags"], before)

    def test_backup_keeps_untouched_original_across_edits(self) -> None:
        photo = self._make_photo("backup.jpg")
        backup = photo.with_name("backup_original.jpg")
        # A photo that already has GPS (photos without GPS aren't backed up).
        self.wrapper.write_gps(photo, 1.0, 2.0)
        self.wrapper.keep_backups = True

        self.wrapper.write_gps(photo, 3.0, 4.0)
        self.wrapper.write_gps(photo, 5.0, 6.0)
        self.wrapper.clear_gps(photo)

        self.assertTrue(backup.exists())
        # Not ExifTool's own "backup.jpg_original" any more.
        self.assertFalse(photo.with_name("backup.jpg_original").exists())
        original = self.wrapper.read_gps(backup)
        self.assertAlmostEqual(original["latitude"], 1.0, places=4)
        self.assertAlmostEqual(original["longitude"], 2.0, places=4)

    def test_no_backup_for_a_real_photo_without_gps(self) -> None:
        photo = self._make_photo("plain.jpg")
        self.wrapper.keep_backups = True

        self.wrapper.write_gps(photo, 1.0, 2.0)

        self.assertFalse(photo.with_name("plain_original.jpg").exists())

    def test_no_backup_file_by_default(self) -> None:
        photo = self._make_photo("no-backup.jpg")

        self.wrapper.write_gps(photo, 1.0, 2.0)

        self.assertFalse(photo.with_name("no-backup_original.jpg").exists())
        self.assertFalse(photo.with_name("no-backup.jpg_original").exists())

    def test_reads_embedded_thumbnail_and_orientation(self) -> None:
        from PIL import Image

        photo = self._make_photo("with-thumbnail.jpg")
        thumbnail = self.temp_path / "thumb.jpg"
        Image.new("RGB", (16, 8), "red").save(thumbnail)
        # Embed a thumbnail and mark the photo as "rotated 90 degrees".
        self.wrapper._run(
            ["-overwrite_original", f"-ThumbnailImage<={thumbnail}", "-Orientation#=6"],
            [photo],
            "Failed to add test thumbnail.",
        )

        preview = self.wrapper.read_embedded_preview(photo)

        self.assertEqual(preview.jpeg_bytes, thumbnail.read_bytes())
        self.assertEqual(preview.orientation, 6)
        self.assertEqual((preview.image_width, preview.image_height), (8, 8))
        self.assertIsNone(self.wrapper.read_embedded_preview(self._make_photo("plain.jpg")))

    def test_one_process_serves_many_commands(self) -> None:
        photos = [self._make_photo(f"photo_{index}.jpg") for index in range(5)]

        for photo in photos:
            self.wrapper.write_gps(photo, 40.7608, -111.891)
        process_id = self.wrapper._process.pid

        results = self.wrapper.read_gps_many(photos)

        self.assertEqual(self.wrapper._process.pid, process_id)
        self.assertEqual(len(results), 5)
        for gps in results.values():
            self.assertAlmostEqual(gps["latitude"], 40.7608, places=4)

    def test_error_is_reported_and_process_keeps_working(self) -> None:
        photo = self._make_photo("good.jpg")

        with self.assertRaisesRegex(RuntimeError, "(?i)error"):
            self.wrapper.write_gps(self.temp_path / "missing.jpg", 1.0, 2.0)

        process_id = self.wrapper._process.pid
        self.wrapper.write_gps(photo, 1.5, 2.5)

        self.assertEqual(self.wrapper._process.pid, process_id)
        self.assertAlmostEqual(self.wrapper.read_gps(photo)["latitude"], 1.5, places=4)

    def test_new_process_starts_after_exiftool_dies(self) -> None:
        photo = self._make_photo("restart.jpg")
        self.wrapper.read_gps(photo)
        old_process = self.wrapper._process

        old_process.kill()
        old_process.wait()

        self.wrapper.write_gps(photo, 10.0, 20.0)
        self.assertIsNot(self.wrapper._process, old_process)
        self.assertAlmostEqual(self.wrapper.read_gps(photo)["latitude"], 10.0, places=4)

    def test_close_stops_process(self) -> None:
        photo = self._make_photo("close.jpg")
        self.wrapper.read_gps(photo)
        process = self.wrapper._process

        self.wrapper.close()

        self.assertIsNotNone(process.poll())
        self.assertIsNone(self.wrapper._process)


if __name__ == "__main__":
    unittest.main()
