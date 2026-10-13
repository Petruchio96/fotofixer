# web/vendor

Third-party code the page loads, served from here (never from a CDN).
These files are not in git; `python packaging/fetch_web_vendor.py` downloads
the pinned versions and the Docker build does the same.

- `exiftool.js`: `@uswriting/exiftool` (Apache-2.0), ExifTool as a Perl
  script with `parseMetadata` / `writeMetadata`.
- `zeroperl.js`, `zeroperl.wasm`: `@6over3/zeroperl-ts` (Apache-2.0), Perl
  compiled to WebAssembly with the ExifTool library (13.42) inside.
- `VERSIONS.txt`: what was fetched.

The fetch script patches `zeroperl.js`'s in-memory file system (quadratic
growth on write) and `exiftool.js`'s import; see the script's docstring.
