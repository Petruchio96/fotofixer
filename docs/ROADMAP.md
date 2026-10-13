# Roadmap

The one place for what's next: the order of upcoming work and the plans for
each piece. `PROJECT_CONTEXT.md` describes what exists today; this file
describes what doesn't exist yet. Update it as work lands or decisions change,
and remove finished items.

## Order

1. **Docker version** (the user's name for the web version; Part 3), 6
   branches counting the Phase 0 trial. It goes first (the user's call,
   2026-10-12). The design is browser-only: a static container, editing in
   each visitor's own browser, photos never leave their computer. It ships
   as **version 1.10.0** (desktop and Docker versions released together).
2. **Then whatever else is wanted before the app is feature complete**
   (for example the not-scheduled items below), as 1.x releases. Feature
   complete is **2.0.0**.
   - **The name: FotoFixer – When & Where** (chosen 2026-10-12; the desktop
     app has it since 1.9.0). The web version uses it from its first image:
     the GHCR image (`fotofixer`), the page title, the self-hosting docs, and
     the address the user plans to share.

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

- **1.9.0** (2026-10-12) is the latest release: the rename to FotoFixer –
  When & Where, HEIC/HEIF, and more RAW formats. Desktop fixes while the
  Docker version is built are **1.9.x**.
- **1.10.0** is the next version: the **Docker version** (the web app),
  released together with the desktop app of the same version.
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

## Part 3: Web version in a Docker container

Decided 2026-10-11/12. It replaces an earlier design (a FastAPI server that
mounted the NAS photo share and ran ExifTool on it), which the user
rejected: the container must never touch photo files.

### Goal

It works like BentoPDF. Someone hosts one container. Friends and family open
its address (the user's will be something like
`https://fotofixer.iramnas.synology.me`, behind the Synology
reverse proxy) and edit GPS and dates in photos **on their own computer**.
Anyone can self-host the same image on any Docker host and share it the same
way.

- **ExifTool runs in the visitor's browser** as WebAssembly.
  `@uswriting/exiftool` runs ExifTool on zeroperl (Perl compiled to
  WebAssembly) and has `readMetadata()` and `writeMetadata()`; ExifTool's
  author points to it. Writing CR3 that way is unproven: Phase 0 is a trial.
- Photos never leave the visitor's computer. Nothing passes through the
  host's internet connection except the app itself; the server stores
  nothing. No NAS folder is mounted, so there is no server-side path
  handling, temp storage, or per-user state.

Decisions with the user:

- Editing in the browser, files on the visitor's own computer, no NAS mount.
- **Login is optional and off by default**, as in BentoPDF. The host can set
  one shared password with environment variables to keep strangers out. A
  visitor can only ever change their own files, so the password only
  decides who can load the page. No per-person accounts.
- **Esri satellite:** each visitor enters their own key, saved only in their
  browser and sent straight to Esri. The host's key is never involved, and
  no key is ever in the repo or image.
- HEIC from the start (the desktop app has it since 1.9.0).
- Image for `linux/amd64` + `linux/arm64` on GHCR. MIT license (add
  `LICENSE`). PCs, Macs, and iPads (about 1024 px and up); phones out of
  scope.

### What changes from the desktop app

| | Desktop | Web |
|---|---|---|
| Where files are | Local disk and shares | The visitor's computer, through the browser |
| ExifTool | Pinned 13.59 Perl/exe, `-stay_open` | ExifTool WebAssembly build in a Web Worker |
| Logic | `core/`, `services/` (Python) | The same pure Python modules through Pyodide, or a JS port if Phase 0 says so |
| Saving | In place | Chrome/Edge: in place in the opened folder. Safari, Firefox, iPad: download (one file, or a zip) |
| Settings | QSettings | `localStorage` in the visitor's browser |
| Undo/redo | In memory | In memory for the tab; in download mode, until the download |

### Architecture

```
Visitor's browser (PC / Mac / iPad)
  index.html + JS modules (no build step) + Leaflet (vendored)
  ├─ UI thread: Photo List, Photos to Change, map, Settings
  └─ Web Worker
       ├─ ExifTool WebAssembly (read GPS/dates/previews, write tags)
       └─ Pyodide + core/ and services/ pure modules (date plans,
          time zones, coordinate parsing, undo history)
  Files: File System Access API (Chrome/Edge, read-write folder)
         or <input type=file>, webkitdirectory, drag and drop (all browsers)
  Map tiles: OSM and USGS direct; Esri direct with the visitor's own key
      │ HTTPS, static files only
Reverse proxy (Synology, Caddy, Traefik…) ── TLS
      │ HTTP
Container: nginx-unprivileged serving web/ (static), optional basic auth
```

### Opening photos (replaces the desktop's folder-tree picker)

- **Open a Folder** (Chrome and Edge on a computer):
  `showDirectoryPicker({mode: "readwrite"})`. The picker's folder tree and
  tiles show that folder and its subfolders, as in the desktop picker.
  Changes are written back into the original files. With the backups option
  on, an `<name>_original.<ext>` copy goes next to the photo, as on the
  desktop.
- **Add Photos** (every browser): a file input with `multiple`, plus a
  folder input (`webkitdirectory`) where supported. Changed photos come back
  as downloads: one file directly, several as a zip, with the original
  names.
- **Drag and drop** anywhere on the Photo List: files and folders
  (`webkitGetAsEntry`). In Chrome/Edge, `getAsFileSystemHandle` gives write
  access, so dropped photos save in place too.
- The page says which mode applies: "Changes are saved straight into your
  files" or "Changed photos download when you click Download".
- iPad: Add Photos opens the Files app picker; downloads go to Files.
- "Copy location / time from a photo" becomes **From a Photo on This
  Computer** (the picker in one-photo mode).

### Logic in the browser

Pyodide runs Python as WebAssembly. The modules with no I/O are reused as
they are (they already have no Qt):

- `core/coordinates.py`, `services/coordinate_service.py`: coordinate parsing
- `core/photo_dates.py`, `core/time_zones.py` (the `tzdata` Pyodide
  package), `services/date_time_service.py` (`plan_shift`, `plan_set`,
  `plan_zone_change`, `date_tag_values`, `group_by_camera`)
- `services/gps_edit_history.py`: undo/redo memory
- `core/map_tiles.py`: tile URLs and fit-to-photos math
- `core/file_types.py`: supported extensions

The I/O parts (`core/exiftool_wrapper.py`, `core/photo_loader.py`,
`services/workflow_facade.py`) stay desktop-only. A JS layer does the
reading and writing and calls Python only for plans and parsing. (Pyodide's
synchronous Python can't wait on the async ExifTool calls in Safari, which
is why I/O stays in JS.)

If Phase 0 shows Pyodide's download (several MB, cached after the first
visit) is too slow on an iPad, port these modules to JS instead, with the
same test cases; a test then checks that both versions give the same
answers.

