"""
Download the browser-side ExifTool (WebAssembly) into web/vendor/.

Usage (from the repository root):
    python packaging/fetch_web_vendor.py            # -> web/vendor/
    python packaging/fetch_web_vendor.py --out DIR  # the Docker build uses this

Why this file exists:
    The web version runs ExifTool in the visitor's browser through
    @uswriting/exiftool (ExifTool as a Perl script) on @6over3/zeroperl-ts
    (Perl compiled to WebAssembly, with the ExifTool library baked in). The
    24 MB .wasm is too big to keep in git, so, like packaging/fetch_exiftool.py
    does for the desktop app, this script downloads pinned versions from the
    npm registry, checks their SHA-256, and unpacks the three files the page
    loads:

        web/vendor/exiftool.js      the ExifTool wrapper (parseMetadata, writeMetadata)
        web/vendor/zeroperl.js      the Perl runtime (patched, see below)
        web/vendor/zeroperl.wasm    Perl + ExifTool 13.42 as WebAssembly

    Two small changes are made to the files as they are unpacked (the Phase 0
    trial found both; see docs/ROADMAP.md):
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
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = PROJECT_ROOT / "web" / "vendor"

EXIFTOOL_PACKAGE_VERSION = "1.0.9"
ZEROPERL_PACKAGE_VERSION = "1.0.10"

# name -> (download URL, SHA-256 of the .tgz, files to take: tar path -> output name)
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
}


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
    with urllib.request.urlopen(url, timeout=120) as response:
        data = response.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected_sha256:
        raise RuntimeError(f"Checksum mismatch for {url}:\n  expected {expected_sha256}\n  got      {digest}")
    return data


def fetch(out_dir: Path) -> None:
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
                (out_dir / out_name).write_bytes(data)
                print(f"  {out_name}: {len(data) / 1048576:.1f} MB")
    (out_dir / "VERSIONS.txt").write_text(
        f"@uswriting/exiftool {EXIFTOOL_PACKAGE_VERSION} (ExifTool 13.42)\n"
        f"@6over3/zeroperl-ts {ZEROPERL_PACKAGE_VERSION}\n"
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Download the browser-side ExifTool into web/vendor/.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output folder (default: web/vendor)")
    args = parser.parse_args(argv)
    try:
        fetch(args.out)
    except (RuntimeError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
