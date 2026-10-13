"""
Prepare what the web version loads but git doesn't hold: the browser-side
ExifTool (WebAssembly), Pyodide, and a zip of the app's own pure Python
modules.

Usage (from the repository root):
    python packaging/fetch_web_vendor.py                      # -> web/vendor/, web/py/
    python packaging/fetch_web_vendor.py --out DIR --py-out DIR   # the Docker build

Why this file exists:
    The web version runs ExifTool in the visitor's browser through
    @uswriting/exiftool (ExifTool as a Perl script) on @6over3/zeroperl-ts
    (Perl compiled to WebAssembly, with the ExifTool library baked in), and
    the app's own coordinate and date logic through Pyodide (Python as
    WebAssembly). Those are 24 MB and 12 MB, too big for git, so, like
    packaging/fetch_exiftool.py does for the desktop app, this script
    downloads pinned versions from the npm registry (and the tzdata wheel
    from the Pyodide CDN), checks their SHA-256, and unpacks the files the
    page loads:

        web/vendor/exiftool.js          the ExifTool wrapper (parseMetadata, writeMetadata)
        web/vendor/zeroperl.js          the Perl runtime (patched, see below)
        web/vendor/zeroperl.wasm        Perl + ExifTool 13.42 as WebAssembly
        web/vendor/pyodide/             pyodide.mjs, pyodide.asm.mjs, pyodide.asm.wasm,
                                        python_stdlib.zip, pyodide-lock.json, the tzdata wheel
        web/vendor/leaflet/             the map library (ES module build, its CSS and images)
        web/py/fotofixer_py.zip         core/ and services/ modules the browser runs
                                        (BROWSER_MODULES; tests/test_fetch_web_vendor.py
                                        checks they do no I/O)

    Two small changes are made to the ExifTool files as they are unpacked
    (the Phase 0 trial found both; see docs/ROADMAP.md):
      - exiftool.js imports zeroperl by its npm name; the page has no bundler,
        so the import becomes the relative file name.
      - zeroperl's in-memory file system grew a file by reallocating and
        copying the whole thing on every 64 KB write (quadratic: a 22 MB RAW
        took 15 s to write). The patch grows the buffer geometrically and
        trims it when the file is closed, which made writes 8 to 25x faster
        with byte-identical output.

Updating the packages:
    Change the version in PACKAGES and the checksum (sha256sum of the .tgz
    from https://registry.npmjs.org/<name>/-/<file>). If a patch no longer
    applies, the script stops with a message rather than shipping an
    unpatched file.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = PROJECT_ROOT / "web" / "vendor"
DEFAULT_PY_OUT = PROJECT_ROOT / "web" / "py"

EXIFTOOL_PACKAGE_VERSION = "1.0.9"
ZEROPERL_PACKAGE_VERSION = "1.0.10"
PYODIDE_VERSION = "314.0.7"
LEAFLET_VERSION = "1.9.4"
TZDATA_WHEEL = "tzdata-2025.3-py2.py3-none-any.whl"

# name -> (download URL, SHA-256 of the archive, files to take: archive path -> output path)
PACKAGES = {
    "@uswriting/exiftool": (
        f"https://registry.npmjs.org/@uswriting/exiftool/-/exiftool-{EXIFTOOL_PACKAGE_VERSION}.tgz",
        "1fad36e02b0c65f88d395bba57f52c7bb5b54ba1cdc0edd2212e4a832c5f7e09",
        {"package/dist/esm/index.js": "exiftool.js"},
    ),
    "@6over3/zeroperl-ts": (
        f"https://registry.npmjs.org/@6over3/zeroperl-ts/-/zeroperl-ts-{ZEROPERL_PACKAGE_VERSION}.tgz",
        "c46c5ffff4f2c2216137a6b34b4eb03f5554e17a2b88979463c5f61dffb36fed",
        {
            "package/dist/esm/index.js": "zeroperl.js",
            "package/dist/esm/zeroperl.wasm": "zeroperl.wasm",
        },
    ),
    # The map (BSD-2-Clause). The ES module build, loaded when the map opens.
    "leaflet": (
        f"https://registry.npmjs.org/leaflet/-/leaflet-{LEAFLET_VERSION}.tgz",
        "84c65a256e50657896f54c33bd857b6849ebe94c817803be818bf32a3dde0b77",
        {
            "package/dist/leaflet-src.esm.js": "leaflet/leaflet.esm.js",
            "package/dist/leaflet.css": "leaflet/leaflet.css",
            "package/dist/images/layers.png": "leaflet/images/layers.png",
            "package/dist/images/layers-2x.png": "leaflet/images/layers-2x.png",
            "package/dist/images/marker-icon.png": "leaflet/images/marker-icon.png",
            "package/dist/images/marker-icon-2x.png": "leaflet/images/marker-icon-2x.png",
            "package/dist/images/marker-shadow.png": "leaflet/images/marker-shadow.png",
        },
    ),
    "pyodide": (
        f"https://registry.npmjs.org/pyodide/-/pyodide-{PYODIDE_VERSION}.tgz",
        "66b7949e5a0cba2250b586d7e368bf12fb482800748d182c4618254b685ffaa0",
        {
            "package/pyodide.mjs": "pyodide/pyodide.mjs",
            "package/pyodide.asm.mjs": "pyodide/pyodide.asm.mjs",
            "package/pyodide.asm.wasm": "pyodide/pyodide.asm.wasm",
            "package/python_stdlib.zip": "pyodide/python_stdlib.zip",
            "package/pyodide-lock.json": "pyodide/pyodide-lock.json",
        },
    ),
}

# Single files (not archives): URL, SHA-256, output path.
FILES = {
    TZDATA_WHEEL: (
        f"https://cdn.jsdelivr.net/pyodide/v{PYODIDE_VERSION}/full/{TZDATA_WHEEL}",
        "9ce669f4f075843c7ff6a3f3dc306ebafa504717ec7beb6aa2233693722ddcfc",
        f"pyodide/{TZDATA_WHEEL}",
    ),
}

# The app's own modules the browser runs through Pyodide: pure logic with no
# file or process I/O (docs/ROADMAP.md, "Logic in the browser").
BROWSER_MODULES = (
    "web/bridge/fotofixer_bridge.py",
    "gui/__init__.py",
    "gui/presenters/__init__.py",
    "gui/presenters/date_time_state.py",
    "core/__init__.py",
    "core/coordinates.py",
    "core/models.py",
    "core/photo_dates.py",
    "core/time_zones.py",
    "core/map_tiles.py",
    "core/file_types.py",
    "services/__init__.py",
    "services/coordinate_service.py",
    "services/date_time_service.py",
    "services/gps_edit_history.py",
    "services/models.py",
)
PY_ZIP_NAME = "fotofixer_py.zip"


class PatchError(RuntimeError):
    """A patch's anchor text was not found exactly once: upstream changed."""


