"""
packaging/fetch_web_vendor.py: the patches applied to the vendored
browser-side ExifTool must apply exactly once, and refuse otherwise (so an
upstream change is noticed instead of shipping an unpatched file); and the
Python modules the browser runs must be pure logic with no I/O.
"""

import importlib.util
import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_ROOT / "packaging" / "fetch_web_vendor.py"
spec = importlib.util.spec_from_file_location("fetch_web_vendor", SCRIPT)
fetch_web_vendor = importlib.util.module_from_spec(spec)
sys.modules["fetch_web_vendor"] = fetch_web_vendor
spec.loader.exec_module(fetch_web_vendor)

# Modules that do file or process I/O, or need the desktop: never in the browser.
FORBIDDEN_IMPORTS = {
    "subprocess", "threading", "multiprocessing", "socket", "shutil", "os", "queue",
    "core.exiftool_wrapper", "core.photo_loader", "core.process_guard", "core.runtime_paths",
    "core.updates", "services.workflow_facade", "services.workflow_controller",
    "services.photo_service", "services.photo_metadata_cache", "PySide6", "PIL",
}


def imported_modules(source: str) -> set[str]:
    names = set()
    for match in re.finditer(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", source, re.MULTILINE):
        names.add(match.group(1) or match.group(2))
    return names


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
        for name, (url, sha256, out_name) in fetch_web_vendor.FILES.items():
            self.assertTrue(url.startswith("https://"), name)
            self.assertRegex(sha256, r"^[0-9a-f]{64}$")
            self.assertTrue(out_name)


class BrowserModulesTests(unittest.TestCase):
    """The Python the browser runs: present, importable, and I/O-free."""

    def test_every_browser_module_exists_and_imports_no_io(self) -> None:
        for module in fetch_web_vendor.BROWSER_MODULES:
            path = PROJECT_ROOT / module
            self.assertTrue(path.exists(), module)
            imports = imported_modules(path.read_text(encoding="utf-8"))
            forbidden = {name for name in imports if name.split(".")[0] in FORBIDDEN_IMPORTS or name in FORBIDDEN_IMPORTS}
            self.assertFalse(forbidden, f"{module} imports {sorted(forbidden)}")
            # Imports of the app's own modules must themselves be in the list.
            own = {name for name in imports if name.startswith(("core.", "services."))}
            listed = {m[:-3].replace("/", ".") for m in fetch_web_vendor.BROWSER_MODULES}
            self.assertTrue(own <= listed, f"{module} imports {sorted(own - listed)}, not in BROWSER_MODULES")

    def test_the_zip_holds_the_modules_with_their_package_paths(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            target = fetch_web_vendor.build_python_zip(Path(folder))
            with zipfile.ZipFile(target) as archive:
                self.assertEqual(sorted(archive.namelist()), sorted(fetch_web_vendor.BROWSER_MODULES))
                self.assertIn(b"def parse_coordinate_text", archive.read("services/coordinate_service.py"))


if __name__ == "__main__":
    unittest.main()
