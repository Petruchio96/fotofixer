# Roadmap

The one place for what's next: the order of upcoming work and the plans for
each piece. `PROJECT_CONTEXT.md` describes what exists today; this file
describes what doesn't exist yet. Update it as work lands or decisions change,
and remove finished items.

## Order

1. **Whatever is wanted before the app is feature complete** (for example
   the not-scheduled items below and the web version's leftovers in
   Part 3), as 1.x releases. Feature complete is **2.0.0**. The Docker
   version (the user's name for the web version) shipped in 1.10.0 on
   2026-10-13; what remains of it is in Part 3.

Not scheduled:

- **Drag-and-drop loading** of photos into the desktop Photo List. The Add
  Photos picker (folders and photos) covers most of the need. (The web
  version has drag and drop from the start.)
- **Macs.** No release has been tested on a real Mac yet; test when one is
  available.
- **Geotagging from a GPS track** (below): load a track log from a phone,
  watch, or GPS logger and give each photo the location recorded at the
  moment it was taken. A future feature, in the desktop and web apps.

## Versions

Decided 2026-10-12 (the user's plan):

- **1.10.1** (2026-10-13) is the latest release: web fixes (the inactive
  tab page is hidden again, the map preview is laid out like the desktop's,
  and its ‹ › arrows work). 1.10.0 (2026-10-13) was the **Docker version**
  (the web app and its image), released together with the desktop app of
  the same version. 1.9.0 (2026-10-12) was the rename to FotoFixer – When &
  Where, HEIC/HEIF, and more RAW formats. Fixes are **1.10.x**.
- Further features before the app is feature complete: **1.11.0**, and so
  on.
- **2.0.0** marks **feature complete**. After it, every release is a fix or
  a small enhancement: **2.0.x** (2.0.1, 2.0.2, …).
- The usual rules in `CLAUDE.md` still decide whether a branch gets a bump
  at all.
- A release is never its own branch or PR. The branch that bumps the version
  is the release: merge its PR, tag, notes, publish (`RELEASE_CHECKLIST.md`).

---

## Geotagging from a GPS track (future)

Added 2026-10-12 (the user's idea, after comparing GeoSetter and GeoTag,
which both do this). Not scheduled yet.

What it does: load a track file that lists times and GPS positions (a phone,
watch, or GPS logger records one while you walk or drive), and the app gives
each selected photo the position recorded at the moment the photo was taken.

- **Files:** GPX first (Garmin, Strava, most GPS apps export it); later KML
  and CSV. ExifTool can read GPX itself (`-geotag`), or the app matches the
  times in `core/`/`services/` (pure Python, so the web version reuses it).
- **Matching works on the moment taken** (the app's rule): the photo's
  date, time, and time zone become a UTC moment, compared with the track's
  UTC times. Between two track points, the position is interpolated.
- **Camera clock off:** the user can enter an offset (or use the existing
  Shift first). A photo with no time zone needs one chosen before matching.
- **Limits:** a photo taken far from any track point (default: more than a
  few minutes before the first point, after the last, or across a long gap)
  is skipped and listed, not guessed.
- **UI:** probably a third source on the Location tab ("From a GPS Track"),
  with the track drawn on the map and the matched photos as dots before
  Apply; step-4-style before → after list; Undo as usual. Mockup first.

---

## Part 3: Web version (the Docker version): what's left

Shipped in **1.10.0** (2026-10-13) as the image `ghcr.io/petruchio96/fotofixer`.
What exists is described in `PROJECT_CONTEXT.md` ("Web version"), hosting
in `docs/SELF_HOSTING.md`, the container in `docker/README.md`. The
decisions that still bind any further web work (the user's, 2026-10-11/12):

- Browser-only. The container serves static files and never touches photo
  files; the earlier NAS-mount server design was rejected, and uploading
  photos to the container is not a fallback either.
- Login stays optional (one shared password at most, no accounts); each
  visitor's Esri key stays in their own browser; nothing from the visitor
  ever reaches the server.
- PCs, Macs, and iPads (about 1024 px and up); phones out of scope.
- The web version reuses `core/` and `services/` through Pyodide; the I/O
  stays in JavaScript. A JS port of those modules is the fallback only if
  Pyodide proves too slow on an iPad (unmeasured, see below).
- A DS920+ hosts it easily: static nginx, under 60 MB, a few MB of RAM, no
  CPU work per visitor.

Mockups (design artifact, 2026-10-11, still the reference for the web UI):
https://claude.ai/artifact/7vLiemwRBdyC351wLkS3SD.

### Still to check by hand (the user)

- Safari on a Mac and an iPad: the page loads (Pyodide and ExifTool, the
  first-visit download), HEIC thumbnails, downloads of changed photos, and
  the Pyodide load time on the iPad (decides the JS-port fallback).
- Lightroom and Synology Photos on files written by the browser
  (`~/Pictures/FotoFixer web trial/`).
- The NAS deployment itself (`docs/SELF_HOSTING.md`, Synology), then the
  shared address over HTTPS from outside the LAN.

### Deferred from the phases

- **The Add Photos picker dialog** of the mockups (folder tree, folder
  tiles, "Add Photos in Subfolders"); the `+ Add Photos` menu (Open a
  Folder, Choose Photos, Choose a Folder) and drag and drop cover the
  sources for now.
- **HEIC thumbnails outside Safari:** iPhone HEICs carry no JPEG thumbnail
  ExifTool can extract, and only Safari decodes HEIC, so those tiles show
  the photo icon. Fix: a small HEIF decoder in WebAssembly (libheif),
  vendored like ExifTool.
- The right-click "use this location" menu and the clipboard watcher (the
  Paste button reads the clipboard when clicked instead).
- Reading is one photo at a time through the worker (0.3 to 1 s per photo,
  2 to 3 s for a DNG that needs the second PreviewImage call): fine for a
  folder, slow for a thousand photos. A second worker instance would double
  it if ever needed.
- The ExifTool inside the WebAssembly bundle is 13.42 (the desktop ships
  13.59). Bump `@uswriting/exiftool` in `packaging/fetch_web_vendor.py` when
  a newer bundle appears, and re-run the real-file comparison (the trial's
  check: tags written in the browser match the desktop's for JPG, HEIC,
  CR2, CR3, and DNG).
- `FileModifyDate` isn't written (no browser can set a file's date).

### Open question

- **The in-page update notice.** The mockups' Settings page shows "Version
  X is available. Ask the person who runs this site to update it." The
  server is static, so the browser would have to ask GitHub, which the
  container's `connect-src 'self'` blocks. Either add `https://api.github.com`
  to `connect-src`, or keep it as it is: since 1.10.0 the version is baked
  in (`web/app/version.js`, shown under Settings with a link to the
  releases page, and the image's tags and labels), so dropping the notice
  costs nothing. The user's call.
