# Roadmap

The one place for what's next: the order of upcoming work and the plans for
each piece. `PROJECT_CONTEXT.md` describes what exists today; this file
describes what doesn't exist yet. Update it as work lands or decisions change,
and remove finished items.

## Order

1. **Geotagging in the web version** (Part 4): the desktop's Geotag from
   GPS Track (1.11.0) in the Docker version, as **1.11.1**.
2. **Whatever is wanted before the app is feature complete** (for example
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
- **Geotagging from KML or CSV tracks** (GPX shipped in 1.11.0): a parser
  per format in `core/gpx_track.py`; nothing else changes.

## Versions

Decided 2026-10-12 (the user's plan):

- **1.11.0** (2026-10-16) is the latest release: **Geotag from GPS Track**
  in the desktop app (File menu), the Settings dialog laid out as setting
  rows with a Units choice, and backups kept out of the Photo List.
  **1.11.1** brings geotagging to the web version (Part 4). 1.10.1
  (2026-10-13): fixes (picking a time from the Photo List shows every
  camera, desktop and web; web tab page, map preview, ‹ › arrows). 1.10.0
  (2026-10-13) was the **Docker version** (the web app and its image),
  released together with the desktop app of the same version. 1.9.0
  (2026-10-12) was the rename to FotoFixer – When & Where, HEIC/HEIF, and
  more RAW formats. Fixes are **1.11.x**.
- Further features before the app is feature complete: **1.12.0**, and so
  on.
- **2.0.0** marks **feature complete**. After it, every release is a fix or
  a small enhancement: **2.0.x** (2.0.1, 2.0.2, …).
- The usual rules in `CLAUDE.md` still decide whether a branch gets a bump
  at all.
- A release is never its own branch or PR. The branch that bumps the version
  is the release: merge its PR, tag, notes, publish (`RELEASE_CHECKLIST.md`).

---

## Part 4: Geotagging in the web version (1.11.1)

Decided 2026-10-16. The desktop feature (1.11.0: `gui/widgets/geotag_window.py`,
`gui/window_mixins/geotagger.py`, `core/gpx_track.py`, `services/geotag_service.py`;
`PROJECT_CONTEXT.md` "Geotag from GPS Track window") in the Docker version, same
look and behaviour: dots, one preview, the master Check All, feet or metres, the
suggestion rules. The matching is the desktop's Python through Pyodide, as Date
& Time is; the UI is a full-size `<dialog>` like the map dialog. The web rules
in `CLAUDE.md` bind (no inline styles or scripts, every button through `el()`
with a `title`, Python ops straight to the worker).

Entry point (the user's choice): a fourth item in the Photo List's **+ Add
Photos** menu, "Geotag from GPS Track…", greyed out until photos are loaded
(the hint says to add photos first); it opens the browser's file picker for
one or more `.gpx` files. Dropping a `.gpx` on the Photo List opens the same
dialog (today `file_sources.js` silently drops non-photo files).

Steps, each with its tests:

1. **Python.** `packaging/fetch_web_vendor.py` `BROWSER_MODULES` +=
   `core/gpx_track.py`, `services/geotag_service.py` (their imports are listed;
   `xml.etree` and `pyexpat` are in the vendored Pyodide); rebuild the zip
   (`--python-only`). `web/bridge/fotofixer_bridge.py` `geotag(op, payload_json)`
   like `dates`: `"load"` (`{tracks: [{name, text}]}` → parse with `parse_gpx`,
   merge, cache the points in a module-level `_TRACK`, return the points, count,
   span), `"plan"` (`{photos: [{id, name, dates, make, model, gps}], checks,
   computerOffsetMinutes, feet}` → `build_geotag_plan` with `_info(index, photo)`,
   the checks re-applied, return the rows with `status, chip, hint, timeText,
   included, hasGps, onTrack, suggested, checkable, latitude, longitude,
   altitude, current`, the summary, span text, nothing-matches hint, and
   `values`), `"forget"`. `tests/test_web_bridge.py` `GeotagTests`.
2. **Worker and client.** `web/worker/exif_worker.js`: `geotag` in the object
   `pythonReady` returns, a wrapper like `dates`, a `"geotag"` branch; `web/app/
   exif_client.js` `geotag(op, payload)` via `_send`.
3. **A shared Leaflet helper** (`web/app/leaflet_map.js`): `loadLeaflet`,
   `createLeafletMap(box, {getEsriKey, onEsriFailed})` (`showSource`,
   `setSatelliteSource`, `fitPoints`, `tileLayer`) and `buildPreview` for the
   "‹ 1 of n ›" popup, pulled out of `map_view.js`'s `createMapDialog`, which
   then uses them (behaviour unchanged; check the map dialog in the browser).
4. **The dialog** (`web/app/geotag_view.js` + pure `web/app/geotag_state.js`,
   Node-tested: `dotStyle`, `markerLocation`, `sameDotGroups` (14 px),
   `masterState`, `applyLabel`, `filesText`): `<dialog class="geotag-dialog">`
   with the map bar (Street/Satellite, Show Whole Track, Show All Photos, +/−),
   the summary line, the row list (`.geotag-row`: checkbox, 40×30 thumb from
   `photo.thumb` or `photoIcon()`, name, time, chip; `.on`/`.off`/`.active`/
   `.has-gps`/`.suggested`; the row's `title` is the hint) and the master Check
   All (`indeterminate`), the Leaflet map (`L.polyline` green 3 px; a
   `circleMarker` per photo, rings as a second larger marker drawn last,
   hovered +3), the readout, the bottom bar (the warning with the Shift link,
   + Add More Photos, Cancel, Geotag N Photos). Clicking a dot or a row (outside
   the checkbox) → `setView(location, 17)` and the preview popup with Leave Off
   Track (grey outline) / Put On Track or Suggested Track Location (orange); the
   same row again or a map click closes it. A store subscription re-runs
   `"plan"` while open (debounced 30 ms), keeping the checks. Units:
   `settings.useFeet` (default true) in the `fotofixer.settings` localStorage
   object; `dialogs.showSettings` gains Imperial / Metric.
5. **Entry points and the flow** (`main.js`, `photo_list_view.js`,
   `file_sources.js`): the menu item and a hidden `<input type=file
   accept=".gpx" multiple>`; `entriesFromDrop` keeps `.gpx` files and
   `dropEntries` opens the dialog on them; `openGeotag(files)` reads each
   file's text, `"load"` (an error → `showMessage`), opens the dialog. Apply:
   `dialogs.askOverwrite` for checked has-GPS rows (Skip removes them);
   `after = Map(id → {gps: {latitude, longitude, altitude}, tags: gpsTags(gps)})`
   with `gpsTags` extended (`GPSAltitude`/`GPSAltitudeRef` when `gps.altitude
   != null`, both `""` in `gpsTags(null)` so Remove GPS clears them);
   `writeStates(after, {text: "Geotagging", makeBackups: true})`,
   `finishChange(kind: EDIT_GPS)` with "Geotagged N photos from the GPS track";
   download mode unchanged. Cancel/Esc: close, clear the selection, `"forget"`.
   Parity with the desktop (1.11.1): the worker also reads `GPSAltitude`/`Ref`
   into `gps.altitude`, so undo restores a photo's own altitude and Apply
   Location copies a source photo's altitude; a selected photo can be the
   location source (deselected when it becomes one, already in `setSource`).
   The Shift link: close, select the dated photos, `store.setMode("date")`, the
   Shift card. Known limit as the desktop: undoing a replaced photo's GPS leaves
   the track's altitude.
6. **Checks and docs.** `node --test web/tests/*.test.mjs`, the Python tests, the
   browser on the dev server with `~/Pictures/Test Pics/GPS Track Test Pics`
   (the campaign's photos and tracks; `reset_test_photos.sh` there resets them)
   through `window.fotofixerDebug`, `docker/check_container.sh`;
   `PROJECT_CONTEXT.md` "Web version", this Part, `README.md`; version 1.11.1.

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
