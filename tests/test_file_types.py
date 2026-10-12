import unittest
from pathlib import Path

from core.file_types import (
    is_heif_file,
    is_raw_file,
    is_supported_file,
    may_hold_preview,
)


class SupportedFileTypeTests(unittest.TestCase):
    def test_supported_extensions_are_case_insensitive(self) -> None:
        self.assertTrue(is_supported_file(Path("image.JPG")))
        self.assertTrue(is_supported_file(Path("image.cr3")))
        self.assertTrue(is_supported_file(Path("image.DNG")))

    def test_heic_and_other_raw_formats_are_supported(self) -> None:
        for name in (
            "IMG_1234.HEIC", "photo.heif", "canon.HIF",
            "nikon.NEF", "nikon.nrw", "sony.ARW", "fuji.RAF",
            "olympus.ORF", "panasonic.RW2", "pentax.PEF", "samsung.SRW",
        ):
            self.assertTrue(is_supported_file(Path(name)), name)

    def test_unsupported_extensions_are_rejected(self) -> None:
        # Only files cameras and phones make: no PNG, TIFF, or GIF.
        for name in ("shot.png", "scan.tif", "scan.tiff", "image.gif", "clip.mov", "notes.txt", "image"):
            self.assertFalse(is_supported_file(Path(name)), name)

    def test_raw_files_are_recognized(self) -> None:
        self.assertTrue(is_raw_file(Path("image.CR2")))
        self.assertTrue(is_raw_file(Path("image.dng")))
        self.assertTrue(is_raw_file(Path("image.nef")))
        self.assertFalse(is_raw_file(Path("image.jpg")))
        self.assertFalse(is_raw_file(Path("image.heic")))

    def test_heif_files_and_preview_sources(self) -> None:
        self.assertTrue(is_heif_file(Path("IMG_1234.HEIC")))
        self.assertFalse(is_heif_file(Path("image.png")))
        # Thumbnails from a preview inside the file: RAW and HEIF.
        self.assertTrue(may_hold_preview(Path("image.arw")))
        self.assertTrue(may_hold_preview(Path("image.hif")))
        self.assertFalse(may_hold_preview(Path("image.jpg")))


if __name__ == "__main__":
    unittest.main()