### Thumbnails

ExifTool WebAssembly extracts `ThumbnailImage` or `PreviewImage`, never
`JpgFromRaw` (a full-size JPEG per RAW). `createImageBitmap` and a canvas
fix the orientation and crop to the photo's aspect ratio, as
`gui/thumbnail_loader.py` does. Photos are read one at a time in the worker,
and tiles fill in as they're ready. Thumbnails stay in memory only, so
nothing is left behind on a shared computer.

### Container and security

- **Image:** `nginxinc/nginx-unprivileged` (alpine) serving `web/` as static
  files. No Python, Perl, or ExifTool in the container. Expected size under
  60 MB.
- **Vendored, never from a CDN:** Leaflet, the ExifTool WebAssembly bundle,
  and Pyodide with only the packages used. Visitors download nothing from
  third parties except map tiles.
- **Optional password:** `APP_USERNAME` + `APP_PASSWORD` (or
  `APP_PASSWORD_FILE`). At start the entrypoint writes an htpasswd file to
  tmpfs and turns on nginx basic auth; without them the app is open. Basic
  auth is safe over HTTPS and needs no server code. nginx `limit_req` slows
  password guessing.
- **Headers:** `Content-Security-Policy: default-src 'self'; script-src
  'self' 'wasm-unsafe-eval'; worker-src 'self' blob:; img-src 'self' data:
  blob: https://tile.openstreetmap.org https://basemap.nationalmap.gov
  https://ibasemaps-api.arcgis.com; connect-src 'self'; object-src 'none';
  frame-ancestors 'none'; base-uri 'none'; form-action 'self'`,
  `X-Content-Type-Options: nosniff`, `Referrer-Policy:
  strict-origin-when-cross-origin` (OpenStreetMap wants an identifying
  referer), `Permissions-Policy`, the `application/wasm` MIME type, and a
  long cache for versioned assets. Cross-origin isolation (COOP/COEP) only
  if Phase 0 shows the WebAssembly build needs it; strict COEP would block
  map tiles.
