import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from core.models import EmbeddedPreview
from gui.thumbnail_loader import ThumbnailLoader, _apply_exif_orientation


class ThumbnailLoaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_load_icon_returns_real_thumbnail_for_jpeg(self) -> None:
        loader = ThumbnailLoader(thumbnail_size=64)

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "photo.jpg"
            Image.new("RGB", (120, 80), color="red").save(path)

            icon = loader.load_icon(path)

        self.assertFalse(icon.isNull())

    def test_load_icon_falls_back_for_non_jpeg_files(self) -> None:
        loader = ThumbnailLoader(thumbnail_size=64)
        icon = loader.load_icon(Path("/tmp/photo.cr3"))
        self.assertFalse(icon.isNull())

    def test_load_icon_handles_unreadable_jpeg_with_fallback(self) -> None:
        loader = ThumbnailLoader(thumbnail_size=64)

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "broken.jpg"
            path.write_text("not really an image", encoding="utf-8")

            icon = loader.load_icon(path)

        self.assertFalse(icon.isNull())

    def test_load_icon_with_gps_badge_still_returns_icon(self) -> None:
        loader = ThumbnailLoader(thumbnail_size=64)

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "photo.jpg"
            Image.new("RGB", (64, 64), color="blue").save(path)

            icon = loader.load_icon(path, has_gps=True)

        self.assertFalse(icon.isNull())


def _jpeg_bytes(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color="green").save(buffer, format="JPEG")
    return buffer.getvalue()


class RawThumbnailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.folder = Path(temp_dir.name)

    def _raw_file(self, name: str) -> Path:
        path = self.folder / name
        path.write_bytes(b"raw")
        return path

    def test_raw_thumbnail_uses_embedded_preview_rotated_upright(self) -> None:
        raw = self._raw_file("portrait.cr2")
        reader_calls = []

        def reader(paths):
            reader_calls.append(list(paths))
            return {raw: EmbeddedPreview(_jpeg_bytes(120, 80), 6)}

        loader = ThumbnailLoader(thumbnail_size=64, preview_reader=reader)
        pixmap = loader.load_icon(raw).pixmap(64, 64)

        # A 120x80 landscape preview with orientation 6 becomes portrait.
        self.assertLess(pixmap.width(), pixmap.height())
        self.assertEqual(reader_calls, [[raw]])

    def test_load_images_reads_all_raw_files_in_one_call(self) -> None:
        first = self._raw_file("first.dng")
        second = self._raw_file("second.cr3")
        jpeg = self.folder / "photo.jpg"
        Image.new("RGB", (10, 10)).save(jpeg)
        reader_calls = []

        def reader(paths):
            reader_calls.append(list(paths))
            return {path: EmbeddedPreview(_jpeg_bytes(40, 30), 1) for path in paths}

        loader = ThumbnailLoader(thumbnail_size=64, preview_reader=reader)
        images = loader.load_images([first, jpeg, second])

        self.assertEqual(reader_calls, [[first, second]])
        self.assertEqual(set(images), {first, jpeg, second})
        self.assertTrue(all(image is not None and not image.isNull() for image in images.values()))

    def test_heic_tries_an_embedded_preview_then_decodes_with_pillow_heif(self) -> None:
        heic = self.folder / "IMG_1234.HEIC"
        heic.write_bytes((Path(__file__).parent / "fixtures" / "sample.heic").read_bytes())
        reader_calls = []

        def reader(paths):
            reader_calls.append(list(paths))
            return {}

        loader = ThumbnailLoader(thumbnail_size=64, preview_reader=reader)
        images = loader.load_images([heic])

        self.assertEqual(reader_calls, [[heic]])
        # No preview inside: decoded with pillow-heif (64x48 sample).
        self.assertEqual((images[heic].width(), images[heic].height()), (64, 48))

    def test_unreadable_heic_gets_no_image(self) -> None:
        broken = self.folder / "broken.heic"
        broken.write_bytes(b"not a heic")
        loader = ThumbnailLoader(thumbnail_size=64)
        self.assertIsNone(loader.load_images([broken])[broken])

    def test_jpeg_uses_its_small_embedded_thumbnail_before_reading_the_photo(self) -> None:
        with_thumbnail = self.folder / "with.jpg"
        without_thumbnail = self.folder / "without.jpg"
        Image.new("RGB", (10, 10)).save(with_thumbnail)
        Image.new("RGB", (10, 10)).save(without_thumbnail)
        small_calls = []

        def small_reader(paths):
            small_calls.append(list(paths))
            return {with_thumbnail: EmbeddedPreview(_jpeg_bytes(120, 80), 1)}

        loader = ThumbnailLoader(thumbnail_size=64, small_preview_reader=small_reader)
        images = loader.load_images([with_thumbnail, without_thumbnail])

        self.assertEqual(small_calls, [[with_thumbnail, without_thumbnail]])
        # From the wide 120x80 embedded thumbnail, not the square photo.
        self.assertGreater(images[with_thumbnail].width(), images[with_thumbnail].height())
        # No embedded thumbnail: the (square) photo itself is read.
        image = images[without_thumbnail]
        self.assertEqual(image.width(), image.height())

    def test_system_cache_is_used_first_and_filled(self) -> None:
        cache = self.folder / "cache"
        photo = self.folder / "photo.jpg"
        Image.new("RGB", (10, 10)).save(photo)
        small_calls = []

        def small_reader(paths):
            small_calls.append(list(paths))
            return {}

        loader = ThumbnailLoader(thumbnail_size=64, small_preview_reader=small_reader)
        loader.use_system_cache = True
        with patch("gui.system_thumbnails.cache_root", return_value=cache):
            loader.load_images([photo])
            self.assertEqual(len(list((cache / "normal").iterdir())), 1)

            small_calls.clear()
            image = loader.load_images([photo])[photo]

        # The second time, the saved thumbnail is used; the photo isn't read.
        self.assertEqual(small_calls, [])
        self.assertIsNotNone(image)

    def test_icons_are_cached_after_icon_from_image(self) -> None:
        raw = self._raw_file("cached.cr3")
        reader_calls = []

        def reader(paths):
            reader_calls.append(list(paths))
            return {path: EmbeddedPreview(_jpeg_bytes(40, 30), 1) for path in paths}

        loader = ThumbnailLoader(thumbnail_size=64, preview_reader=reader)
        self.assertIsNone(loader.cached_icon(raw))

        image = loader.load_images([raw])[raw]
        icon = loader.icon_from_image(raw, False, image)

        self.assertIs(loader.cached_icon(raw), icon)
        self.assertIs(loader.load_icon(raw), icon)
        self.assertEqual(len(reader_calls), 1)

    def test_load_images_is_safe_on_a_background_thread(self) -> None:
        import threading

        jpeg = self.folder / "threaded.jpg"
        Image.new("RGB", (80, 60), color="purple").save(jpeg)
        loader = ThumbnailLoader(thumbnail_size=64)
        results = {}

        thread = threading.Thread(target=lambda: results.update(loader.load_images([jpeg])))
        thread.start()
        thread.join(timeout=10)

        self.assertFalse(results[jpeg].isNull())
        self.assertFalse(loader.icon_from_image(jpeg, True, results[jpeg]).isNull())

    def test_padded_preview_is_cropped_to_photo_shape(self) -> None:
        raw = self._raw_file("padded.cr3")

        # A 4:3 preview (like Canon's 160x120 CR3 thumbnail) of a 3:2 photo,
        # shot in portrait (orientation 8).
        def reader(paths):
            return {raw: EmbeddedPreview(_jpeg_bytes(160, 120), 8, 6000, 4000)}

        loader = ThumbnailLoader(thumbnail_size=120, preview_reader=reader)
        pixmap = loader.load_icon(raw).pixmap(120, 120)

        # 160x120 scales to 120x90, crops to 120x80 (3:2), then rotates to 80x120.
        self.assertEqual((pixmap.width(), pixmap.height()), (80, 120))

    def test_raw_file_without_preview_or_reader_failure_gets_fallback_icon(self) -> None:
        raw = self._raw_file("photo.cr2")

        def failing_reader(paths):
            raise RuntimeError("ExifTool stopped unexpectedly.")

        for reader in (lambda paths: {}, failing_reader):
            loader = ThumbnailLoader(thumbnail_size=64, preview_reader=reader)
            icon = loader.load_icon(raw)
            self.assertFalse(icon.isNull())

    def test_exif_orientations(self) -> None:
        image = QImage(4, 2, QImage.Format_RGB32)
        image.fill(QColor("white"))
        image.setPixelColor(0, 0, QColor("red"))  # marker in the top-left corner

        def red_corner(result: QImage) -> tuple[int, int]:
            for x in range(result.width()):
                for y in range(result.height()):
                    if result.pixelColor(x, y) == QColor("red"):
                        return x, y
            raise AssertionError("marker lost")

        expected = {
            1: ((4, 2), (0, 0)),
            2: ((4, 2), (3, 0)),
            3: ((4, 2), (3, 1)),
            4: ((4, 2), (0, 1)),
            5: ((2, 4), (0, 0)),
            6: ((2, 4), (1, 0)),
            7: ((2, 4), (1, 3)),
            8: ((2, 4), (0, 3)),
        }
        for orientation, (size, corner) in expected.items():
            result = _apply_exif_orientation(image, orientation)
            with self.subTest(orientation=orientation):
                self.assertEqual((result.width(), result.height()), size)
                self.assertEqual(red_corner(result), corner)


if __name__ == "__main__":
    unittest.main()
