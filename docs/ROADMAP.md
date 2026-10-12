# Roadmap

The one place for what's next: the order of upcoming work and the plans for
each piece. `PROJECT_CONTEXT.md` describes what exists today; this file
describes what doesn't exist yet. Update it as work lands or decisions change,
and remove finished items.

## Order

1. **Docker/web version** (Part 3), 6 branches counting the Phase 0
   trial. It goes first (the user's call, 2026-10-12). The design is
   browser-only: a static container, editing in each visitor's own browser,
   photos never leave their computer. When it's done, the app is feature
   complete: **version 2.0.0**.
   - **Pick the app's new name before the first image is published.** The
     GHCR image, the page title, the self-hosting docs, and the address the
     user plans to share (`photo-gps-date-changer.iramnas.synology.me`) all
     carry it, and renaming a published image later strands anyone who
     pulled the old one. The desktop rename itself (item 3) can wait.
2. **HEIC (iPhone) support in the desktop app** (below), one branch with a
   version bump, on Linux, Windows, and macOS. The web version supports HEIC
   from its start, so this can land before, during, or after it.
3. **Rename the app** (below), one branch. "Photo GPS Editor" no longer fits:
   it edits dates and times too. The update checker (1.8.0) finds each
   download by name, so the rename must also change the names in
   `core/updates.py` (`RELEASE_ASSETS`), `.github/workflows/build.yml`, and
   the installer (`packaging/windows_installer.iss`: install folder,
   shortcuts, setup file name; its fixed `AppId` keeps upgrades working).
   Copies already out there look for the old names, so keep those for one
   release (or teach the checker both) so they can still update themselves.

Not scheduled:

- **Drag-and-drop loading** of photos into the desktop Photo List. The Add
  Photos picker (folders and photos) covers most of the need. (The web
  version has drag and drop from the start.)
- **Macs.** No release has been tested on a real Mac yet; test when one is
  available.

## Versions

- 1.8.0 (2026-10-12, the in-app update checker) is the latest release.
- While the web version is built, desktop fixes and small improvements are
  **1.8.x**, and HEIC support gets its own bump (1.9.0 if it ships first).
  The usual rules in `CLAUDE.md` still decide whether a branch gets a bump
  at all.
- **2.0.0** marks the web version: the desktop app plus the browser version,
  feature complete. The rename that follows is 2.1.0.
- A release is never its own branch or PR. The branch that bumps the version
  is the release: merge its PR, tag, notes, publish (`RELEASE_CHECKLIST.md`).

---

## Rename the app

"Photo GPS Editor" describes only half of what the app does now that it
edits dates and times as well as GPS. Pick a new name first (the user's
choice), then change it everywhere in one branch, with a version bump.

What the name touches (about 50 places outside the tests):

- **Window titles and menus:** the main window, map, picker, Settings, About.
- **App identity:** `setApplicationName`/`setOrganizationName` in `app.py`.
  These decide where settings and the error log live (registry
  `HKCU\Software\Photo GPS Editor`, `%LOCALAPPDATA%\Photo GPS Editor`,
  `~/.config/Photo GPS Editor`). Changing them would lose the saved
  settings (backups option, Esri key, last folder, map size). So either
  copy the old settings across once at startup, or keep the old internal
  identity and change only what users see.
- **Builds:** `photo_gps_editor.spec` (exe and `.app` names), the AppImage
  (`packaging/build_appimage.sh`, its `.desktop` file), and the download
  file names in `.github/workflows/build.yml`.
- **Project:** `pyproject.toml` name, the README, `PROJECT_CONTEXT.md`,
  `CLAUDE.md`, the map tile User-Agent (OpenStreetMap asks apps to identify
  themselves), and optionally the GitHub repository (GitHub redirects the
  old address).
- **Release notes** for the version that renames it: say what the app used
  to be called, so people find it.

**The bridge: copies of 1.8.0 must still be able to update.** The update
checker in 1.8.0 finds the next version by exact names, so the first
release under the new name has to be one those copies can find and install:

- **Download file names** (`RELEASE_ASSETS` in `core/updates.py`):
  `photo-gps-editor-windows-x86_64-setup.exe`,
  `photo-gps-editor-macos-arm64.zip`,
  `photo-gps-editor-linux-x86_64.tar.gz`, and
  `Photo_GPS_Editor-x86_64.AppImage`.
- **Names inside the downloads.** For the Linux tarball folder and the
  macOS app, 1.8.0 writes its own update script, which expects
  `FOLDER_NAME` "Photo GPS Editor", `BUNDLE_NAME` "Photo GPS Editor.app",
  and `POSIX_EXE_NAME` "Photo GPS Editor". If they change, the swap stops
  safely, but the app doesn't reopen by itself. The AppImage swap and
  Windows Setup need only the file name (and the installer's fixed
  `AppId`).
- **The clean way:** one release under the current name teaches the checker
  (and its update script) the new names before the rename ships. The HEIC
  release (above in the Order) is the natural bridge; any 1.8.x fix would
  do too. It needs no release of its own.
- **The other way:** the rename release also uploads its files under the
  old names and keeps the old names inside the downloads, for that one
  release.

---

## HEIC support (desktop)

The desktop app reads and writes JPG, CR2, CR3, and DNG. iPhones save HEIC
by default, so friends' and family's photos often are. Add it on Linux,
Windows, and macOS:

- `.heic`/`.heif` in `core/file_types.py`. ExifTool 13.59 writes GPS and
  dates to HEIC.
- Thumbnails: Qt can't decode HEIC, so use the embedded preview through
  `read_embedded_previews`. Check that iPhone HEICs have an extractable
  `ThumbnailImage`/`PreviewImage`, and fall back to the file icon when they
  don't.
- Tests with a real iPhone HEIC fixture (GPS and date writes, thumbnails).
- A significant feature, so it gets a version bump in its own PR.
- If it ships before the rename, make it the rename's bridge release:
  teach the update checker the new names too (see "The bridge" under
  "Rename the app").

---

## Part 3: Web version in a Docker container

Decided 2026-10-11/12. It replaces an earlier design (a FastAPI server that
mounted the NAS photo share and ran ExifTool on it), which the user
rejected: the container must never touch photo files.

### Goal

It works like BentoPDF. Someone hosts one container. Friends and family open
its address (the user's will be something like
`https://photo-gps-date-changer.iramnas.synology.me`, behind the Synology
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
- HEIC from the start (and in the desktop app, above).
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
   the hostname (for example `photo-gps-date-changer.iramnas.synology.me`),
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
1. **Skeleton.** Container, compose, optional password, headers, CI build,
   `LICENSE`; open a folder / add photos / drag and drop; Photo List with
   thumbnails, GPS badges, Show filter, selection; the summary pane. Deploy
   on the NAS.
2. **Location editing.** Apply/clear GPS (typed, pasted, from a photo),
   overwrite confirmation, backups (folder mode), undo/redo, save in place or
   download (one file or a zip), progress.
3. **Map.** Leaflet, OSM and USGS, Esri with the visitor's key, the pin,
   photo dots and previews, Use This Location, Back/Clear.
4. **Date & Time.** Shift, Set, Change Time Zone, camera groups.
5. **Polish and publish.** iPad pass in Safari, `docs/SELF_HOSTING.md`, a
   README section, the GHCR workflow, version **2.0.0** in the same PR, and
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

1. The app's new name, needed before the first image is published (see
   Order).
2. The in-page update notice: allow the browser to ask GitHub, or drop it
   (see "Updates for the container").