- **Privacy:** no analytics, no cookies (except basic auth), no file data
  ever sent. nginx access logs can be turned off with an env var.
- **The Esri key** lives in the visitor's `localStorage` under a clear "this
  browser only" label, with Remove Key; tiles load from Esri with `?token=`,
  as on the desktop.
- **Compose defaults:** `read_only: true`, `tmpfs: /tmp`, `cap_drop: [ALL]`,
  `security_opt: [no-new-privileges:true]`, `mem_limit: 128m`,
  `restart: unless-stopped`, port on `127.0.0.1:8080` only, `HEALTHCHECK`.
- The server has nothing to steal or misuse: no files, no keys, no accounts.

### Publishing the image

A workflow (`.github/workflows/docker.yml`) builds `linux/amd64` and
`linux/arm64` with buildx and pushes `ghcr.io/petruchio96/<new-name>` with
the tags `latest`, `X.Y`, and `X.Y.Z` when a GitHub release is
**published** (`on: release: types: [published]`, pre-releases skipped;
plus `workflow_dispatch` with a tag input), not on the `v*` tag: the tag
build makes the draft, and publishing the release ships the desktop files
(which the update checker sees) and the image at the same time. Steps:
checkout at the tag, `docker/login-action` to ghcr.io with `GITHUB_TOKEN`
(`permissions: packages: write`), `docker/metadata-action`,
`docker/build-push-action` with `file: docker/Dockerfile`. Pushes to `main`
may also publish `:edge` so the NAS can try a build before a release.

### Updates for the container

Containers don't update themselves; this one follows the usual practice:

- **The image carries the versions** (above). Synology Container Manager
  checks downloaded images against the registry and shows its own "update
  available" badge; the update is Project > Action > Stop, pull, Build/Start
  (or `docker compose pull && docker compose up -d`).
- **Automatic pulls, if wanted.** `docker/compose.yaml` ships a commented-out
  Watchtower sidecar, scoped by label so it updates only this container:

  ```yaml
  services:
    app:                       # named after the new app name
      image: ghcr.io/petruchio96/<new-name>:latest
      labels:
        - com.centurylinklabs.watchtower.enable=true
    # Uncomment to pull new versions automatically (checks once a day).
    # watchtower:
    #   image: containrrr/watchtower
    #   volumes:
    #     - /var/run/docker.sock:/var/run/docker.sock
    #   command: --label-enable --cleanup --interval 86400
    #   restart: unless-stopped
  ```