def _replace_once(text: str, old: str, new: str, what: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{what}: expected the anchor once, found it {count} times")
    return text.replace(old, new)


def patch_exiftool(text: str) -> str:
    """Point the wrapper's import at the vendored zeroperl.js next to it."""
    return _replace_once(
        text,
        'from"@6over3/zeroperl-ts"',
        'from"./zeroperl.js"',
        "exiftool.js import of zeroperl",
    )


# The two anchors in zeroperl's minified source that the patch replaces.
FD_WRITE_ANCHOR = "if(F>k(u.node))h=new Uint8Array(F),h.set(u.node.content,0);else h=u.node.content;"
FD_CLOSE_ANCHOR = "fd_close:(A)=>{let l=E(A);if(!l)return i.WASI_ERRNO_BADF;"


def patch_zeroperl(text: str) -> str:
    """
    Make the in-memory file system's writes linear instead of quadratic.

    fd_write: when a write goes past the end of the file, upstream allocates
    a buffer of exactly the new size and copies the old content. Instead,
    keep `content` a view of the logical length over a backing buffer that
    at least doubles each time it runs out.

    fd_close: callers take `content.buffer` as the file, so trim the view
    to an exact-size copy once the file is closed.
    """
    text = _replace_once(
        text,
        FD_WRITE_ANCHOR,
        "if(F>k(u.node)){let cur=u.node.content,cap=cur.buffer.byteLength-cur.byteOffset;"
        "if(cap>=F)h=new Uint8Array(cur.buffer,cur.byteOffset,F);"
        "else{let nb=new Uint8Array(Math.max(F,cap*2,65536));nb.set(cur,0);h=new Uint8Array(nb.buffer,0,F)}}"
        "else h=u.node.content;",
        "zeroperl.js fd_write growth",
    )
    return _replace_once(
        text,
        FD_CLOSE_ANCHOR,
        FD_CLOSE_ANCHOR
        + 'if(l.node.type==="file"&&ArrayBuffer.isView(l.node.content)'
        "&&l.node.content.buffer.byteLength!==l.node.content.byteLength)"
        "l.node.content=l.node.content.slice();",
        "zeroperl.js fd_close trim",
    )


PATCHES = {"exiftool.js": patch_exiftool, "zeroperl.js": patch_zeroperl}


def download(url: str, expected_sha256: str) -> bytes:
    print(f"Downloading {url}")
    with urllib.request.urlopen(url, timeout=180) as response:
        data = response.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected_sha256:
        raise RuntimeError(f"Checksum mismatch for {url}:\n  expected {expected_sha256}\n  got      {digest}")
    return data


def _write(out_dir: Path, name: str, data: bytes) -> None:
    target = out_dir / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    print(f"  {name}: {len(data) / 1048576:.1f} MB")


def fetch_vendor(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, (url, sha256, wanted) in PACKAGES.items():
        archive = download(url, sha256)
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
            for tar_path, out_name in wanted.items():
                member = tar.extractfile(tar_path)
                if member is None:
                    raise RuntimeError(f"{name}: {tar_path} is not in the package")
                data = member.read()
                patch = PATCHES.get(out_name)
                if patch is not None:
                    data = patch(data.decode("utf-8")).encode("utf-8")
                _write(out_dir, out_name, data)
    for url, sha256, out_name in FILES.values():
        _write(out_dir, out_name, download(url, sha256))
    (out_dir / "VERSIONS.txt").write_text(
        f"@uswriting/exiftool {EXIFTOOL_PACKAGE_VERSION} (ExifTool 13.42)\n"
        f"@6over3/zeroperl-ts {ZEROPERL_PACKAGE_VERSION}\n"
        f"pyodide {PYODIDE_VERSION} + {TZDATA_WHEEL}\n"
        f"leaflet {LEAFLET_VERSION}\n"
    )


def build_python_zip(py_out: Path, project_root: Path = PROJECT_ROOT) -> Path:
    """
    Zip the browser-side Python modules (BROWSER_MODULES) with their package
    paths, for Pyodide's unpackArchive.
    """
    py_out.mkdir(parents=True, exist_ok=True)
    target = py_out / PY_ZIP_NAME
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for module in BROWSER_MODULES:
            archive.write(project_root / module, module)
    print(f"  {PY_ZIP_NAME}: {len(BROWSER_MODULES)} modules, {target.stat().st_size / 1024:.0f} KB")
    return target


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Prepare the web version's vendored files and Python modules.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="vendor output folder (default: web/vendor)")
    parser.add_argument("--py-out", type=Path, default=DEFAULT_PY_OUT, help="Python zip output folder (default: web/py)")
    parser.add_argument("--python-only", action="store_true", help="only rebuild the Python zip (no downloads)")
    args = parser.parse_args(argv)
    try:
        if not args.python_only:
            fetch_vendor(args.out)
        build_python_zip(args.py_out)
    except (RuntimeError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
