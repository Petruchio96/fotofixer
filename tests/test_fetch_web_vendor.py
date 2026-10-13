"""
packaging/fetch_web_vendor.py: the patches applied to the vendored
browser-side ExifTool must apply exactly once, and refuse otherwise (so an
upstream change is noticed instead of shipping an unpatched file).
"""

import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "packaging" / "fetch_web_vendor.py"
spec = importlib.util.spec_from_file_location("fetch_web_vendor", SCRIPT)
fetch_web_vendor = importlib.util.module_from_spec(spec)
sys.modules["fetch_web_vendor"] = fetch_web_vendor
spec.loader.exec_module(fetch_web_vendor)


class PatchTests(unittest.TestCase):
    def test_exiftool_import_points_at_the_vendored_zeroperl(self) -> None:
        source = 'import{MemoryFileSystem as O,ZeroPerl as E}from"@6over3/zeroperl-ts";var y=1;'
        patched = fetch_web_vendor.patch_exiftool(source)
        self.assertIn('from"./zeroperl.js"', patched)
        self.assertNotIn("zeroperl-ts", patched)

    def test_zeroperl_file_system_grows_geometrically_and_trims_on_close(self) -> None:
        source = (
            "x;" + fetch_web_vendor.FD_WRITE_ANCHOR + "y;" + fetch_web_vendor.FD_CLOSE_ANCHOR + "z;"
        )
        patched = fetch_web_vendor.patch_zeroperl(source)
        self.assertNotIn(fetch_web_vendor.FD_WRITE_ANCHOR, patched)
        self.assertIn("cap*2", patched)
        self.assertIn("l.node.content=l.node.content.slice()", patched)
        # Nothing else changed.
        self.assertTrue(patched.startswith("x;"))
        self.assertTrue(patched.endswith("z;"))

    def test_a_missing_or_repeated_anchor_is_refused(self) -> None:
        with self.assertRaises(fetch_web_vendor.PatchError):
            fetch_web_vendor.patch_zeroperl("nothing here")
        with self.assertRaises(fetch_web_vendor.PatchError):
            fetch_web_vendor.patch_exiftool('from"@6over3/zeroperl-ts" from"@6over3/zeroperl-ts"')

    def test_pinned_downloads_have_checksums(self) -> None:
        for name, (url, sha256, wanted) in fetch_web_vendor.PACKAGES.items():
            self.assertTrue(url.startswith("https://registry.npmjs.org/"), name)
            self.assertRegex(sha256, r"^[0-9a-f]{64}$")
            self.assertTrue(wanted)


if __name__ == "__main__":
    unittest.main()