- **The in-page notice is open (ask the user).** The first design had the
  server ask GitHub (`core/updates.py`, install kind `CONTAINER`, which
  exists). The server is now static nginx, so the *browser* would have to
  ask, and `connect-src 'self'` blocks that. Either add
  `https://api.github.com` to `connect-src` (the mockups assume this: the
  Settings page shows "Version X is available. Ask the person who runs this
  site to update it."), or bake the version into the image and drop the
  notice.

### Mockups

Design artifact: https://claude.ai/artifact/7vLiemwRBdyC351wLkS3SD. They
are current for this design (updated 2026-10-11): the Location tab (with a
Tweak that switches between saving in place and the Download bar), the
Date & Time tab, Add Photos from this computer (switch between the
Chrome/Edge folder view and the Safari/iPad drop zone), the map, Settings
(saved in the browser only), and the browser's own sign-in box, which
appears only when the host sets a password.

### Hosting on Synology (goes into `docs/SELF_HOSTING.md`)

1. Container Manager > Project > Create with `docker/compose.yaml` (image
   from GHCR). Optionally set `APP_USERNAME`/`APP_PASSWORD` in `.env`.
2. Control Panel > Login Portal > Advanced > Reverse Proxy: source HTTPS,
   the hostname (for example `fotofixer.iramnas.synology.me`),
   port 443; destination `http://localhost:8080`; add the HSTS header.
3. Security > Certificate: a Let's Encrypt certificate covering that
   hostname (DSM can issue one for subdomains of a synology.me address;
   check the wildcard option there).
4. Share the address. Nothing else to configure; there's no folder to mount.

Generic Docker, Caddy, and Traefik examples go in the same document.

### Phases (one branch / PR each)

0. **Trial (a throwaway branch, not merged).** Ask the user for test files
   first: real R8 CR3s and DNGs (on the NAS share), a JPG, **an iPhone
   HEIC**, and **a CR2** (the R8 shoots only CR3, so the CR2 comes from an
   older camera or a sample file). A bare page that:
   - reads and writes GPS and all three date tags with the ExifTool
     WebAssembly build on all five formats, and compares the result with the
     desktop's ExifTool 13.59 (same tags, the file still opens in Lightroom
     and Synology Photos, nothing else changed);
   - checks the package's license, its ExifTool version (13.42 in its README
     vs our 13.59), memory with a 30 MB CR3, and whether it needs
     cross-origin isolation;
   - loads Pyodide with the pure modules and times the first and cached
     loads on a PC and an iPad;
   - saves back in place in Chrome, and downloads in Safari and on an iPad.

   Go if CR3 and HEIC writes are correct. If not, **stop and plan again with
   the user**. The fallback they named is uploading photos to the container
   for editing, which needs a new design (uploads, temp storage and cleanup,
   size limits, the Synology proxy's 60 s timeout); the rejected NAS-mount
   design is not it.

   **Result (2026-10-12): GO.** Branch `web-trial`, report in
   `web_trial/TRIAL_REPORT.md`. JPG, both HEICs, and the CR2 written by the
   WebAssembly build are byte-identical to ExifTool 13.59's; the DNG and
   CR3 differ only in the XMPToolkit version string, and the CR3's QuickTime
   dates. What Phase 1 onwards must carry over from the trial:
   - `@uswriting/exiftool` 1.0.9 + `@6over3/zeroperl-ts` 1.0.10 (Apache-2.0,
     ExifTool 13.42 inside): vendor both JS files and `zeroperl.wasm`
     (24 MB, 7 MB gzip). No cross-origin isolation needed (no shared
     memory), so no COOP/COEP.
   - **Patch the vendored zeroperl file system** (quadratic append; the
     trial's `vendor/zeroperl.js` has the fix): RAW writes 0.6 s instead
     of 15 s in the browser. One ExifTool call at a time (a queue in the
     worker; two at once crash the instance). Pass bytes (`Uint8Array`),
     not `File` objects (2× faster reads). In the worker, set
     `globalThis.window`/`document` before importing (zeroperl's browser
     detection), and pass a `fetch` option for the wasm's URL.
   - **CR3 QuickTime dates:** the wasm process is in UTC, so write
     `QuickTime:CreateDate`/`ModifyDate` explicitly with the UTC value the
     app computes (the visitor's zone, or the photo's offset); a zone
     suffix and `-api QuickTimeUTC` do nothing. EXIF dates need nothing.
   - Pyodide 314.0.7 (Python 3.14) from npm + the `tzdata` wheel: 12 MB,
     loads in 2 s on a PC; the pure modules ran unchanged with real time
     zone data. iPad timing still to measure; the JS-port fallback stands.
   - Saving through a `FileSystemFileHandle` works (tested via OPFS). Still
     by hand: Lightroom and Synology Photos on the written files
     (`~/Pictures/FotoFixer web trial/`), the real folder picker, Safari
     and the iPad.
1. **Skeleton.** Container, compose, optional password, headers, CI build,
   `LICENSE`; open a folder / add photos / drag and drop; Photo List with
   thumbnails, GPS badges, Show filter, selection; the summary pane. Deploy
   on the NAS.

   **Built 2026-10-12 (branch `web-skeleton`):** `web/` (no build step:
   `index.html`, `app/*.js` modules, `worker/exif_worker.js`, `vendor/`
   fetched by `packaging/fetch_web_vendor.py`), `docker/` (Dockerfile on
   `nginx-unprivileged`, `nginx.conf` with the headers, the password
   entrypoint, `compose.yaml`, `check_container.sh`), the `web` job in
   `build.yml` (Node tests + container checks; its `changes` job skips the
   desktop builds for web-only pushes), `LICENSE` (MIT). Add Photos is a menu:
   Open a Folder (Chrome/Edge, read-write, subfolders included), Choose
   Photos, Choose a Folder; plus drag and drop. Left for later phases:
   - **The Add Photos picker dialog** of the mockups (folder tree, folder
     tiles, "Add Photos in Subfolders"): the menu covers the three sources
     for now.
   - **HEIC thumbnails in Chrome/Edge/Firefox:** iPhone HEICs carry no JPEG
     thumbnail ExifTool can extract, and only Safari decodes HEIC itself,
     so those tiles show the photo icon (with the GPS badge). Fix: a small
     HEIF decoder in WebAssembly (libheif), vendored like ExifTool.
   - **Deploy on the NAS:** the image builds in CI; the Synology steps
     (`docs/SELF_HOSTING.md`) are Phase 5's, and the GHCR image too. Until
     then build locally with `docker compose -f docker/compose.yaml up -d
     --build`.
   - Reading is one photo at a time through the worker (about 0.3 to 1 s
     per photo, 2 to 3 s for a DNG that needs the second PreviewImage
     call); fine for a folder, slow for a thousand photos. A second worker
     instance would double it if ever needed.
2. **Location editing.** Apply/clear GPS (typed, pasted, from a photo),
   overwrite confirmation, backups (folder mode), undo/redo, save in place or
   download (one file or a zip), progress.

   **Built 2026-10-13 (branch `web-location`):** the Location tab
   (`web/app/location_view.js`, state rules ported from
   `gui/presenters/inspector_state.py` in `location_state.js`), pick mode
   and the location source in the Photo List, From a Photo on This
   Computer, Paste, the overwrite question (Cancel / Skip / Replace) and
   the Remove GPS confirmation as non-blocking `<dialog>`s, writes through
   the worker (`exif.write`) one photo at a time with a progress row, in
   place through file handles with `<name>_original.<ext>` backups (Settings
   > Keep Backup Copies of Originals, this browser only) or into memory for
   the Download bar (one file, or a stored zip from `zip_store.js`),
   single-step undo/redo (`edit_history.js`, a port of
   `services/gps_edit_history.py`; undo deletes the backups it made and
   puts the list and selection back), header Undo/Redo/Settings. Coordinate
   parsing runs the real `services/coordinate_service.py` through Pyodide
   in the worker (12 MB more on the first visit; loads in about 2 s on a PC,
   in the background). `packaging/serve_web.py` serves the page locally with
   the container's CSP. Deferred: Pick from a Map (Phase 3), the right-click
   "use this location" menu, and the clipboard watcher (the Paste button
   reads the clipboard when clicked instead).
3. **Map.** Leaflet, OSM and USGS, Esri with the visitor's key, the pin,
   photo dots and previews, Use This Location, Back/Clear.
4. **Date & Time.** Shift, Set, Change Time Zone, camera groups.
5. **Polish and publish.** iPad pass in Safari, `docs/SELF_HOSTING.md`, a
   README section, the GHCR workflow, version **1.10.0** in the same PR, and
   the release.

### Tests

- Python: the existing suite unchanged; a new test lists the modules the
  browser loads and checks that they import nothing that does I/O
  (`subprocess`, `threading`, `core.exiftool_wrapper`).
- JS: unit tests for the file layer (save-mode detection, zip naming, undo
  in download mode) with Node's built-in test runner, no build step, run in
  CI. If logic is ported to JS, both versions run against the same cases.
- Real files (Phase 0, then each phase): tags written in the browser match
  ExifTool 13.59's on the desktop for all five formats.
- Container: `docker run` with `read_only` and `cap_drop`; the page loads;
  the password works when set and is absent when not; the headers are
  present; `grep` the image for keys (none).
- Browser: Chrome against `http://localhost:8080` for each phase; Safari and
  an iPad for downloads; the Synology address over HTTPS from outside the
  LAN.

---

## Part 4: Can a DS920+ host it?

Easily. The container is static nginx: under 60 MB on disk and a few MB of
RAM (`mem_limit: 128m` is generous), with no CPU work, because every photo
is processed on the visitor's own computer. The NAS only serves the app's
files once per visitor (Pyodide and the ExifTool bundle are the bulk, a few
MB each, then cached by the browser). It sits comfortably beside
Vaultwarden and other light containers.

---

## Open questions

1. The in-page update notice: allow the browser to ask GitHub, or drop it
   (see "Updates for the container").
